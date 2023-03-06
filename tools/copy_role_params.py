#!/usr/bin/python3
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
import os
import sys
import yaml


def filter_count(pair):
    key, _ = pair
    if key.endswith('Count'):
        return True
    else:
        return False


# We need to filter out roles with simillar name that our starts with picked up.
# But we also want to filter out baremetal node provision provided params, ContainerImage,Prepare and so on.
# Example to filter out:
# resource_registry:
#  OS::TripleO::ComputeHCI::Net::SoftwareConfig: OS::Heat::None
#  OS::TripleO::ComputeHCI::Ports::InternalApiPort: /usr/share/openstack-tripleo-heat-templates/network/ports/deployed_internal_api.yaml
#  OS::TripleO::ComputeHCI::Ports::StorageMgmtPort: /usr/share/openstack-tripleo-heat-templates/network/ports/deployed_storage_mgmt.yaml
#  OS::TripleO::ComputeHCI::Ports::StoragePort: /usr/share/openstack-tripleo-heat-templates/network/ports/deployed_storage.yaml
#  OS::TripleO::ComputeHCI::Ports::TenantPort: /usr/share/openstack-tripleo-heat-templates/network/ports/deployed_tenant.yaml
#  This one specifically as it's OSP17.1 EL8.4 compatibility:
#  OS::TripleO::ComputeHCI::Services::NovaLibvirt: /usr/share/openstack-tripleo-heat-templates/deployment/deprecated/nova/nova-libvirt-container-puppet.yaml
def filter_out_reg(pair):
    key, _ = pair
    if ("::Ports::" in key and key.endswith("Port")):
        return False
    elif key.endswith("Services::NovaLibvirt"):
        return False
    elif key.endswith("Net::SoftwareConfig"):
        return False
    else:
        return True


# parameter_defaults:
#  ComputeHCICount: 1
#  ComputeHCIHostnameFormat: computehci-%index%
#  ComputeHCINetworkConfigTemplate: /home/stack/overcloud-deploy/qe-Cloud-0/nic-configs/osdcompute.j2
#  ComputeHCIContainerImagePrepare:
def filter_out_f(pair, rolename=''):
    key, _ = pair
    if key.startswith(rolename):
        return False
    elif ("::Ports::" in key and key.endswith("Port:")):
        return False
    else:
        return True


def filter_out_f_2(pair, removeme=''):
    key, _ = pair
    return False if key.endswith(removeme) else True


def copy_role_parameters(env_files, rolename, new_role_env_file):
    n_role_params_def = {}
    n_role_res_registry = {}

    for file in env_files:
        if os.path.exists(file):
            with open(file, 'r') as env_file:
                contents = yaml.safe_load(env_file)
                pd = contents.get('parameter_defaults', {})
                if pd:
                    for key, value in pd.items():
                        if key.startswith(rolename):
                            n_role_params_def[key] = value
                rr = contents.get('resource_registry', {})
                if rr:
                    for key, value in rr.items():
                        if key.startswith("OS::TripleO::{}:".format(rolename)):
                            n_role_res_registry[key] = value
    # We can have ComputeCount Compute1Count which
    # means we have picked on multiple roles and as we
    # cannot parse here for all role_specific tagged params
    # we simply pick on Count: to figure out if we don't happen
    # to have colision
    role_count = []
    filter_out = []
    role_count = dict(filter(filter_count, n_role_params_def.items()))

    if len(role_count) > 1:
        for key in role_count:
            if key != "{}Count".format(rolename):
                filter_out.append(key[:-5])
    for role in filter_out:
        n_role_params_def = dict(filter(
                                    lambda seq: filter_out_f(seq,
                                                             rolename=role),
                                    n_role_params_def.items()))
    for word in ['Count',
                 'HostnameFormat',
                 'NetworkConfigTemplate',
                 'ContainerImagePrepare',
                 'UpgradeInitCommand']:
        n_role_params_def = dict(filter(
                                   lambda seq: filter_out_f_2(seq,
                                                            removeme=word),
                                    n_role_params_def.items()))
    n_role_res_registry = dict(filter(
                                    lambda seq: filter_out_reg(seq),
                                    n_role_res_registry.items()))
    with open(new_role_env_file, 'w') as new_file:
        # I don't think we can blindly dump here, if one is empty we skip dumping
        dump_var = {}
        if (n_role_params_def != {}):
            dump_var['parameter_defaults'] = n_role_params_def
        if (n_role_res_registry != {}):
            dump_var['resource_registry'] = n_role_res_registry
        if (dump_var != {}):
            yaml.dump(dump_var,
                      new_file,
                      default_flow_style=False)


def filter_role_parameters(env_files, rolename, new_role_env_file):
    n_role_params_def = {}
    n_role_res_registry = {}

    for file in env_files:
        if os.path.exists(file):
            with open(file, 'r') as env_file:
                contents = yaml.safe_load(env_file)
                pd = contents.get('parameter_defaults', {})
                if pd:
                    for key, value in pd.items():
                        if key.startswith(rolename):
                            n_role_params_def[key] = value
                rr = contents.get('resource_registry', {})
                if rr:
                    for key, value in rr.items():
                        if key.startswith("OS::TripleO::{}:".format(rolename)):
                            n_role_res_registry[key] = value
    # We can have ComputeCount Compute1Count which
    # means we have picked on multiple roles and as we
    # cannot parse here for all role_specific tagged params
    # we simply pick on Count: to figure out if we don't happen
    # to have colision
    role_count = []
    filter_out = []
    role_count = dict(filter(filter_count, n_role_params_def.items()))
    if len(role_count) > 1:
        for key in role_count:
            if key != "{}Count".format(rolename):
                filter_out.append(key[:-5])
    for role in filter_out:
        n_role_params_def = dict(filter(
                                    lambda seq: filter_out_f(seq,
                                                             rolename=role),
                                    n_role_params_def.items()))
    for word in ['Count',
                 'HostnameFormat',
                 'NetworkConfigTemplate',
                 'ContainerImagePrepare',
                 'UpgradeInitCommand']:
        n_role_params_def = dict(filter(
                                   lambda seq: filter_out_f_2(seq,
                                                            removeme=word),
                                    n_role_params_def.items()))
    n_role_res_registry = dict(filter(
                                    lambda seq: filter_out_reg(seq),
                                    n_role_res_registry.items()))
    return (n_role_res_registry, n_role_params_def)


def rename_parameters(parameters, role_src, role_dst):
    rr, pd = parameters
    new_rr = {}
    new_pd = {}
    for registry in rr.keys():
        new_rr[registry.replace(role_src, role_dst)] = rr[registry]
    for parameter in pd.keys():
        new_pd[parameter.replace(role_src, role_dst)] = pd[parameter]
    return (new_rr, new_pd)


def write_parameters(parameters, new_role_env_file):
    rr, pd = parameters
    with open(new_role_env_file, 'w') as new_file:
        # I don't think we can blindly dump here, if one is empty we skip dumping
        dump_var = {}
        if (pd != {}):
            dump_var['parameter_defaults'] = pd
        if (rr != {}):
            dump_var['resource_registry'] = rr
        if (dump_var != {}):
            yaml.dump(dump_var,
                      new_file,
                      default_flow_style=False)


def parse_opts(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('--environment', '-e', dest='e',
                        help='envs', action = 'append')

    parser.add_argument('--output-file', '-o', dest='output_file', required=True,
                        help='Output file where the outcome is written')

    parser.add_argument('--rolename-src', dest='rolename_src', required=True,
                        help='The name of the role to copy')

    parser.add_argument('--rolename-dst', dest='rolename_dst', required=True,
                        help='The name of the role with paramaters copied')

    opts = parser.parse_known_args(argv[1:])
    return opts


opts = parse_opts(sys.argv)

parameters = filter_role_parameters(opts[0].e, opts[0].rolename_src, opts[0].output_file)
parameters = rename_parameters(parameters, opts[0].rolename_src, opts[0].rolename_dst)
write_parameters(parameters, opts[0].output_file)
