#!/usr/libexec/platform-python
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import openstack
import os
from pathlib import Path
import shutil
import subprocess
import yaml

CONF = json.loads(os.environ['config'])


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
    """Disable nova quotas"""
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


def create_update_clouds_yaml():
    """Disable nova quotas"""
    clouds_yaml_dir = '/etc/openstack'
    clouds_yaml = os.path.join(clouds_yaml_dir, 'clouds.yaml')
    cloud_name = CONF.get('cloud_name', 'undercloud')
    Path(clouds_yaml_dir).mkdir(parents=True, exist_ok=True)

    usr_clouds_yaml_dir = os.path.join(CONF['home_dir'], '.config/openstack')
    usr_clouds_yaml = os.path.join(usr_clouds_yaml_dir, 'clouds.yaml')
    Path(usr_clouds_yaml_dir).mkdir(parents=True, exist_ok=True)

    data = {}
    if os.path.exists(clouds_yaml):
        with open(clouds_yaml, 'r') as fs:
            data = yaml.safe_load(fs)

    if 'clouds' not in data:
        data['clouds'] = {}

    data['clouds'][cloud_name] = {}
    config = {}
    config['auth_type'] = 'http_basic'
    config['auth'] = {}
    config['auth']['username'] = 'admin'
    config['auth']['password'] = CONF.get('admin_password', 'admin')
    config['baremetal_endpoint_override'] = CONF.get(
        'endpoints', {}).get('baremetal', 'https://192.168.24.2:13385/')
    config['network_endpoint_override'] = CONF.get(
            'endpoints', {}).get('network', 'https://192.168.24.2:13696/')
    config['baremetal_introspection_endpoint_override'] = CONF.get(
            'endpoints', {}).get(
                'baremetal_introspection', 'https://192.168.24.2:13696/')
    config['baremetal_api_version'] = '1'
    config['network_api_version'] = '2'

    data['clouds'][cloud_name] = config
    with open(clouds_yaml, 'w') as fs:
        fs.write(yaml.dump(data, default_flow_style=False))

    shutil.copyfile(clouds_yaml, usr_clouds_yaml)

    stat_info = os.stat(CONF['home_dir'])
    os.chown(usr_clouds_yaml_dir, stat_info.st_uid, stat_info.st_gid)
    os.chown(usr_clouds_yaml, stat_info.st_uid, stat_info.st_gid)


def _create_default_keypair(sdk):
    """Set up a default keypair."""
    ssh_dir = os.path.join(CONF['home_dir'], '.ssh')
    public_key_file = os.path.join(ssh_dir, 'id_rsa.pub')
    if (not [True for kp in sdk.compute.keypairs() if kp.name == 'default'] and
            os.path.isfile(public_key_file)):
        with open(public_key_file, 'r') as pub_key_file:
            sdk.compute.create_keypair(name='default',
                                       public_key=pub_key_file.read())


keystone_enabled = 'true' in _run_command(
    ['hiera', 'keystone_enabled']).lower()
if not keystone_enabled:
    create_update_clouds_yaml()

nova_api_enabled = 'true' in _run_command(
    ['hiera', 'nova_api_enabled']).lower()

if not nova_api_enabled:
    print('WARNING: Undercloud Post - Nova API is disabled.')

sdk = openstack.connect(CONF['cloud_name'])

try:
    if nova_api_enabled:
        _configure_nova(sdk)
        _create_default_keypair(sdk)
except Exception:
    print('ERROR: Undercloud Post - Failed.')
    raise
