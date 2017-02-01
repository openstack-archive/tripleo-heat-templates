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


def exit_usage():
    print('Usage %s <yaml file or directory>' % sys.argv[0])
    sys.exit(1)


def validate_mysql_connection(settings):
    no_op = lambda *args: False
    error_status = [0]

    def mysql_protocol(items):
        return 'mysql+pymysql' in items

    def client_bind_address(item):
        return 'bind_address' in item

    def validate_mysql_uri(key, items):
        # Only consider a connection if it targets mysql
        if key.endswith('dsn') and \
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


def validate(filename):
    print('Validating %s' % filename)
    try:
        tpl = yaml.load(open(filename).read())
        if filename.startswith('./puppet/') and \
           validate_mysql_connection(tpl):
            print('ERROR: mysql connection uri should use option bind_address')
            return 1
    except Exception:
        print(traceback.format_exc())
        return 1
    # yaml is OK, now walk the parameters and output a warning for unused ones
    for p in tpl.get('parameters', {}):
        str_p = '\'%s\'' % p
        in_resources =  str_p in str(tpl.get('resources', {}))
        in_outputs =  str_p in str(tpl.get('outputs', {}))
        if not in_resources and not in_outputs:
            print('Warning: parameter %s in template %s appears to be unused'
                  % (p, filename))

    return 0

if len(sys.argv) < 2:
    exit_usage()

path_args = sys.argv[1:]
exit_val = 0
failed_files = []

for base_path in path_args:
    if os.path.isdir(base_path):
        for subdir, dirs, files in os.walk(base_path):
            for f in files:
                if f.endswith('.yaml'):
                    file_path = os.path.join(subdir, f)
                    failed = validate(file_path)
                    if failed:
                        failed_files.append(file_path)
                    exit_val |= failed
    elif os.path.isfile(base_path) and base_path.endswith('.yaml'):
        failed = validate(base_path)
        if failed:
            failed_files.append(base_path)
        exit_val |= failed
    else:
        print('Unexpected argument %s' % base_path)
        exit_usage()

if failed_files:
    print('Validation failed on:')
    for f in failed_files:
        print(f)
else:
    print('Validation successful!')
sys.exit(exit_val)
