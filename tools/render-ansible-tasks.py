#!/usr/bin/env python3
#
# Copyright 2019 Red Hat, Inc.
#
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
#

import argparse
import errno
import json
import os
import sys
import yaml
import yaql


def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Render the Ansible tasks based in the role and the tags selected.'
                    'Those tasks can be used for debugging or linting purposes.')
    subp = parser.add_mutually_exclusive_group(required=True)

    parser.add_argument('--output', required=True, metavar='<tasks directory output>',
                        help="The folder to store the rendered tasks",
                        )

    parser.add_argument('--ansible-tasks', nargs="+", required=True,
                        metavar='<ansible tasks to be rendered>',
                        help='THT tags to filter the Ansible rendering '
                             'i.e. update_tasks')

    subp.add_argument('--roles-list', nargs="+", metavar='<list of roles to render>',
                      help='Composable roles to filter the Ansible rendering '
                           'i.e. Controller Compute')

    subp.add_argument('--all', action='store_true',
                      help='Process all services in the resource registry at once, '
                           'this allows to test all services templates avoiding '
                             'reading and generating all the files.')

    opts = parser.parse_args(argv[1:])
    return opts


def main():
    opts = parse_opts(sys.argv)
    engine = yaql.factory.YaqlFactory().create()
    output = opts.output
    # We open the resource registry once
    resource_registry = "./overcloud-resource-registry-puppet.yaml"
    resource_reg = yaml.load(open(os.path.join(resource_registry), 'r'))

    if (opts.all):
        # This means we will parse all the services defined
        # by default in the resource registry
        roles_list = ["overcloud-resource-registry-puppet"]
    else:
        roles_list = opts.roles_list

    for role in roles_list:
        # We open the role file only once.
        if (opts.all):
            # The service definition will be the same resource registry
            role_resources = resource_reg
        else:
            role_resources = yaml.load(open(os.path.join("./roles/", role + ".yaml"), 'r'))

        for section_task in opts.ansible_tasks:
            if(opts.all):
                # We get all the services in the resource_registry section
                expression = engine(
                    "$.resource_registry"
                )
            else:
                expression = engine(
                    "$.ServicesDefault.flatten().distinct()"
                )
            heat_resources = expression.evaluate(data=role_resources)
            role_ansible_tasks = []

            for resource in heat_resources:
                if(opts.all):
                    # If we use the resource registry as the source of the
                    # data we need to split the service name of the
                    # service config definition
                    resource = resource.split(' ')[0]
                expression = engine(
                  "$.resource_registry.get('" + resource + "')"
                )
                config_file = expression.evaluate(data=resource_reg)
                if(config_file is not None):
                    if('::' in config_file):
                        print("This is a nested Heat resource")
                    else:
                        data_source = yaml.load(open("./" + config_file, 'r'))
                        expression = engine(
                          "$.outputs.role_data.value.get(" + section_task + ").flatten().distinct()"
                        )
                        try:
                            ansible_tasks = expression.evaluate(data=data_source)
                            print(ansible_tasks)
                            role_ansible_tasks = role_ansible_tasks + ansible_tasks
                        except Exception as e:
                            print("There are no tasks in the configuration file")
            if (role_ansible_tasks != []):
                tasks_output_file = os.path.join(output, role + "_" + section_task + ".yml")
                if not os.path.exists(os.path.dirname(tasks_output_file)):
                    try:
                        os.makedirs(os.path.dirname(tasks_output_file))
                    except OSError as exc:
                        if exc.errno != errno.EEXIST:
                            raise
                save = open(tasks_output_file, 'w+')
                yaml.dump(yaml.load(json.dumps(role_ansible_tasks)), save, default_flow_style=False)

if __name__ == '__main__':
    main()
