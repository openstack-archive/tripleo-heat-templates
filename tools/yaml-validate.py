#!/usr/bin/env python
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import sys
import traceback
import yaml


required_params = ['EndpointMap', 'ServiceNetMap', 'DefaultPasswords',
                   'RoleName', 'RoleParameters', 'ServiceData']

# NOTE(bnemec): The duplication in this list is intentional.  For the
# transition to generated environments we have two copies of these files,
# so they need to be listed twice.  Once the deprecated version can be removed
# the duplicate entries can be as well.
envs_containing_endpoint_map = ['tls-endpoints-public-dns.yaml',
                                'tls-endpoints-public-ip.yaml',
                                'tls-everywhere-endpoints-dns.yaml',
                                'tls-endpoints-public-dns.yaml',
                                'tls-endpoints-public-ip.yaml',
                                'tls-everywhere-endpoints-dns.yaml']
ENDPOINT_MAP_FILE = 'endpoint_map.yaml'
OPTIONAL_SECTIONS = ['workflow_tasks', 'cellv2_discovery']
REQUIRED_DOCKER_SECTIONS = ['service_name', 'docker_config', 'puppet_config',
                            'config_settings', 'step_config']
OPTIONAL_DOCKER_SECTIONS = ['docker_puppet_tasks', 'upgrade_tasks',
                            'post_upgrade_tasks', 'update_tasks',
                            'service_config_settings',
                            'host_prep_tasks', 'metadata_settings',
                            'kolla_config', 'logging_source',
                            'logging_groups', 'docker_config_scripts']
REQUIRED_DOCKER_PUPPET_CONFIG_SECTIONS = ['config_volume', 'step_config',
                                          'config_image']
OPTIONAL_DOCKER_PUPPET_CONFIG_SECTIONS = [ 'puppet_tags', 'volumes' ]
# Mapping of parameter names to a list of the fields we should _not_ enforce
# consistency across files on.  This should only contain parameters whose
# definition we cannot change for backwards compatibility reasons.  New
# parameters to the templates should not be added to this list.
PARAMETER_DEFINITION_EXCLUSIONS = {'CephPools': ['description',
                                                 'type',
                                                 'default'],
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
                                   # There's one template that defines this
                                   # differently, and I'm not sure if we can
                                   # safely change it.
                                   'EC2MetadataIp': ['default'],
                                   # Same as EC2MetadataIp
                                   'ControlPlaneDefaultRoute': ['default'],
                                   # TODO(bnemec): Address these existing
                                   # inconsistencies.
                                   'ServiceNetMap': ['description', 'default'],
                                   'network': ['default'],
                                   'ControlPlaneIP': ['default',
                                                      'description'],
                                   'ControlPlaneIp': ['default',
                                                      'description'],
                                   'NeutronBigswitchLLDPEnabled': ['default'],
                                   'NeutronWorkers': ['description'],
                                   'ServerMetadata': ['description'],
                                   'server': ['description'],
                                   'servers': ['description'],
                                   'ExtraConfig': ['description'],
                                   'DefaultPasswords': ['description',
                                                        'default'],
                                   'BondInterfaceOvsOptions': ['description',
                                                               'default',
                                                               'constraints'],
                                   'KeyName': ['constraints'],
                                   'OVNSouthboundServerPort': ['description'],
                                   'ExternalInterfaceDefaultRoute':
                                       ['description', 'default'],
                                   'ManagementInterfaceDefaultRoute':
                                       ['description', 'default'],
                                   'IPPool': ['description'],
                                   'SSLCertificate': ['description',
                                                      'default',
                                                      'hidden'],
                                   'HostCpusList': ['default', 'constraints'],
                                   'NodeIndex': ['description'],
                                   'name': ['description', 'default'],
                                   'image': ['description', 'default'],
                                   'NeutronBigswitchAgentEnabled': ['default'],
                                   'EndpointMap': ['description', 'default'],
                                   'DockerManilaConfigImage': ['description',
                                                               'default'],
                                   'replacement_policy': ['default'],
                                   'CloudDomain': ['description', 'default'],
                                   'EnableLoadBalancer': ['description'],
                                   'ControllerExtraConfig': ['description'],
                                   'NovaComputeExtraConfig': ['description'],
                                   'controllerExtraConfig': ['description'],
                                   'DockerSwiftConfigImage': ['default']
                                   }

PREFERRED_CAMEL_CASE = {
    'ec2api': 'Ec2Api',
    'haproxy': 'HAProxy',
}

# Overrides for docker/puppet validation
# <filename>: True explicitly enables validation
# <filename>: False explicitly disables validation
#
# If a filename is not found in the overrides then the top level directory is
# used to determine which validation method to use.
VALIDATE_PUPPET_OVERRIDE = {
  # docker/service/sshd.yaml is a variation of the puppet sshd service
  './docker/services/sshd.yaml': True,
  # qdr aliases rabbitmq service to provide alternative messaging backend
  './puppet/services/qdr.yaml': False,
}
VALIDATE_DOCKER_OVERRIDE = {
  # docker/service/sshd.yaml is a variation of the puppet sshd service
  './docker/services/sshd.yaml': False,
}

def exit_usage():
    print('Usage %s <yaml file or directory>' % sys.argv[0])
    sys.exit(1)


def to_camel_case(string):
    return PREFERRED_CAMEL_CASE.get(string, ''.join(s.capitalize() or '_' for
                                                    s in string.split('_')))


def get_base_endpoint_map(filename):
    try:
        tpl = yaml.load(open(filename).read())
        return tpl['parameters']['EndpointMap']['default']
    except Exception:
        print(traceback.format_exc())
    return None


def get_endpoint_map_from_env(filename):
    try:
        tpl = yaml.load(open(filename).read())
        return {
            'file': filename,
            'map': tpl['parameter_defaults']['EndpointMap']
        }
    except Exception:
        print(traceback.format_exc())
    return None


def validate_endpoint_map(base_map, env_map):
    return sorted(base_map.keys()) == sorted(env_map.keys())


def validate_hci_compute_services_default(env_filename, env_tpl):
    env_services_list = env_tpl['parameter_defaults']['ComputeServices']
    env_services_list.remove('OS::TripleO::Services::CephOSD')
    roles_filename = os.path.join(os.path.dirname(env_filename),
                                  '../roles/Compute.yaml')
    roles_tpl = yaml.load(open(roles_filename).read())
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
    compute_role_tpl = yaml.load(open(compute_role_filename).read())
    compute_role_services = compute_role_tpl[0]['ServicesDefault']
    for role in hci_role_tpl:
        if role['name'] == 'ComputeHCI':
            hci_role_services = role['ServicesDefault']
            hci_role_services.remove('OS::TripleO::Services::CephOSD')
            if sorted(hci_role_services) != sorted(compute_role_services):
                print('ERROR: ServicesDefault in %s is different from'
                      'ServicesDefault in roles/Compute.yaml' % hci_role_filename)
                return 1
    return 0


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
        content = inctpl['outputs']['role_data']['value'].get('config_settings',{})
        all_content.append(content)
        included_res[:] = []
        if search(content, match_included_res, no_op):
            files = [inctpl['resources'][x]['type'] for x in included_res]
            # parse included content
            for r, f in zip(included_res, files):
                # disregard class names, only consider file names
                if 'OS::' in f:
                    continue
                newfile = os.path.normpath(os.path.dirname(incfile)+'/'+f)
                newtmp = yaml.load(open(newfile).read())
                read_all(newfile, newtmp)

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
                  "::tripleo::profile::base::database::mysql::client"
                  % filename)
            return 1

    return 0


def validate_docker_service(filename, tpl):
    if 'outputs' in tpl and 'role_data' in tpl['outputs']:
        if 'value' not in tpl['outputs']['role_data']:
            print('ERROR: invalid role_data for filename: %s'
                  % filename)
            return 1
        role_data = tpl['outputs']['role_data']['value']

        for section_name in REQUIRED_DOCKER_SECTIONS:
            if section_name not in role_data:
                print('ERROR: %s is required in role_data for %s.'
                      % (section_name, filename))
                return 1

        for section_name in role_data.keys():
            if section_name in REQUIRED_DOCKER_SECTIONS:
                continue
            else:
                if section_name in OPTIONAL_DOCKER_SECTIONS:
                    continue
                elif section_name in OPTIONAL_SECTIONS:
                    continue
                else:
                    print('ERROR: %s is extra in role_data for %s.'
                          % (section_name, filename))
                    return 1

        if 'puppet_config' in role_data:
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
            expected_config_image_parameter = "Docker%sConfigImage" % to_camel_case(config_volume)
            if config_volume and not expected_config_image_parameter in tpl.get('parameters', []):
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
                      print('ERROR: bootstrap_host_exec needs to run as the root user.')
                      return 1

    if 'parameters' in tpl:
        for param in required_params:
            if param not in tpl['parameters']:
                print('ERROR: parameter %s is required for %s.'
                      % (param, filename))
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
        # service_name must match the filename, but with an underscore
        if (role_data['service_name'] !=
                os.path.basename(filename).split('.')[0].replace("-", "_")):
            print('ERROR: service_name should match file name for service: %s.'
                  % filename)
            return 1
        # if service connects to mysql, the uri should use option
        # bind_address to avoid issues with VIP failover
        if 'config_settings' in role_data and \
           validate_mysql_connection(role_data['config_settings']):
            print('ERROR: mysql connection uri should use option bind_address')
            return 1
    if 'parameters' in tpl:
        for param in required_params:
            if param not in tpl['parameters']:
                print('ERROR: parameter %s is required for %s.'
                      % (param, filename))
                return 1
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
    """
    print('Validating %s' % filename)
    retval = 0
    try:
        tpl = yaml.load(open(filename).read())

        # The template alias version should be used instead a date, this validation
        # will be applied to all templates not just for those in the services folder.
        if 'heat_template_version' in tpl and not str(tpl['heat_template_version']).isalpha():
            print('ERROR: heat_template_version needs to be the release alias not a date: %s'
                  % filename)
            return 1

        if VALIDATE_PUPPET_OVERRIDE.get(filename, False) or (
                filename.startswith('./puppet/services/') and
                VALIDATE_PUPPET_OVERRIDE.get(filename, True)):
            retval = validate_service(filename, tpl)

        if VALIDATE_DOCKER_OVERRIDE.get(filename, False) or (
                filename.startswith('./docker/services/') and
                VALIDATE_DOCKER_OVERRIDE.get(filename, True)):
            retval = validate_docker_service(filename, tpl)

        if filename.endswith('hyperconverged-ceph.yaml'):
            retval = validate_hci_compute_services_default(filename, tpl)

        if filename.startswith('./roles/ComputeHCI.yaml'):
            retval = validate_hci_computehci_role(filename, tpl)

    except Exception:
        print(traceback.format_exc())
        return 1
    # yaml is OK, now walk the parameters and output a warning for unused ones
    if 'heat_template_version' in tpl:
        for p, data in tpl.get('parameters', {}).items():
            definition = {'data': data, 'filename': filename}
            param_map.setdefault(p, []).append(definition)
            if p in required_params:
                continue
            str_p = '\'%s\'' % p
            in_resources = str_p in str(tpl.get('resources', {}))
            in_outputs = str_p in str(tpl.get('outputs', {}))
            if not in_resources and not in_outputs:
                print('Warning: parameter %s in template %s '
                      'appears to be unused' % (p, filename))

    return retval

if len(sys.argv) < 2:
    exit_usage()

path_args = sys.argv[1:]
exit_val = 0
failed_files = []
base_endpoint_map = None
env_endpoint_maps = list()
param_map = {}

for base_path in path_args:
    if os.path.isdir(base_path):
        for subdir, dirs, files in os.walk(base_path):
            if '.tox' in dirs:
                dirs.remove('.tox')
            for f in files:
                if f.endswith('.yaml') and not f.endswith('.j2.yaml'):
                    file_path = os.path.join(subdir, f)
                    failed = validate(file_path, param_map)
                    if failed:
                        failed_files.append(file_path)
                    exit_val |= failed
                    if f == ENDPOINT_MAP_FILE:
                        base_endpoint_map = get_base_endpoint_map(file_path)
                    if f in envs_containing_endpoint_map:
                        env_endpoint_map = get_endpoint_map_from_env(file_path)
                        if env_endpoint_map:
                            env_endpoint_maps.append(env_endpoint_map)
    elif os.path.isfile(base_path) and base_path.endswith('.yaml'):
        failed = validate(base_path, param_map)
        if failed:
            failed_files.append(base_path)
        exit_val |= failed
    else:
        print('Unexpected argument %s' % base_path)
        exit_usage()

if base_endpoint_map and \
        len(env_endpoint_maps) == len(envs_containing_endpoint_map):
    for env_endpoint_map in env_endpoint_maps:
        matches = validate_endpoint_map(base_endpoint_map,
                                        env_endpoint_map['map'])
        if not matches:
            print("ERROR: %s needs to be updated to match changes in base "
                  "endpoint map" % env_endpoint_map['file'])
            failed_files.append(env_endpoint_map['file'])
            exit_val |= 1
        else:
            print("%s matches base endpoint map" % env_endpoint_map['file'])
else:
    print("ERROR: Did not find expected number of environments containing the "
          "EndpointMap parameter.  If you meant to add or remove one of these "
          "environments then you also need to update this tool.")
    if not base_endpoint_map:
        failed_files.append(ENDPOINT_MAP_FILE)
    if len(env_endpoint_maps) != len(envs_containing_endpoint_map):
        matched_files = set(os.path.basename(matched_env_file['file'])
                            for matched_env_file in env_endpoint_maps)
        failed_files.extend(set(envs_containing_endpoint_map) - matched_files)
    exit_val |= 1

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
