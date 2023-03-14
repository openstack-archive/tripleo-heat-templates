#!/usr/bin/python3

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
import datetime
import os
import shutil
import sys
import yaml


from io import StringIO
from tripleo_common.image import kolla_builder
from tripleoclient import utils


def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Tool to help to create the multi-rhel container image file')
    parser.add_argument(
        "--output-env-file",
        dest="output_env_file",
        metavar='<file path>',
        required=True,
        help="File to write environment file containing default "
             "ContainerImagePrepare value.",
    )
    parser.add_argument(
        '--local-push-destination',
        dest='push_destination',
        action='store_true',
        default=False,
        help='Include a push_destination to trigger upload to a local '
             'registry.'
    )
    parser.add_argument(
        '--enable-registry-login',
        dest='registry_login',
        action='store_true',
        default=False,
        help='Use this flag to enable the flag to have systems attempt '
               'to login to a remote registry prior to pulling their '
               'containers. This flag should be used when '
               '--local-push-destination is *NOT* used and the target '
               'systems will have network connectivity to the remote '
               'registries. Do not use this for an overcloud that '
               'may not have network connectivity to a remote registry.'
    )
    parser.add_argument(
        '--enable-multi-rhel',
        dest='multi_rhel',
        action='store_true',
        default=False,
        help='Use this flag to enable multi-rhel'
    )
    parser.add_argument(
        '--excludes',
        dest='excludes',
        action='append',
        default=[],
        help='List of services to include/exclude'
    )
    parser.add_argument(
        '--major-override',
        dest='major',
        action='store',
        default='{}',
        help='The override parameters for major release'
    )
    parser.add_argument(
        '--minor-override',
        dest='minor',
        action='store',
        default='{}',
        help='The override parameters for minor release'
    )
    parser.add_argument(
        '--role',
        dest='roles',
        action='append',
        default=[],
        help='List of roles'
    )
    parser.add_argument(
        '--role-file',
        dest='rolefile',
        action='store',
        default='',
        help='role_data.yaml file'
    )

    opts = parser.parse_args(argv[1:])
    return opts


def build_env_file(params):
    f = StringIO()
    f.write('# Generated with the following on %s\n#\n' %
            datetime.datetime.now().isoformat())
    yaml.safe_dump({'parameter_defaults': params}, f,
                   default_flow_style=False,
                   sort_keys=False)
    return f.getvalue()


parsed_args = parse_opts(sys.argv)

auth_required = False

cip = copy.deepcopy(kolla_builder.CONTAINER_IMAGE_PREPARE_PARAM)
if parsed_args.push_destination:
    for entry in cip:
        entry['push_destination'] = True
params = {
    'ContainerImagePrepare': cip
}
if parsed_args.registry_login:
    if parsed_args.push_destination:
        print('[WARNING] --local-push-destination was used '
                         'with --enable-registry-login. Please make '
                         'sure you understand the use of these '
                         'parameters together as they can cause '
                         'deployment failures.')
    print('[NOTE] Make sure to update the paramter_defaults'
          ' with ContainerImageRegistryCredentials for the '
          'registries requiring authentication.')
    params['ContainerImageRegistryLogin'] = True

if parsed_args.multi_rhel:
    cip_exc = copy.deepcopy(cip)
    cip_inc = copy.deepcopy(cip)
    if parsed_args.major is not None:
        major = yaml.safe_load(parsed_args.major)
    if len(parsed_args.excludes) > 0:
        cip_exc[0]['excludes'] = copy.deepcopy(parsed_args.excludes)
        cip_inc[0]['includes'] = copy.deepcopy(parsed_args.excludes)
        if parsed_args.minor is not None:
            minor = yaml.safe_load(parsed_args.minor)
            for key in minor.keys():
                if key in cip_inc[0]['set'].keys():
                    cip_inc[0]['set'][key] = minor[key]
        if parsed_args.major is not None:
            major = yaml.safe_load(parsed_args.major)
            for key in major.keys():
                if key in cip_exc[0]['set'].keys():
                    cip_exc[0]['set'][key] = major[key]
                params_set = params['ContainerImagePrepare'][0]['set']
                if key in params_set.keys():
                    params_set[key] = major[key]
    base_role = [cip_exc[0], cip_inc[0]]
    if parsed_args.rolefile != '':
        read_roles = []
        if os.path.exists(parsed_args.rolefile):
            with open(parsed_args.rolefile) as file:
                roles_f = yaml.safe_load(file)
                for role in roles_f:
                    read_roles.append(role['name'])
        else:
            print('[ERROR] {} role file does'
                           ' not exits'.format(parsed_args.rolefile))
        roles = read_roles
    else:
        roles = parsed_args.roles
    params['MultiRhelRoleContainerImagePrepare'] = base_role
    for role in roles:
        params[('{}ContainerImagePrepare').format(role)] = base_role
env_data = build_env_file(params)
if parsed_args.output_env_file:
    if os.path.exists(parsed_args.output_env_file):
        print("Output env file exists, "
                         "moving it to backup.")
        shutil.move(parsed_args.output_env_file,
                    parsed_args.output_env_file + ".backup")
    utils.safe_write(parsed_args.output_env_file, env_data)
