# Copyright 2023 Red Hat, Inc.
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
import copy
import sys
import yaml


def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Help to modify the baremental deployment script')
    parser.add_argument('--baremetal-deployment', metavar='<baremetal_file>',
                        help="Path to baremetal-deployment.yaml")
    parser.add_argument('--src-role', metavar='<src_role>',
                        help='role')
    parser.add_argument('--dst-role', metavar='<dst_role>',
                        help='role')
    parser.add_argument('nodes', nargs="+", metavar='<node>',
                        help='List of nodes')
    opts = parser.parse_args(argv[1:])

    return opts


opts = parse_opts(sys.argv)
print("File {} src role {} dst role {} "
      "and nodes {}".format(opts.baremetal_deployment,
                            opts.src_role,
                            opts.dst_role,
                            opts.nodes))

with open(opts.baremetal_deployment) as file:
    baremetal = yaml.safe_load(file.read())
    role_src = None
    role_dst = None
    for role in baremetal:
        if role['name'] == opts.src_role:
            role_src = role
        else:
            if role['name'] == opts.dst_role:
                role_dst = role
    if role_src is not None:
        if role_dst is None:
            role_dst = copy.copy(role_src)
            role_dst['count'] = 0
            role_dst['instances'] = []
            role_dst['name'] = opts.dst_role
            hostname_format = "{}-%index%".format(role_dst['name'].lower())
            role_dst['hostname_format'] = hostname_format
            baremetal.append(role_dst)
    for node2move in opts.nodes:
        for node in role_src['instances']:
            if (node['hostname'] == node2move):
                role_dst['count'] = role_dst['count'] + 1
                role_dst['instances'].append(node)
                role_src['instances'].remove(node)
                role_src['count'] = role_src['count'] - 1

if role_src is not None:
    with open(opts.baremetal_deployment, "w") as file:
        yaml.dump(baremetal, file)
