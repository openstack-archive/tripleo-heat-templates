#!/usr/bin/env python
#
# Copyright 2017 Red Hat, Inc.
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
import collections
import os
import sys

from tripleo_common.utils import roles as rolesutils

__tht_root_dir = os.path.dirname(os.path.dirname(__file__))
__tht_roles_dir = os.path.join(__tht_root_dir, 'roles')


def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Generate roles_data.yaml for requested roles. NOTE: '
                    'This is a stripped down version of what is provided by '
                    'the tripleoclient. The tripleoclient should be used for '
                    'additional functionality.')
    parser.add_argument('--roles-path', metavar='<roles directory>',
                        help="Filesystem path containing the roles yaml files",
                        default=__tht_roles_dir)
    parser.add_argument('roles', nargs="+", metavar='<role>',
                        help='List of roles to use to generate the '
                             'roles_data.yaml file')
    opts = parser.parse_args(argv[1:])

    return opts


opts = parse_opts(sys.argv)

roles = collections.OrderedDict.fromkeys(opts.roles)
print(rolesutils.generate_roles_data_from_directory(opts.roles_path,
                                                    roles.keys()))
