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


required_params = ['EndpointMap', 'ServiceNetMap', 'DefaultPasswords']

envs_containing_endpoint_map = ['tls-endpoints-public-dns.yaml',
                                'tls-endpoints-public-ip.yaml',
                                'tls-everywhere-endpoints-dns.yaml']
ENDPOINT_MAP_FILE = 'endpoint_map.yaml'

def exit_usage():
    print('Usage %s <yaml file or directory>' % sys.argv[0])
    sys.exit(1)


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
                                  '../roles_data.yaml')
    roles_tpl = yaml.load(open(roles_filename).read())
    for role in roles_tpl:
        if role['name'] == 'Compute':
            roles_services_list = role['ServicesDefault']
            if sorted(env_services_list) != sorted(roles_services_list):
                print('ERROR: ComputeServices in %s is different '
                      'from ServicesDefault in roles_data.yaml' % env_filename)
                return 1
    return 0

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

    search(settings, no_op, validate_mysql_uri)
    return error_status[0]


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


def validate(filename):
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

        if (filename.startswith('./puppet/services/') and
                filename != './puppet/services/services.yaml'):
            retval = validate_service(filename, tpl)

        if filename.endswith('hyperconverged-ceph.yaml'):
            retval = validate_hci_compute_services_default(filename, tpl)

    except Exception:
        print(traceback.format_exc())
        return 1
    # yaml is OK, now walk the parameters and output a warning for unused ones
    if 'heat_template_version' in tpl:
        for p in tpl.get('parameters', {}):
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

for base_path in path_args:
    if os.path.isdir(base_path):
        for subdir, dirs, files in os.walk(base_path):
            for f in files:
                if f.endswith('.yaml') and not f.endswith('.j2.yaml'):
                    file_path = os.path.join(subdir, f)
                    failed = validate(file_path)
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
        failed = validate(base_path)
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
    print("ERROR: Can't validate endpoint maps since a file is missing. "
          "If you meant to delete one of these files you should update this "
          "tool as well.")
    if not base_endpoint_map:
        failed_files.append(ENDPOINT_MAP_FILE)
    if len(env_endpoint_maps) != len(envs_containing_endpoint_map):
        matched_files = set(os.path.basename(matched_env_file['file'])
                            for matched_env_file in env_endpoint_maps)
        failed_files.extend(set(envs_containing_endpoint_map) - matched_files)
    exit_val |= 1

if failed_files:
    print('Validation failed on:')
    for f in failed_files:
        print(f)
else:
    print('Validation successful!')
sys.exit(exit_val)
