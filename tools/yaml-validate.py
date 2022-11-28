#!/usr/bin/env python3
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

import argparse
import glob
import os
import re
import sys
import traceback
import yaml

from copy import copy


def is_string(value):
    return isinstance(value, str)


# Only permit the template alias versions.
# The current template version should be the last element.
# As tripleo-heat-templates is a branched repository, this
# list should contain only the alias name for the current branch.
# This allows to avoid merging old templates versions aliases.
valid_heat_template_versions = [
  'wallaby',
]

current_heat_template_version = valid_heat_template_versions[-1]

required_params = ['EndpointMap', 'ServiceNetMap', 'RoleName',
                   'RoleParameters', 'ServiceData']

OPTIONAL_SECTIONS = ['ansible_group_vars',
                     'cellv2_discovery',
                     'firewall_rules',
                     'firewall_frontend_rules',
                     'firewall_ssl_frontend_rules',
                     'firewall_edge_frontend_rules',
                     'firewall_edge_ssl_frontend_rules',
                     'keystone_resources']
REQUIRED_DOCKER_SECTIONS = ['service_name', 'docker_config', 'puppet_config',
                            'config_settings']
OPTIONAL_DOCKER_SECTIONS = ['container_puppet_tasks', 'upgrade_tasks',
                            'deploy_steps_tasks',
                            'pre_upgrade_rolling_tasks',
                            'post_upgrade_tasks', 'update_tasks',
                            'post_update_tasks', 'service_config_settings',
                            'host_firewall_tasks', 'host_prep_tasks',
                            'metadata_settings', 'kolla_config',
                            'global_config_settings', 'external_deploy_tasks',
                            'external_post_deploy_tasks',
                            'container_config_scripts', 'step_config',
                            'monitoring_subscription', 'scale_tasks',
                            'external_update_tasks', 'external_upgrade_tasks']
REQUIRED_DOCKER_SECTIONS_OVERRIDES = {
    # Runs puppet within a container
    './deployment/neutron/neutron-agents-ib-config-container-puppet.yaml': [
        'service_name',
        'docker_config',
        'config_settings'
    ],
    # Just sets hieradata
    './deployment/neutron/neutron-ovn-dpdk-config-container-puppet.yaml': [
        'service_name',
        'config_settings'
    ],
    # Does not deploy container
    './deployment/ceilometer/ceilometer-base-container-puppet.yaml': [
        'service_name',
        'config_settings'
    ],
    # Does not manage container using docker_config
    './deployment/nova/nova-libvirt-guests-container-puppet.yaml': [
        'service_name',
        'puppet_config',
        'config_settings'
    ],
    # Inherits sections
    './deployment/haproxy/haproxy-edge-container-puppet.yaml': [
        'service_name',
        'config_settings'
    ],
    './deployment/glance/glance-api-edge-container-puppet.yaml': [
        'service_name',
    ],
    # Does not manage container using docker_config
    './deployment/iscsid/iscsid-container-puppet.yaml': [
        'service_name',
        'puppet_config',
        'config_settings'
    ],
}
# ansible tasks cannot be an empty dict or ansible is unhappy
ANSIBLE_TASKS_SECTIONS = ['upgrade_tasks', 'pre_upgrade_rolling_tasks',
                          'post_upgrade_tasks', 'update_tasks',
                          'post_update_tasks', 'host_prep_tasks',
                          'external_deploy_tasks',
                          'external_post_deploy_tasks']
REQUIRED_DOCKER_PUPPET_CONFIG_SECTIONS = ['config_volume', 'step_config',
                                          'config_image']
OPTIONAL_DOCKER_PUPPET_CONFIG_SECTIONS = ['puppet_tags', 'volumes']
REQUIRED_DOCKER_LOGGING_OUTPUTS = ['config_settings', 'docker_config',
                                   'volumes', 'host_prep_tasks']
# Mapping of parameter names to a list of the fields we should _not_ enforce
# consistency across files on.  This should only contain parameters whose
# definition we cannot change for backwards compatibility reasons.  New
# parameters to the templates should not be added to this list.
PARAMETER_DEFINITION_EXCLUSIONS = {
    'CephPools': ['description', 'type', 'default'],
    'ManagementNetCidr': ['default'],
    'ManagementAllocationPools': ['default'],
    'ExternalNetCidr': ['default'],
    'ExternalAllocationPools': ['default'],
    'StorageNetCidr': ['default'],
    'StorageAllocationPools': ['default'],
    'StorageMgmtNetCidr': ['default'],
    'StorageMgmtAllocationPools': ['default'],
    'TenantNetCidr': ['default'],
    'TenantAllocationPools': ['default'],
    'InternalApiNetCidr': ['default'],
    'InternalApiAllocationPools': ['default'],
    'UpdateIdentifier': ['description'],
    'key_name': ['default'],
    'CeilometerAgentCentralLoggingSource': ['default'],
    'CeilometerAgentIpmiLoggingSource': ['default'],
    'CeilometerAgentNotificationLoggingSource': ['default'],
    'CinderApiLoggingSource': ['default'],
    'CinderSchedulerLoggingSource': ['default'],
    'CinderVolumeLoggingSource': ['default'],
    'DesignateApiLoggingSource': ['default'],
    'DesignateCentralLoggingSource': ['default'],
    'DesignateMiniDNSLoggingSource': ['default'],
    'DesignateProducerLoggingSource': ['default'],
    'DesignateSinkLoggingSource': ['default'],
    'DesignateWorkerLoggingSource': ['default'],
    'GlanceApiLoggingSource': ['default'],
    'GnocchiApiLoggingSource': ['default'],
    'HeatApiCfnLoggingSource': ['default'],
    'HeatApiLoggingSource': ['default'],
    'HeatEngineLoggingSource': ['default'],
    'KeystoneLoggingSource': ['default'],
    'KeystoneErrorLoggingSource': ['default'],
    'KeystoneAdminAccessLoggingSource': ['default'],
    'KeystoneAdminErrorLoggingSource': ['default'],
    'KeystoneMainAccessLoggingSource': ['default'],
    'KeystoneMainErrorLoggingSource': ['default'],
    'LibvirtVncCACert': ['description'],
    'NeutronApiLoggingSource': ['default'],
    'NeutronDhcpAgentLoggingSource': ['default'],
    'NeutronL3AgentLoggingSource': ['default'],
    'NeutronMetadataAgentLoggingSource': ['default'],
    'NeutronOpenVswitchAgentLoggingSource': ['default'],
    'NovaApiLoggingSource': ['default'],
    'NovaComputeLoggingSource': ['default'],
    'NovaConductorLoggingSource': ['default'],
    'NovaMetadataLoggingSource': ['default'],
    'NovaSchedulerLoggingSource': ['default'],
    'NovaVncproxyLoggingSource': ['default'],
    'OctaviaApiLoggingSource': ['default'],
    'OctaviaHealthManagerLoggingSource': ['default'],
    'OctaviaHousekeepingLoggingSource': ['default'],
    'OctaviaWorkerLoggingSource': ['default'],
    'OvnMetadataAgentLoggingSource': ['default'],
    'PlacementLoggingSource': ['default'],
    # There's one template that defines this
    # differently, and I'm not sure if we can
    # safely change it.
    'ControlPlaneDefaultRoute': ['default'],
    # TODO(bnemec): Address these existing inconsistencies.
    'ServiceNetMap': ['description', 'default'],
    'network': ['default'],
    'ControlPlaneIP': ['default',
                       'description'],
    'ControlPlaneIp': ['default',
                       'description'],
    'NeutronBigswitchLLDPEnabled': ['default'],
    'NeutronWorkers': ['description'],
    'NeutronEnableDVR': ['default'],
    'ServerMetadata': ['description'],
    'server': ['description'],
    'servers': ['description'],
    'ExtraConfig': ['description'],
    'BondInterfaceOvsOptions': ['description',
                                'default',
                                'constraints'],
    'OVNSouthboundServerPort': ['description'],
    'ExternalInterfaceDefaultRoute': ['description', 'default'],
    'ManagementInterfaceDefaultRoute': ['description', 'default'],
    'IPPool': ['description'],
    'SSLCertificate': ['description', 'default', 'hidden'],
    'NodeIndex': ['description'],
    'name': ['description', 'default'],
    'image': ['description', 'default'],
    'NeutronBigswitchAgentEnabled': ['default'],
    'EndpointMap': ['description', 'default'],
    'ContainerManilaConfigImage': ['description', 'default'],
    'replacement_policy': ['default'],
    'CloudDomain': ['description', 'default'],
    'EnableLoadBalancer': ['description'],
    'ControllerExtraConfig': ['description'],
    'NovaComputeExtraConfig': ['description'],
    'controllerExtraConfig': ['description'],
    'ContainerSwiftConfigImage': ['default'],
    'input_values': ['default'],
    'fixed_ips': ['default', 'type']
    }

PREFERRED_CAMEL_CASE = {
    'haproxy': 'HAProxy',
    'metrics-qdr': 'MetricsQdr'
}

# Overrides for docker/puppet validation
# <filename>: True explicitly enables validation
# <filename>: False explicitly disables validation
#
# If a filename is not found in the overrides then the top level directory is
# used to determine which validation method to use.
VALIDATE_PUPPET_OVERRIDE = {
  # deployment/rabbitmq/rabbitmq-messaging*.yaml provide oslo_messaging services
  './deployment/rabbitmq/rabbitmq-messaging-notify-shared-puppet.yaml': False,
  './deployment/rabbitmq/rabbitmq-messaging-notify-container-puppet.yaml': False,
  './deployment/rabbitmq/rabbitmq-messaging-rpc-container-puppet.yaml': False,
  # docker/services/messaging/*.yaml provide oslo_messaging services
  './deployment/messaging/rpc-qdrouterd-container-puppet.yaml': False,
  # docker/services/pacemaker/*-rabbitmq.yaml provide oslo_messaging services
  './deployment/rabbitmq/rabbitmq-messaging-notify-pacemaker-puppet.yaml': False,
  './deployment/rabbitmq/rabbitmq-messaging-rpc-pacemaker-puppet.yaml': False,
  # qdr aliases rabbitmq service to provide alternative messaging backend
  './deployment/qdr/qdroutered-container-puppet.yaml': False,
  # puppet/services/messaging/*.yaml provide oslo_messaging services
  './deployment/messaging/rpc-qdrouterd-container-puppet.yaml': False,

}
VALIDATE_DOCKER_OVERRIDE = {
  # deployment/rabbitmq/rabbitmq-messaging-notify-shared-puppet.yaml does not
  # deploy container
  './deployment/rabbitmq/rabbitmq-messaging-notify-shared-puppet.yaml': False,
  # Does not follow the filename pattern
  './deployment/multipathd/multipathd-container.yaml': True
}
VALIDATE_DOCKER_PUPPET_CONFIG_OVERRIDE = {
    # inherits from nova-conductor
  './deployment/nova/nova-manager-container-puppet.yaml': False,
}
DEPLOYMENT_RESOURCE_TYPES = [
    'OS::Heat::SoftwareDeploymentGroup',
    'OS::Heat::StructuredDeploymentGroup',
    'OS::Heat::SoftwareDeployment',
    'OS::Heat::StructuredDeployment',
]
CONFIG_RESOURCE_TYPES = [
    'OS::Heat::SoftwareConfig',
    'OS::Heat::StructuredConfig'
]

WORKFLOW_TASKS_EXCLUSIONS = [
    './deployment/octavia/octavia-deployment-config.yaml',
]


HEAT_OUTPUTS_EXCLUSIONS = [
    './puppet/extraconfig/tls/ca-inject.yaml',
    './deployed-server/deployed-server.yaml',
    './extraconfig/tasks/ssh/host_public_key.yaml',
    './extraconfig/pre_network/host_config_and_reboot.yaml'
]

CONFIG_IMAGE_OVERRIDES = {
    'ContainerSwiftRingbuilderConfigImage': 'ContainerSwiftConfigImage'
}

SERVICE_NAME_OVERRIDE = {
    './deployment/rabbitmq/rabbitmq-messaging-pacemaker-puppet.yaml': 'rabbitmq',
}


def exit_usage():
    print('Usage %s <yaml file or directory>' % sys.argv[0])
    sys.exit(1)


def to_camel_case(string):
    return PREFERRED_CAMEL_CASE.get(string, ''.join(s.capitalize() or '_' for
                                                    s in string.split('_')))


def compare_parameters(old_impl_path, new_impl_path):
    old_impl_params = []
    new_impl_params = []
    for filename in glob.glob(old_impl_path + "/*.yaml"):
        with open(filename, 'r') as f:
            tpl = yaml.safe_load(f.read())
            old_impl_params.extend(tpl["parameters"].keys())
    for filename in glob.glob(new_impl_path + "/*.yaml"):
        with open(filename, 'r') as f:
            tpl = yaml.safe_load(f.read())
            new_impl_params.extend(tpl["parameters"].keys())
    return set(old_impl_params).difference(set(new_impl_params))


def validate_role_name(filename):
    with open(filename, 'r') as f:
        tpl = yaml.safe_load(f.read())

    role_data = tpl[0]
    if role_data['name'] != os.path.basename(filename).split('.')[0]:
        print('ERROR: role name should match file name for role : %s.'
              % filename)
        return 1
    return 0


def validate_hci_compute_services_default(env_filename, env_tpl):
    env_services_list = env_tpl['parameter_defaults']['ComputeServices']
    env_services_list.remove('OS::TripleO::Services::CephOSD')
    roles_filename = os.path.join(os.path.dirname(env_filename),
                                  '../roles/Compute.yaml')
    with open(roles_filename, 'r') as f:
        roles_tpl = yaml.safe_load(f.read())

    for role in roles_tpl:
        if role['name'] == 'Compute':
            roles_services_list = role['ServicesDefault']
            if sorted(env_services_list) != sorted(roles_services_list):
                print('ERROR: ComputeServices in %s is different from '
                      'ServicesDefault in roles/Compute.yaml' % env_filename)
                return 1
    return 0


def validate_hci_computehci_role(hci_role_filename, hci_role_tpl):
    compute_role_filename = os.path.join(os.path.dirname(hci_role_filename),
                                         './Compute.yaml')
    with open(compute_role_filename, 'r') as f:
        compute_role_tpl = yaml.safe_load(f.read())

    compute_role_services = compute_role_tpl[0]['ServicesDefault']
    for role in hci_role_tpl:
        if role['name'] == 'ComputeHCI':
            hci_role_services = role['ServicesDefault']
            hci_role_services.remove('OS::TripleO::Services::CephOSD')
            if sorted(hci_role_services) != sorted(compute_role_services):
                print('ERROR: ServicesDefault in %s is different from '
                      'ServicesDefault in roles/Compute.yaml' % hci_role_filename)
                return 1
    return 0


def validate_controller_dashboard(filename, tpl):
    control_role_filename = os.path.join(os.path.dirname(filename),
                                         './Controller.yaml')
    with open(control_role_filename, 'r') as f:
        control_role_tpl = yaml.safe_load(f.read())

    control_role_services = control_role_tpl[0]['ServicesDefault']
    for role in tpl:
        if role['name'] == 'ControllerStorageDashboard':
            services = role['ServicesDefault']
            if sorted(services) != sorted(control_role_services):
                print('ERROR: ServicesDefault in %s is different from '
                      'ServicesDefault in roles/Controller.yaml' % filename)
                return 1
    return 0


def validate_hci_role(hci_role_filename, hci_role_tpl):
    role_files = ['HciCephAll', 'HciCephFile', 'HciCephMon', 'HciCephObject']
    if hci_role_filename in ['./roles/' + x + '.yaml' for x in role_files]:
        compute_role_filename = \
            os.path.join(os.path.dirname(hci_role_filename), './Compute.yaml')
        with open(compute_role_filename, 'r') as f:
            compute_role_tpl = yaml.safe_load(f.read())

        compute_role_services = compute_role_tpl[0]['ServicesDefault']
        for role in hci_role_tpl:
            if role['name'] == 'HciCephAll':
                hci_role_services = role['ServicesDefault']
                hci_role_services.remove('OS::TripleO::Services::CephGrafana')
                hci_role_services.remove('OS::TripleO::Services::CephIngress')
                hci_role_services.remove('OS::TripleO::Services::CephMds')
                hci_role_services.remove('OS::TripleO::Services::CephMgr')
                hci_role_services.remove('OS::TripleO::Services::CephMon')
                hci_role_services.remove('OS::TripleO::Services::CephRbdMirror')
                hci_role_services.remove('OS::TripleO::Services::CephRgw')
                hci_role_services.remove('OS::TripleO::Services::CephOSD')
            if role['name'] == 'HciCephFile':
                hci_role_services = role['ServicesDefault']
                hci_role_services.remove('OS::TripleO::Services::CephMds')
                hci_role_services.remove('OS::TripleO::Services::CephOSD')
            if role['name'] == 'HciCephMon':
                hci_role_services = role['ServicesDefault']
                hci_role_services.remove('OS::TripleO::Services::CephMgr')
                hci_role_services.remove('OS::TripleO::Services::CephMon')
                hci_role_services.remove('OS::TripleO::Services::CephOSD')
            if role['name'] == 'HciCephObject':
                hci_role_services = role['ServicesDefault']
                hci_role_services.remove('OS::TripleO::Services::CephRgw')
                hci_role_services.remove('OS::TripleO::Services::CephOSD')
            if sorted(hci_role_services) != sorted(compute_role_services):
                print('ERROR: ServicesDefault in %s is different from '
                      'ServicesDefault in roles/Compute.yaml' % hci_role_filename)
                return 1
    return 0


def validate_ceph_role(ceph_role_filename, ceph_role_tpl):
    role_files = ['CephAll', 'CephFile', 'CephMon', 'CephObject']
    if ceph_role_filename in ['./roles/' + x + '.yaml' for x in role_files]:
        ceph_storage_role_filename = \
            os.path.join(os.path.dirname(ceph_role_filename), './CephStorage.yaml')
        with open(ceph_storage_role_filename, 'r') as f:
            ceph_storage_role_tpl = yaml.safe_load(f.read())

        ceph_storage_role_services = ceph_storage_role_tpl[0]['ServicesDefault']
        for role in ceph_role_tpl:
            if role['name'] == 'CephAll':
                ceph_role_services = role['ServicesDefault']
                ceph_role_services.remove('OS::TripleO::Services::CephGrafana')
                ceph_role_services.remove('OS::TripleO::Services::CephIngress')
                ceph_role_services.remove('OS::TripleO::Services::CephMds')
                ceph_role_services.remove('OS::TripleO::Services::CephMgr')
                ceph_role_services.remove('OS::TripleO::Services::CephMon')
                ceph_role_services.remove('OS::TripleO::Services::CephRbdMirror')
                ceph_role_services.remove('OS::TripleO::Services::CephRgw')
            if role['name'] == 'CephFile':
                ceph_role_services = role['ServicesDefault']
                ceph_role_services.remove('OS::TripleO::Services::CephClient')
                ceph_role_services.remove('OS::TripleO::Services::CephMds')
            if role['name'] == 'CephObject':
                ceph_role_services = role['ServicesDefault']
                ceph_role_services.remove('OS::TripleO::Services::CephClient')
                ceph_role_services.remove('OS::TripleO::Services::CephRgw')
            if sorted(ceph_role_services) != sorted(ceph_storage_role_services):
                print('ERROR: ServicesDefault in %s is different from '
                      'ServicesDefault in roles/Ceph_storage.yaml' % ceph_role_filename)
                return 1
    return 0


def validate_controller_no_ceph_role(filename, tpl):
    control_role_filename = os.path.join(os.path.dirname(filename),
                                         './Controller.yaml')
    with open(control_role_filename, 'r') as f:
        control_role_tpl = yaml.safe_load(f.read())

    control_role_services = control_role_tpl[0]['ServicesDefault']
    for role in tpl:
        if role['name'] == 'ControllerNoCeph':
            services = role['ServicesDefault']
            services.append('OS::TripleO::Services::CephMds')
            services.append('OS::TripleO::Services::CephMgr')
            services.append('OS::TripleO::Services::CephGrafana')
            services.append('OS::TripleO::Services::CephIngress')
            services.append('OS::TripleO::Services::CephMon')
            services.append('OS::TripleO::Services::CephNfs')
            services.append('OS::TripleO::Services::CephRbdMirror')
            services.append('OS::TripleO::Services::CephRgw')
            if sorted(services) != sorted(control_role_services):
                print('ERROR: ServicesDefault in %s is different from '
                      'ServicesDefault in roles/Controller.yaml' % filename)
                return 1
    return 0


def validate_with_compute_role_services(role_filename, role_tpl, exclude_service=()):
    cmpt_filename = os.path.join(os.path.dirname(role_filename),
                                 './Compute.yaml')
    with open(cmpt_filename, 'r') as f:
        cmpt_tpl = yaml.safe_load(f.read())

    cmpt_services = cmpt_tpl[0]['ServicesDefault']
    cmpt_services = [x for x in cmpt_services if (x not in exclude_service)]

    role_services = set(role_tpl[0]['ServicesDefault'])
    missing_services = list(set(cmpt_services) - role_services)
    if missing_services:
        print('ERROR: ServicesDefault in {0} is missing services [{1}] from '
              'ServicesDefault in roles/Compute.yaml'.format(role_filename,
              ', '.join(missing_services)))
        return 1

    cmpt_us = cmpt_tpl[0].get('update_serial', None)
    tpl_us = role_tpl[0].get('update_serial', None)

    if 'OS::TripleO::Services::CephOSD' in role_services:
        if tpl_us not in (None, 1):
            print('ERROR: update_serial in {0} ({1}) '
                  'is should be 1 as it includes CephOSD {2}'.format(
                      role_filename,
                      tpl_us,
                      cmpt_us))
            return 1
    elif cmpt_us is not None and tpl_us != cmpt_us:
        print('ERROR: update_serial in {0} ({1}) '
              'does not match roles/Compute.yaml {2}'.format(
                  role_filename,
                  tpl_us,
                  cmpt_us))
        return 1

    return 0


def validate_multiarch_compute_roles(role_filename, role_tpl):
    errors = 0
    roles_dir = os.path.dirname(role_filename)
    compute_services = set(role_tpl[0].get('ServicesDefault', []))
    compute_networks = role_tpl[0].get('networks', [])

    for arch in ['ppc64le']:
        arch_filename = os.path.join(roles_dir,
                                     'Compute%s.yaml' % (arch.upper()))
        with open(arch_filename, 'r') as f:
            arch_tpl = yaml.safe_load(f)

        arch_services = set(arch_tpl[0].get('ServicesDefault', []))
        if compute_services != arch_services:
            print('ERROR ServicesDefault in %s and %s do not match' %
                  (role_filename, arch_filename))
            print('ERROR problems with: %s' % (','.join(compute_services.symmetric_difference(arch_services))))
            errors = 1

        arch_networks = arch_tpl[0].get('networks', [])
        if compute_networks != arch_networks:
            print('ERROR networks in %s and %s do not match' %
                  (role_filename, arch_filename))
            print('ERROR problems with: %s' % (','.join(compute_networks.symmetric_difference(arch_networks))))
            errors = 1

    return errors


def search(item, check_item, check_key):
    if check_item(item):
        return True
    elif isinstance(item, list):
        for i in item:
            if search(i, check_item, check_key):
                return True
    elif isinstance(item, dict):
        for k in item.keys():
            if check_key(k, item[k]):
                return True
            elif search(item[k], check_item, check_key):
                return True
    return False


def validate_mysql_connection(settings):
    no_op = lambda *args: False
    error_status = [0]

    def mysql_protocol(items):
        return items == ['EndpointMap', 'MysqlInternal', 'protocol']

    def client_bind_address(item):
        return 'read_default_file' in item and \
               'read_default_group' in item

    def validate_mysql_uri(key, items):
        # Only consider a connection if it targets mysql
        if key.endswith('connection') and \
           search(items, mysql_protocol, no_op):
            # Assume the "bind_address" option is one of
            # the token that made up the uri
            if not search(items, client_bind_address, no_op):
                error_status[0] = 1
        return False

    search(settings, no_op, validate_mysql_uri)
    return error_status[0]


def validate_docker_service_mysql_usage(filename, tpl):
    no_op = lambda *args: False
    included_res = []

    def match_included_res(item):
        is_config_setting = isinstance(item, list) and len(item) > 1 and \
            item[1:] == ['role_data', 'config_settings']
        if is_config_setting:
            included_res.append(item[0])
        return is_config_setting

    def match_use_mysql_protocol(items):
        return items == ['EndpointMap', 'MysqlInternal', 'protocol']

    all_content = []

    def read_all(incfile, inctpl):
        # search for included content
        content = inctpl['outputs']['role_data']['value'].get('config_settings', {})
        all_content.append(content)
        included_res[:] = []
        if search(content, match_included_res, no_op):
            files = [inctpl['resources'][x]['type'] for x in included_res]
            # parse included content
            for r, f in zip(included_res, files):
                # disregard class names, only consider file names
                if 'OS::' in f:
                    continue
                newfilename = \
                    os.path.normpath(os.path.join(os.path.dirname(incfile), f))
                if not os.path.exists(newfilename) and \
                    os.path.exists(newfilename.replace('.yaml', '.j2.yaml')):
                    return  # Skip for now if it's templated
                with open(newfilename, 'r') as newfile:
                    newtmp = yaml.safe_load(newfile.read())
                read_all(newfilename, newtmp)

    read_all(filename, tpl)
    if search(all_content, match_use_mysql_protocol, no_op):
        # ensure this service includes the mysqlclient service
        resources = tpl['resources']
        mysqlclient = [x for x in resources
                       if resources[x]['type'].endswith('mysql-client.yaml')]
        if len(mysqlclient) == 0:
            print("ERROR: containerized service %s uses mysql but "
                  "resource mysql-client.yaml is not used"
                  % filename)
            return 1

        # and that mysql::client puppet module is included in puppet-config
        match_mysqlclient = \
            lambda x: x == [mysqlclient[0], 'role_data', 'step_config']
        role_data = tpl['outputs']['role_data']
        puppet_config = role_data['value']['puppet_config']['step_config']
        if not search(puppet_config, match_mysqlclient, no_op):
            print("ERROR: containerized service %s uses mysql but "
                  "puppet_config section does not include "
                  "tripleo::profile::base::database::mysql::client"
                  % filename)
            return 1

    return 0


def validate_common_service(filename, tpl):
    # NOTE(bogdando): it doesn't always detect volumes in Heat funcs, like:
    #   <func>: [{<func>: [FooCommon, volumes]}, [<listed_volumes>]]
    if 'outputs' not in tpl:
        print('ERROR: missing outputs for filename: %s' % filename)
        return 1
    if validate_ct_volumes(tpl['outputs']):
        return 1
    return 0


def validate_docker_service(filename, tpl):
    if 'outputs' in tpl and 'role_data' in tpl['outputs']:
        if 'value' not in tpl['outputs']['role_data']:
            print('ERROR: invalid role_data for filename: %s'
                  % filename)
            return 1
        role_data = tpl['outputs']['role_data']['value']

        if validate_ct_volumes(role_data):
            return 1

        if list(role_data.keys()) == ['map_merge']:
            merged_role_data = {}
            for part in role_data['map_merge']:
                if list(part.keys()) == ['get_attr']:
                    continue
                merged_role_data.update(part)
            role_data = merged_role_data

        for section_name in REQUIRED_DOCKER_SECTIONS_OVERRIDES.get(filename, REQUIRED_DOCKER_SECTIONS):
            if section_name not in role_data:
                # add an exception if both step_config is used in docker service
                if (section_name == 'docker_config' and
                        role_data.get('step_config', '')):
                    print('ERROR: %s appears to be a baremetal-puppet service'
                        % (filename))
                    return 1
                print('ERROR: %s is required in role_data for %s.'
                      % (section_name, filename))
                return 1

        for section_name in role_data.keys():
            if section_name in REQUIRED_DOCKER_SECTIONS:
                continue
            else:
                if section_name in OPTIONAL_DOCKER_SECTIONS:
                    # check for LP##1768019
                    if section_name in ANSIBLE_TASKS_SECTIONS and \
                            role_data.get(section_name) == {}:
                        print('ERROR: %s cannot be an empty dict. If not '
                              'required please consider removing remove this '
                              'option or setting it to [] or null' %
                              section_name)
                        return 1
                    continue
                elif section_name in OPTIONAL_SECTIONS:
                    continue
                else:
                    print('ERROR: %s is extra in role_data for %s.'
                          % (section_name, filename))
                    return 1

        if 'puppet_config' in role_data and \
                VALIDATE_DOCKER_PUPPET_CONFIG_OVERRIDE.get(filename, True) and \
                role_data.get('puppet_config', {}) != {}:
            if validate_docker_service_mysql_usage(filename, tpl):
                print('ERROR: could not validate use of mysql service for %s.'
                      % filename)
                return 1
            puppet_config = role_data['puppet_config']
            for key in puppet_config:
                if key in REQUIRED_DOCKER_PUPPET_CONFIG_SECTIONS:
                    continue
                else:
                    if key in OPTIONAL_DOCKER_PUPPET_CONFIG_SECTIONS:
                        continue
                    else:
                        print('ERROR: %s should not be in puppet_config section.'
                              % key)
                        return 1
            for key in REQUIRED_DOCKER_PUPPET_CONFIG_SECTIONS:
                if key not in puppet_config:
                    print('ERROR: %s is required in puppet_config for %s.'
                          % (key, filename))
                    return 1

            config_volume = puppet_config.get('config_volume')
            expected_config_image_parameter = \
                "Container%sConfigImage" % to_camel_case(config_volume)
            expected_config_image_parameter = CONFIG_IMAGE_OVERRIDES.get(
                expected_config_image_parameter,
                expected_config_image_parameter
            )
            if config_volume and expected_config_image_parameter not in tpl.get('parameters', []):
                print('ERROR: Missing %s heat parameter for %s config_volume.'
                      % (expected_config_image_parameter, config_volume))
                return 1

        if 'docker_config' in role_data:
            docker_config = role_data['docker_config']
            for _, step in docker_config.items():
                if not isinstance(step, dict):
                    # NOTE(mandre) this skips everything that is not a dict
                    # so we may ignore some containers definitions if they
                    # are in a map_merge for example
                    continue
                for _, container in step.items():
                    if not isinstance(container, dict):
                        continue
                    command = container.get('command', '')
                    if isinstance(command, list):
                        command = ' '.join(map(str, command))
                    if 'bootstrap_host_exec' in command \
                            and container.get('user') != 'root':
                        print('ERROR: bootstrap_host_exec needs to run '
                              'as the root user.')
                        return 1

        if 'upgrade_tasks' in role_data and role_data['upgrade_tasks']:
            if (validate_upgrade_tasks(role_data['upgrade_tasks']) or
                validate_upgrade_tasks_duplicate_whens(filename)):
                print('ERROR: upgrade_tasks validation failed')
                return 1

    if 'parameters' in tpl:
        for param in required_params:
            if param not in tpl['parameters']:
                print('ERROR: parameter %s is required for %s.'
                      % (param, filename))
                return 1
    return 0


def validate_ct_volumes(data):
    '''Ensure we don't have any trailing "/" in data for volumes'''
    def check_volumes(volumes):
        if not volumes:
            return 0
        elif isinstance(volumes, list):
            return sum([check_volumes(item) for item in volumes])
        elif isinstance(volumes, dict):
            return sum([check_volumes(item) for item in volumes.values()])
        elif isinstance(volumes, str):
            vol_def = volumes.split(':')
            try:
                if vol_def[0][-1] == '/' or vol_def[1][-1] == '/':
                    print('ERROR: trailing "/" detected'
                          ' for {}'.format(volumes))
                    return 1
            except IndexError:
                # Not a volume definition, ignore it
                pass
        return 0

    if not data:
        return 0
    result = 0
    for _, item in enumerate(data):
        if isinstance(data[item], dict):
            if 'volumes' not in data[item]:
                result += validate_ct_volumes(data[item])
            else:
                result += check_volumes(data[item]['volumes'])
        elif isinstance(item, list):
            if 'volumes' not in item:
                result += validate_ct_volumes(item)
            else:
                result += check_volumes(item.index('volumes'))
        else:
            continue
    return result


def validate_docker_logging_template(filename, tpl):
    if 'outputs' not in tpl:
        print('ERROR: outputs are missing from: %s' % filename)
        return 1
    missing_entries = [
        entry for entry in REQUIRED_DOCKER_LOGGING_OUTPUTS
        if entry not in tpl['outputs']]
    if any(missing_entries):
        print('ERROR: The file %s is missing the following output(s):'
              ' %s' % (filename, ', '.join(missing_entries)))
        return 1
    if validate_ct_volumes(tpl['outputs']):
        return 1
    return 0


def validate_service(filename, tpl):
    if 'outputs' in tpl and 'role_data' in tpl['outputs']:
        if 'value' not in tpl['outputs']['role_data']:
            print('ERROR: invalid role_data for filename: %s'
                  % filename)
            return 1
        role_data = tpl['outputs']['role_data']['value']
        if 'service_name' not in role_data:
            print('ERROR: service_name is required in role_data for %s.'
                  % filename)
            return 1
        # service_name must match the beginning of the file name, but with an underscore
        service_name = \
                os.path.basename(filename).split('.')[0].rsplit('-', 2)[0].replace('-', '_')

        if is_string(role_data['service_name']):
            service_name = SERVICE_NAME_OVERRIDE.get(filename, service_name)
            if not role_data['service_name'].startswith(service_name):
                print('ERROR: service_name "%s" should match the beginning of the '
                      'filename: %s (%s).'
                      % (role_data['service_name'], os.path.basename(filename), service_name))
                return 1
        # if service connects to mysql, the uri should use option
        # bind_address to avoid issues with VIP failover
        if 'config_settings' in role_data and \
           validate_mysql_connection(role_data['config_settings']):
            print('ERROR: mysql connection uri should use option bind_address')
            return 1
        if 'upgrade_tasks' in role_data and role_data['upgrade_tasks']:
            if (validate_upgrade_tasks(role_data['upgrade_tasks']) or
                validate_upgrade_tasks_duplicate_whens(filename)):
                print('ERROR: upgrade_tasks validation failed')
                return 1

    if 'parameters' in tpl:
        for param in required_params:
            if param not in tpl['parameters']:
                print('ERROR: parameter %s is required for %s.'
                      % (param, filename))
                return 1
    return 0


def _rsearch_keys(d, pattern, search_keynames=False, enter_lists=False):
    """Deep regex search through a dict for k or v matching a pattern

    Returns a list of the matched parent keys. Nested keypaths are
    represented as lists. Looks for either values (default) or keys mathching
    the search pattern. A key name may also be joined an integer index, when
    the matched value belongs to a list and enter_lists is enabled.

    Example:

    >>> example_dict = { 'key1' : [ 'value1', { 'key1': 'value2' } ],
                         'key2' : 'value2',
                         'key3' : { 'key3a': 'value3a' },
                         'key4' : { 'key4a': { 'key4aa': 'value4aa',
                                               'key4ab': 'value4ab',
                                               'key4ac': 'value1'},
                                    'key4b': 'value4b'} }
    >>>_rsearch_keys(example_dict, 'value1', search_keynames=False,
                     enter_lists=True)
    [['key1', 0], ['key4', 'key4a', 'key4ac']]
    >>> _rsearch_keys(example_dict, 'key4aa', search_keynames=True)
    [['key4', 'key4a', 'key4aa']]
    >>> _rsearch_keys(example_dict, 'key1', True, True)
    [['key1', 1, 'key1']]

    """
    def _rsearch_keys_nested(d, pattern, search_keynames=False,
                             enter_lists=False, workset=None, path=None):
        if path is None:
            path = []
        # recursively walk through the dict, optionally entering lists
        if isinstance(d, dict):
            for k, v in d.items():
                path.append(k)
                if (isinstance(v, dict) or enter_lists and
                    isinstance(v, list)):
                    # results are accumulated in the upper scope result var
                    _rsearch_keys_nested(v, pattern, search_keynames,
                                         enter_lists, result, path)

                if search_keynames:
                    target = str(k)
                else:
                    target = str(v)

                if re.search(pattern, target):
                    present = False
                    for entry in result:
                        if set(path).issubset(set(entry)):
                            present = True
                            break
                    if not present:
                        result.append(copy(path))

                path.pop()

        if enter_lists and isinstance(d, list):
            for ind in range(len(d)):
                path.append(ind)
                if (isinstance(d[ind], dict) or
                    enter_lists and isinstance(d[ind], list)):
                    _rsearch_keys_nested(d[ind], pattern, search_keynames,
                                         enter_lists, result, path)
                if re.search(pattern, str(d[ind])):
                    present = False
                    for entry in result:
                        if set(path).issubset(set(entry)):
                            present = True
                            break
                    if not present:
                        result.append(copy(path))

                path.pop()

        return result

    result = []
    return _rsearch_keys_nested(d, pattern, search_keynames, enter_lists)


def _get(d, path):
    """Get a value (or None) from a dict by path given as a list

    Integer values represent indexes in lists, string values are for dict keys
    """
    if not isinstance(path, list):
        raise LookupError("The path needs to be a list")
    for step in path:
        try:
            d = d[step]
        except KeyError:
            return None
    return d


def validate_service_hiera_interpol(f, tpl):
    """Validate service templates for hiera interpolation rules

    Find all {get_param: [ServiceNetMap, ...]} missing hiera
    interpolation of IP addresses or network ranges vs
    the names of the networks, which needs no interpolation
    """
    def _getindex(lst, element):
        try:
            pos = lst.index(element)
            return pos
        except ValueError:
            return None

    if 'ansible' in f or 'endpoint_map' in f:
        return 0

    failed = False
    search_keynames = False
    enter_lists = True
    if 'outputs' in tpl and 'role_data' in tpl['outputs']:
        values_found = _rsearch_keys(tpl['outputs']['role_data'],
                                     'ServiceNetMap',
                                     search_keynames, enter_lists)
        for path in values_found:
            # Omit if external deploy tasks in the path
            if 'external_deploy_tasks' in path:
                continue
            # Omit if deploy steps tasks in the path
            if 'deploy_steps_tasks' in path:
                continue
            # Omit apache remoteip proxy_ips
            if 'apache::mod::remoteip::proxy_ips' in path:
                continue
            # Omit Designate rndc_allowed_addresses
            if ('rndc_allowed_addresses' in path):
                continue
            # Omit Neutron ml2 overlay_ip_version
            if 'neutron::plugins::ml2::overlay_ip_version' in path:
                continue

            # Omit if not a part of {get_param: [ServiceNetMap ...
            if not enter_lists and path[-1] != 'get_param':
                continue
            if enter_lists and path[-1] != 0 and path[-2] != 'get_param':
                continue

            # Omit if it is not a hiera config setting
            if path[1] in ['kolla_config']:
                continue

            path_str = ';'.join(str(x) for x in path)
            # NOTE(bogdando): Omit foo_network keys looking like a network
            # name. The only exception is allow anything under
            # str_replace['params'] ('str_replace;params' in the str notation).
            # We need to escape because of '$' char may be in templated params.
            query = re.compile(r'(\\)?;str(\\)?_replace(\\)?;params(\\)?;\S*?net',
                               re.IGNORECASE)
            if not query.search(re.escape(path_str)):
                # Keep parsing, if foo_vip_network, or anything
                # else that looks like a keystore for an IP address value.
                query = re.compile(r'(?!ip|cidr|addr|bind|host)([^;]\S)*?net',
                                   re.IGNORECASE)
                if query.search(re.escape(path_str)):
                    continue

            # Omit mappings in tht, like:
            # [NetXxxMap, <... ,> {get_param: [ServiceNetMap, ...
            if re.search(r'Map.*get(\\)?_param', re.escape(path_str)):
                continue

            # For the remaining cases, verify if there is a template
            # (like str_replace) with the expected format, which is
            # containing lookup(param_name) interpolation
            str_replace_pos = _getindex(path, 'str_replace')
            params_pos = _getindex(path, 'params')
            if str_replace_pos is None or params_pos is None:
                print("ERROR: Missed lookup interpolation via str_replace "
                      "in %s, role_data: %s"
                      % (f, path))
                failed = True
                continue

            # Get the name of the templated param, like NETWORK or $NETWORK
            param_name = path[params_pos + 1]
            str_replace = _get(tpl['outputs']['role_data'],
                               path[:(str_replace_pos + 1)])
            match_interp = re.search("%%\{lookup\(\S+%s\S+\)\}" %
                                     re.escape(param_name),
                                     str_replace['template'])
            if str_replace['template'] is None or match_interp is None:
                print("ERROR: Missed %%{lookup('... %s ...')} interpolation "
                      "in str_replace['template'] "
                      "in %s, role_data: %s" % (param_name, f, path))
                failed = True
                continue
            # end processing this path and go for the next one

    if failed:
        return 1
    else:
        return 0


def validate_upgrade_tasks_duplicate_whens(filename):
    """Take a heat template and starting at the upgrade_tasks
       try to detect duplicate 'when:' statements
    """
    with open(filename, 'r') as template:
        contents = template.read()
        upgrade_task_position = contents.index('upgrade_tasks')
        lines = contents[upgrade_task_position:].splitlines()
        count = 0
        duplicate = ''
        for line in lines:
            if '  when:' in line:
                count += 1
                if count > 1:
                    print("ERROR: found duplicate when statements in %s "
                          "upgrade_task: %s %s" % (filename, line, duplicate))
                    return 1
                duplicate = line
            elif ' -' in line:
                count = 0
                duplicate = ''
        return 0


def validate(filename, param_map):
    """Validate a Heat template

    :param filename: The path to the file to validate
    :param param_map: A dict which will be populated with the details of the
                      parameters in the template.  The dict will have the
                      following structure:

                          {'ParameterName': [
                               {'filename': ./file1.yaml,
                                'data': {'description': '',
                                         'type': string,
                                         'default': '',
                                         ...}
                                },
                               {'filename': ./file2.yaml,
                                'data': {'description': '',
                                         'type': string,
                                         'default': '',
                                         ...}
                                },
                                ...
                           ]}
    Returns a global retval that indicates any failures had been in the check progress.
    """
    if args.quiet < 1:
        print('Validating %s' % filename)
    retval = 0
    try:
        with open(filename, 'r') as f:
            tpl = yaml.safe_load(f.read())

        is_heat_template = 'heat_template_version' in tpl

        # The template version should be in the list of supported versions for the current release.
        # This validation will be applied to all templates not just for those in the services folder.
        if is_heat_template:
            tpl_template_version = str(tpl['heat_template_version'])

            if tpl_template_version not in valid_heat_template_versions:
                print('ERROR: heat_template_version in template %s '
                      'is not valid: %s (allowed values %s)'
                    % (
                        filename,
                        tpl_template_version,
                        ', '.join(valid_heat_template_versions)
                    )
                )
                return 1
            if tpl_template_version != current_heat_template_version \
                    and args.quiet < 2:
                print('Warning: heat_template_version in template %s '
                      'is outdated: %s (current %s)'
                    % (
                        filename,
                        tpl_template_version,
                        current_heat_template_version
                    )
                )

        if VALIDATE_PUPPET_OVERRIDE.get(filename, False) or (
                re.search(r'^\.\/deployment\/.+-(baremetal|pacemaker)-puppet.yaml$', filename) and
                VALIDATE_PUPPET_OVERRIDE.get(filename, True)):
            retval |= validate_service(filename, tpl)

        if re.search(r'(puppet|docker)\/services', filename) or \
                re.search(r'^\.\/deployment\/', filename):
            retval |= validate_service_hiera_interpol(filename, tpl)

        if re.search(r'^\.\/deployment\/logging\/(files|stdout)\/', filename):
            retval |= validate_docker_logging_template(filename, tpl)
        elif VALIDATE_DOCKER_OVERRIDE.get(filename, False) or (
                re.search(r'^\.\/deployment\/.+-container(-puppet)*.yaml$', filename) and
                VALIDATE_DOCKER_OVERRIDE.get(filename, True)):
            retval |= validate_docker_service(filename, tpl)
        elif re.search(r'^\.\/deployment\/.+-common.*.yaml$', filename):
            retval |= validate_common_service(filename, tpl)

        if filename.endswith('hyperconverged-ceph.yaml'):
            retval |= validate_hci_compute_services_default(filename, tpl)

        if filename.startswith('./roles/'):
            retval = validate_role_name(filename)

        if filename.startswith('./roles/ComputeHCI.yaml') or \
                filename.startswith('./roles/ComputeHCIOvsDpdk.yaml') or \
                filename.startswith('./roles/ComputeHCISriov.yaml'):
            retval |= validate_hci_computehci_role(filename, tpl)

        if filename.startswith('./roles/ControllerStorageDashboard.yaml'):
            retval |= validate_controller_dashboard(filename, tpl)
        if filename in ['./roles/ComputeOvsDpdk.yaml',
                        './roles/ComputeSriov.yaml',
                        './roles/ComputeOvsDpdkRT.yaml',
                        './roles/ComputeSriovRT.yaml',
                        './roles/ComputeHCIOvsDpdk.yaml',
                        './roles/ComputeVdpa.yaml']:
            exclude = [
                'OS::TripleO::Services::OVNController',
                'OS::TripleO::Services::ComputeNeutronOvsAgent',
                'OS::TripleO::Services::Tuned',
                'OS::TripleO::Services::NeutronLinuxbridgeAgent']
            retval |= validate_with_compute_role_services(filename, tpl, exclude)

        if filename.startswith('./roles/ComputeRealTime.yaml'):
            exclude = [
                'OS::TripleO::Services::Tuned',
            ]
            retval |= validate_with_compute_role_services(filename, tpl, exclude)

        if filename.startswith('./roles/Hci'):
            retval |= validate_hci_role(filename, tpl)

        if filename.startswith('./roles/Ceph'):
            retval |= validate_ceph_role(filename, tpl)

        if filename.startswith('./roles/ControllerNoCeph.yaml'):
            retval |= validate_controller_no_ceph_role(filename, tpl)

        if filename == './roles/Compute.yaml':
            retval |= validate_multiarch_compute_roles(filename, tpl)

        if filename in ('./roles/ComputeLocalEphemeral.yaml',
                        './roles/ComputeRBDEphemeral.yaml'):
            retval |= validate_with_compute_role_services(filename, tpl)

        # NOTE(hjensas): The routed network data example is very different ...
        # We need to develop a more advanced validator, probably using a schema
        # definition instead.
        if (filename.startswith('./network_data_') and
                not filename.endswith(('routed.yaml',
                                       'undercloud.yaml',
                                       'default.yaml'))):
            result = validate_network_data_file(filename)
            retval |= result
        else:
            result = retval

        if result == 0 and is_heat_template:
            # check for old style nic config files
            retval |= validate_nic_config_file(filename, tpl)

    except Exception:
        print(traceback.format_exc())
        return 1
    # yaml is OK, now walk the parameters and output a warning for unused ones
    if is_heat_template:
        for p, data in tpl.get('parameters', {}).items():
            definition = {'data': data, 'filename': filename}
            param_map.setdefault(p, []).append(definition)
            if p in required_params:
                continue
            str_p = '\'%s\'' % p
            in_resources = str_p in str(tpl.get('resources', {}))
            in_outputs = str_p in str(tpl.get('outputs', {}))
            in_conditions = str_p in str(tpl.get('conditions', {}))
            in_parameter_groups = str_p in str(tpl.get('parameter_groups', {}))
            if (not in_resources and not in_outputs and not in_conditions
                and not in_parameter_groups and args.quiet < 2):
                print('Warning: parameter %s in template %s '
                      'appears to be unused' % (p, filename))

        resources = tpl.get('resources')
        if resources:
            for resource, data in resources.items():
                if data['type'] in DEPLOYMENT_RESOURCE_TYPES:
                    if 'name' not in data['properties']:
                        print('ERROR: resource %s from %s missing name property.'
                                % (resource, filename))
                        return 1

                elif data['type'] in CONFIG_RESOURCE_TYPES:
                    if 'outputs' in data['properties']:
                        if filename in HEAT_OUTPUTS_EXCLUSIONS:
                            if args.quiet < 1:
                                print('Resource %s from %s uses Heat '
                                      'outputs which are not supported with '
                                      'config-download (ignored due to '
                                      'exclusions).'
                                      % (resource, filename))
                        else:
                            print('ERROR: resource %s from %s uses Heat '
                                  'outputs which are not supported with '
                                  'config-download.'
                                  % (resource, filename))
                            return 1

    return retval


def validate_upgrade_tasks(upgrade_tasks):
    # some templates define its upgrade_tasks via list_concat
    if isinstance(upgrade_tasks, dict):
        if upgrade_tasks.get('list_concat'):
            return validate_upgrade_tasks(upgrade_tasks['list_concat'][1])
        elif upgrade_tasks.get('get_attr'):
            return 0

    for task in upgrade_tasks:
        task_name = task.get("name", "")
        whenline = task.get("when", "")
        if (type(whenline) == list):
            if any('step|int ' in condition for condition in whenline) \
                    and ('step|int == ' not in whenline[0]):
                print('ERROR: \'step|int ==\' condition should be evaluated '
                      'first in when conditions for task (%s)' % (task))
                return 1
        else:
            if (' and ' in whenline) and (' or ' not in whenline) \
                    and args.quiet < 2:
                print("Warning: Consider specifying \'and\' conditions as "
                      "a list to improve readability in task: \"%s\""
                      % (task_name))
    return 0


def validate_network_data_file(data_file_path):
    try:
        with open(data_file_path, 'r') as data_file:
            data_file = yaml.safe_load(data_file.read())

        base_file_path = os.path.dirname(data_file_path) + "/network_data.yaml"
        with open(base_file_path, 'r') as base_file:
            base_file = yaml.safe_load(base_file.read())

        retval = 0
        for n in base_file:
            if n not in data_file:
                print('ERROR: The following network from network_data.yaml is '
                      'missing or differs in %s : %s'
                      % (data_file_path, n))
                retval = 1
        return retval
    except Exception:
        print(traceback.format_exc())
        return 1


def validate_nic_config_file(filename, tpl):
    try:
        if isinstance(tpl.get('resources', {}), dict):
            for r in (tpl.get('resources', {})).items():
                if (r[1].get('type') == 'OS::Heat::StructuredConfig' and
                    r[1].get('properties', {}).get('group') == 'os-apply-config' and
                    r[1].get('properties', {}).get('config', {}).get('os_net_config')):
                    print('ERROR: Using old format of nic configuration file: %s' % filename)
                    print('tools/yaml-nic-config-2-script.py can be used to convert to new format')
                    return 1

    except Exception:
        print(traceback.format_exc())
        return 1
    return 0


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument('--quiet', '-q',
                   action='count',
                   default=0,
                   help='output warnings and errors (-q) or only errors (-qq)')
    p.add_argument('--skip-dir',
                   action='append',
                   dest='skip_dirs',
                   help='The directories to be skipped during file search')
    p.add_argument('path_args',
                   nargs='*',
                   default=['.'])

    return p.parse_args()


args = parse_args()
skip_dirs = args.skip_dirs
path_args = args.path_args
quiet = args.quiet
exit_val = 0
failed_files = []
base_endpoint_map = None
env_endpoint_maps = list()
param_map = {}

for base_path in path_args:
    if os.path.isdir(base_path):
        for subdir, dirs, files in os.walk(base_path):
            for skip_dir in skip_dirs:
                if subdir.startswith(os.path.join('.', skip_dir, '')):
                    skip = True
                    break
            else:
                skip = False

            if skip:
                continue

            for f in files:
                file_path = os.path.join(subdir, f)
                if 'tools/tests/nic_config_convert_samples' in file_path:
                    continue

                if 'environments/services-docker' in file_path:
                    print("ERROR: environments/services-docker should not be "
                          "used any more, use environments/services instead: "
                          "%s " % file_path)
                    failed_files.append(file_path)
                    exit_val |= 1

                if f.endswith('.yaml') and not f.endswith('.j2.yaml'):
                    failed = validate(file_path, param_map)
                    if failed:
                        failed_files.append(file_path)
                    exit_val |= failed
    elif os.path.isfile(base_path) and base_path.endswith('.yaml'):
        failed = validate(base_path, param_map)
        if failed:
            failed_files.append(base_path)
        exit_val |= failed
    else:
        print('Unexpected argument %s' % base_path)
        exit_usage()

# Validate that duplicate parameters defined in multiple files all have the
# same definition.
mismatch_count = 0
for p, defs in param_map.items():
    # Nothing to validate if the parameter is only defined once
    if len(defs) == 1:
        continue
    check_data = [d['data'] for d in defs]
    # Override excluded fields so they don't affect the result
    exclusions = PARAMETER_DEFINITION_EXCLUSIONS.get(p, [])
    ex_dict = {}
    for field in exclusions:
        ex_dict[field] = 'IGNORED'
    for d in check_data:
        d.update(ex_dict)
    # If all items in the list are not == the first, then the check fails
    if check_data.count(check_data[0]) != len(check_data):
        mismatch_count += 1
        exit_val |= 1
        failed_files.extend([d['filename'] for d in defs])
        print('Mismatched parameter definitions found for "%s"' % p)
        print('Definitions found:')
        for d in defs:
            print('  %s:\n    %s' % (d['filename'], d['data']))
print('Mismatched parameter definitions: %d' % mismatch_count)

if failed_files:
    print('Validation failed on:')
    for f in failed_files:
        print(f)
else:
    print('Validation successful!')
sys.exit(exit_val)
