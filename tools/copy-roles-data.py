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
        description='Helper to copy the roles data')
    parser.add_argument('--role-file', metavar='<role_file>',
                        help="Path to role_data.yaml")
    parser.add_argument('--src-role', metavar='<src_role>',
                        help='role')
    parser.add_argument('--minor', metavar='<minor>',
                        help='role')
    parser.add_argument('--major', metavar='<major>',
                        help='role')
    opts = parser.parse_args(argv[1:])
    return opts


opts = parse_opts(sys.argv)
print("File {} src role {} dst role {} "
      "and nodes {}".format(opts.role_file,
                            opts.src_role,
                            opts.minor,
                            opts.major))
with open(opts.role_file) as file:
    role_data = yaml.safe_load(file.read())
    role_src = None
    for role in role_data:
        if role['name'] == opts.src_role:
            role_src = role
    if role_src is not None:
        if opts.minor is not None and opts.minor != opts.src_role:
            minor_role = copy.copy(role_src)
            minor_role['name'] = opts.minor
            srvs = role_src['ServicesDefault']
            minor_role['ServicesDefault'] = []
            for srv in srvs:
                if srv == 'OS::TripleO::Services::NovaLibvirt':
                    minor_role['ServicesDefault'].append('OS::TripleO::Services::NovaLibvirtLegacy')
                else:
                    minor_role['ServicesDefault'].append(srv)
            role_data.append(minor_role)
        if opts.major is not None and opts.major != opts.src_role:
            major_role = copy.copy(role_src)
            major_role['name'] = opts.major
            srvs = role_src['ServicesDefault']
            major_role['ServicesDefault'] = []
            for srv in srvs:
                if srv == 'OS::TripleO::Services::NovaLibvirtLegacy':
                    major_role['ServicesDefault'].append('OS::TripleO::Services::NovaLibvirt')
                else:
                    major_role['ServicesDefault'].append(srv)
            role_data.append(major_role)
if role_src is not None:
    with open(opts.role_file, "w") as file:
        yaml.dump(role_data, file)
