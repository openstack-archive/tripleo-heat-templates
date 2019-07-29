#!/usr/bin/env python

import json
import os
import openstack
import subprocess

from keystoneauth1 import exceptions as ks_exceptions
from mistralclient.api import client as mistralclient
from mistralclient.api import base as mistralclient_exc


CONF = json.loads(os.environ['config'])
WORKBOOK_PATH = '/usr/share/openstack-tripleo-common/workbooks'
THT_DIR = '/usr/share/openstack-tripleo-heat-templates'


def _run_command(args, env=None, name=None):
    """Run the command defined by args and return its output

    :param args: List of arguments for the command to be run.
    :param env: Dict defining the environment variables. Pass None to use
        the current environment.
    :param name: User-friendly name for the command being run. A value of
        None will cause args[0] to be used.
    """
    if name is None:
        name = args[0]

    if env is None:
        env = os.environ
    env = env.copy()

    # When running a localized python script, we need to tell it that we're
    # using utf-8 for stdout, otherwise it can't tell because of the pipe.
    env['PYTHONIOENCODING'] = 'utf8'

    try:
        return subprocess.check_output(args,
                                       stderr=subprocess.STDOUT,
                                       env=env).decode('utf-8')
    except subprocess.CalledProcessError as ex:
        print('ERROR: %s failed: %s' % (name, ex.output))
        raise


def _configure_nova(sdk):
    """ Disable nova quotas """
    sdk.set_compute_quotas('admin', cores='-1', instances='-1', ram='-1')

    # Configure flavors.
    sizings = {'ram': 4096, 'vcpus': 1, 'disk': 40}
    extra_specs = {'resources:CUSTOM_BAREMETAL': 1,
                   'resources:VCPU': 0,
                   'resources:MEMORY_MB': 0,
                   'resources:DISK_GB': 0}
    profiles = ['control', 'compute', 'ceph-storage', 'block-storage',
                'swift-storage', 'baremetal']
    flavors = [flavor.name for flavor in sdk.list_flavors()]
    for profile in profiles:
        if profile not in flavors:
            flavor = sdk.create_flavor(profile, **sizings)
            if profile != 'baremetal':
                extra_specs.update({'capabilities:profile': profile})
            else:
                extra_specs.pop('capabilities:profile', None)
            sdk.set_flavor_specs(flavor.id, extra_specs)
        else:
            flavor = sdk.get_flavor(profile)
            # In place to migrate flavors from rocky too stein
            if flavor.extra_specs.get('capabilities:boot_option') == 'local':
                sdk.unset_flavor_specs(flavor.id, ['capabilities:boot_option'])
    print('INFO: Undercloud Post - Nova configuration completed successfully.')


def _create_default_keypair(sdk):
    """ Set up a default keypair. """
    ssh_dir = os.path.join(CONF['home_dir'], '.ssh')
    public_key_file = os.path.join(ssh_dir, 'id_rsa.pub')
    if (not [True for kp in sdk.compute.keypairs() if kp.name == 'default'] and
            os.path.isfile(public_key_file)):
        with open(public_key_file, 'r') as pub_key_file:
            sdk.compute.create_keypair(name='default',
                                       public_key=pub_key_file.read())


def _configure_workbooks_and_workflows(mistral):
    for workbook in [w for w in mistral.workbooks.list()
                     if w.name.startswith('tripleo')]:
        mistral.workbooks.delete(workbook.name)
    managed_tag = 'tripleo-common-managed'
    all_workflows = mistral.workflows.list()
    workflows_delete = [w.name for w in all_workflows
                        if managed_tag in w.tags]
    # in order to delete workflows they should have no triggers associated
    for trigger in [t for t in mistral.cron_triggers.list()
                    if t.workflow_name in workflows_delete]:
        mistral.cron_triggers.delete(trigger.name)
    for workflow_name in workflows_delete:
        mistral.workflows.delete(workflow_name)
    for workbook in [f for f in os.listdir(WORKBOOK_PATH)
                     if os.path.isfile(os.path.join(WORKBOOK_PATH, f))]:
        mistral.workbooks.create(os.path.join(WORKBOOK_PATH, workbook))
    print('INFO: Undercloud post - Mistral workbooks configured successfully.')


def _store_passwords_in_mistral_env(mistral):
    """ Store required passwords in a mistral environment """
    env_name = 'tripleo.undercloud-config'
    config_data = {
        'undercloud_ceilometer_snmpd_password':
            CONF['snmp_readonly_user_password'],
        'undercloud_db_password':
            CONF['undercloud_db_password'],
        'undercloud_db_host':
            CONF['undercloud_db_host']
    }
    try:
        mistral.environments.get(env_name).variables
        mistral.environments.update(
            name=env_name,
            description='Undercloud configuration parameters',
            variables=json.dumps(config_data, sort_keys=True))
    except (ks_exceptions.NotFound, mistralclient_exc.APIException):
        # The environment is not created, we need to create it
        mistral.environments.create(
            name=env_name,
            description='Undercloud configuration parameters',
            variables=json.dumps(config_data, sort_keys=True))
    print('INFO: Undercloud post - Mistral environment configured '
          'successfully.')


def _prepare_ssh_environment(mistral):
    mistral.executions.create('tripleo.validations.v1.copy_ssh_key')


def _upload_validations_to_swift(mistral):
    mistral.executions.create('tripleo.validations.v1.upload_validations')


def _create_default_plan(mistral):
    plan_exists = [True for c in sdk.list_containers() if
                   c['name'] == 'overcloud']
    if not plan_exists and os.path.isdir(THT_DIR):
        mistral.executions.create(
            'tripleo.plan_management.v1.create_deployment_plan',
            workflow_input={'container': 'overcloud',
                            'use_default_templates': True})
        print('INFO: Undercloud post - Default plan overcloud created.')


nova_api_enabled = 'true' in _run_command(
    ['hiera', 'nova_api_enabled']).lower()
mistral_api_enabled = 'true' in _run_command(
    ['hiera','mistral_api_enabled']).lower()
tripleo_validations_enabled = 'true' in _run_command(
    ['hiera', 'tripleo_validations_enabled']).lower()

if not nova_api_enabled:
    print('WARNING: Undercloud Post - Nova API is disabled.')
if not mistral_api_enabled:
    print('WARNING: Undercloud Post - Mistral API is disabled.')
if not tripleo_validations_enabled:
    print('WARNING: Undercloud Post - Tripleo validations is disabled.')

sdk = openstack.connect(CONF['cloud_name'])

try:
    if nova_api_enabled:
        _configure_nova(sdk)
        _create_default_keypair(sdk)
    if mistral_api_enabled:
        mistral = mistralclient.client(mistral_url=sdk.workflow.get_endpoint(),
                                       session=sdk.session)
        _configure_workbooks_and_workflows(mistral)
        _store_passwords_in_mistral_env(mistral)
        _create_default_plan(mistral)
        if tripleo_validations_enabled:
            _prepare_ssh_environment(mistral)
            _upload_validations_to_swift(mistral)
            print('INFO: Undercloud post - Validations executed and '
                  'uploaded to Swift.')
except Exception:
    print('ERROR: Undercloud Post - Failed.')
    raise
