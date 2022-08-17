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
import collections
import openstack
import os
import re
import sys
import yaml


MIN_VIABLE_MTU_HEADER = (
    "{% set mtu_list = [ctlplane_mtu] %}\n"
    "{% for network in role_networks %}\n"
    "{{ mtu_list.append(lookup('vars', networks_lower[network] ~ '_mtu')) }}\n"
    "{%- endfor %}\n"
    "{% set min_viable_mtu = mtu_list | max %}\n"
)

DUAL_MIN_VIABLE_MTU_HEADER = (
    "{% set mtu_ctlplane_list = [ctlplane_mtu] %}\n"
    "{% set mtu_dataplane_list = [] %}\n"
    "{% for network in role_networks %}\n"
    "{# This block resolves the minimum viable MTU for interfaces connected to #}\n"  # noqa
    "{# the dataplane network(s), which start by Tenant, and also bonds #}\n"
    "{# and bridges that carry multiple VLANs. Each VLAN may have different MTU. #}\n"  # noqa
    "{# The bridge, bond or interface must have an MTU to allow the VLAN with the #}\n"  # noqa
    "{# largest MTU. #}\n"
    "{% if network.startswith('Tenant') %}\n"
    "{{ mtu_dataplane_list.append(lookup('vars', networks_lower[network] ~ '_mtu')) }}\n"  # noqa
    "{# This block resolves the minimum viable MTU for interfaces connected to #}\n"  # noqa
    "{# the control plane network(s) (don't start by Tenant), and also bonds #}\n"  # noqa
    "{# and bridges that carry multiple VLANs. Each VLAN may have different MTU. #}\n"  # noqa
    "{# The bridge, bond or interface must have an MTU to allow the VLAN with the #}\n"  # noqa
    "{# largest MTU. #}\n"
    "{% else %}\n"
    "{{ mtu_ctlplane_list.append(lookup('vars', networks_lower[network] ~ '_mtu')) }}\n"  # noqa
    "{%- endif %}\n"
    "{%- endfor %}\n"
    "{% set min_viable_mtu_ctlplane = mtu_ctlplane_list | max %}\n"
    "{% set min_viable_mtu_dataplane = mtu_dataplane_list | max %}\n"
)

UNSUPPORTED_HEAT_INTRINSIC_FUNCTIONS = {
    'get_file', 'get_resource', 'digest', 'repeat', 'resource_facade',
    'str_replace', 'str_replace_strict', 'str_split', 'map_merge',
    'map_replace', 'yaql', 'equals', 'if', 'not', 'and', 'or', 'filter',
    'make_url', 'contains'
}

QUOTE_FIX = '%_fix_quote_%'
DBL_QUOTE_FIX = '%_double_fix_quote_%'


def parse_opts(argv):
    parser = argparse.ArgumentParser(
            description='Convert to Ansible Jinja2 NIC config templates.')
    parser.add_argument('--stack',
                        metavar='STACK_NAME',
                        help='Name or ID of heat stack (default=overcloud)',
                        default='overcloud')
    parser.add_argument('-n', '--networks_file',
                        metavar='<network_data.yaml>',
                        required=True,
                        help=('Configuration file describing the network '
                              'deployment.'))
    parser.add_argument('-y', '--yes',
                        default=False,
                        action='store_true',
                        help='Overwrite existing files.')
    parser.add_argument('template',
                        metavar='TEMPLATE_FILE',
                        help='Existing NIC config template to convert.')
    parser.add_argument('--standalone',
                        default=False,
                        action='store_true',
                        help='This switch allows the script to operate in '
                             'environments where the orchestration service '
                             'is not available. Such as environemnts with '
                             'ephemeral-heat')

    opts = parser.parse_args(argv[1:])

    return opts


class TemplateDumper(yaml.SafeDumper):
    def represent_ordered_dict(self, data):
        return self.represent_dict(data.items())


class TemplateLoader(yaml.SafeLoader):
    def construct_mapping(self, node):
        self.flatten_mapping(node)
        return collections.OrderedDict(self.construct_pairs(node))


TemplateDumper.add_representer(collections.OrderedDict,
                               TemplateDumper.represent_ordered_dict)
TemplateLoader.add_constructor(yaml.BaseLoader,
                               TemplateLoader.construct_mapping)


class ConvertToAnsibleJ2(object):

    def __init__(self, stack_env, networks_file):
        self.stack_env = stack_env
        self.param_to_var_map = self.create_param_to_var_map(networks_file)
        self.hard_coded_parameters = list()

    @staticmethod
    def unwrap_j2_var(x):
        """Strip jinja2 brackets from string

        When nesting ansible vars in jinja2 the brackets must be
        removed. This also adds appropriate quote fix prefix and
        suffix.
        """
        is_ansible_var = False
        if isinstance(x, str):
            if x.startswith('{{ ') and x.endswith(' }}'):
                is_ansible_var = True
                x = x[3:]
                x = x[:-3]
        else:
            raise RuntimeError(
                'Unsupported type {} for method unwrap_j2_var'.format(type(x)))

        if is_ansible_var:
            return DBL_QUOTE_FIX + '{}'.format(x) + DBL_QUOTE_FIX
        else:
            return QUOTE_FIX + '{}'.format(x) + QUOTE_FIX

    @staticmethod
    def strip_j2_comment(x):
        """Strip jinja2 comment from string

        When nesting hard-coded parameter conversions in jinja2 the
        comment must be removed.
        """
        return re.sub('{#.*#}', '', x)

    def normalize_complex(self, old):
        if isinstance(old, list):
            new = list()
            for i in old:
                if isinstance(i, str):
                    new.append(self.strip_j2_comment(self.unwrap_j2_var(i)))
                if isinstance(i, (bool, int)):
                    new.append(i)
                if isinstance(i, (list, dict)):
                    new.append(self.normalize_complex(i))
        elif isinstance(old, dict):
            new = dict()
            for k, v in old.items():
                k = QUOTE_FIX + '{}'.format(k) + QUOTE_FIX
                if isinstance(v, str):
                    new[k] = self.strip_j2_comment(self.unwrap_j2_var(v))
                if isinstance(v, (bool, int)):
                    new[k] = v
                if isinstance(v, (list, dict)):
                    new[k] = self.normalize_complex(v)
        else:
            raise RuntimeError(
                'Unsupported type {} for method normalize_complex'.format(
                    type(old)))

        return new

    @staticmethod
    def to_j2_var(x):
        if not isinstance(x, str):
            raise RuntimeError(
                'Unsupported type {} for method to_j2_var'.format(type(x)))

        return '{{{{ {} }}}}'.format(x)

    @staticmethod
    def quote_fix(x):
        return QUOTE_FIX + '{}'.format(x) + QUOTE_FIX

    def create_param_to_var_map(self, networks_file):
        _map = {
            'ControlPlaneIp': self.to_j2_var('ctlplane_ip'),
            'ControlPlaneSubnetCidr': self.to_j2_var('ctlplane_subnet_cidr'),
            'ControlPlaneMtu': self.to_j2_var('ctlplane_mtu'),
            'ControlPlaneDefaultRoute': self.to_j2_var('ctlplane_gateway_ip'),
            'ControlPlaneStaticRoutes': self.to_j2_var('ctlplane_host_routes'),
            'DnsServers': self.to_j2_var('ctlplane_dns_nameservers'),
            'DnsSearchDomains': self.to_j2_var('dns_search_domains'),
            'NumDpdkInterfaceRxQueues':
                self.to_j2_var('num_dpdk_interface_rx_queues'),
            'BondInterfaceOvsOptions':
                self.to_j2_var('bond_interface_ovs_options')
        }

        with open(networks_file, 'r') as f:
            networks = yaml.safe_load(f.read())

        for net in networks:
            name = net['name']
            name_lower = net.get('name_lower', net['name'].lower())
            _map.update({
                name + 'NetworkVlanID':
                    self.to_j2_var('{}_vlan_id'.format(name_lower)),
                name + 'IpSubnet':
                    '/'.join([self.to_j2_var('{}_ip'.format(name_lower)),
                              self.to_j2_var('{}_cidr'.format(name_lower))]),
                name + 'InterfaceDefaultRoute':
                    self.to_j2_var('{}_gateway_ip'.format(name_lower)),
                name + 'InterfaceRoutes':
                    self.to_j2_var('{}_host_routes'.format(name_lower)),
                name + 'Mtu':
                    self.to_j2_var('{}_mtu'.format(name_lower))
            })

        return _map

    def convert_get_param(self, old):
        param = old['get_param']
        if isinstance(param, str):
            if param in self.param_to_var_map:
                return self.param_to_var_map[param]
            elif (self.stack_env and
                  param in self.stack_env.get('parameter_defaults', {})):
                stack_value = self.stack_env['parameter_defaults'][param]
                print('INFO - Custom Parameter {} was hard-coded in the '
                      'converted template using the value from the Heat stack '
                      'environment.\n'
                      '  To parameterize the value an ansible var must be '
                      'added using the {{role.name}}ExtraGroupVars '
                      'THT interface and the template modified to use the '
                      'ansible var.'.format(param))
                j2_comment = (
                    '{{# NOTE! Custom parameter {} was hard-coded in '
                    'the converted template. To parameterize use the '
                    '{{role.name}}ExtraGroupVars THT interface and update the '
                    'template to use an ansible var. #}}'.format(param))
                self.hard_coded_parameters.append(param)
                if isinstance(stack_value, str):
                    return self.quote_fix(stack_value + j2_comment)
                else:
                    return stack_value
            else:
                print('WARNING - Manual intervention required. Unable to '
                      'convert get_param occurrence: {}'.format(old))
                return self.quote_fix(
                    'NEED MANUAL CONVERSION: {}'.format(str(old)))
        elif isinstance(param, list):
            print('WARNING - can not convert get_param referencing values in '
                  'complex datastructures. Please review the Ansible Jinja2 '
                  'template and convert this manually.')
            return self.quote_fix(
                'NEED MANUAL CONVERSION: {}'.format(str(old)))

        raise RuntimeError(
            'Unexpected Type {} in get_param: {}'.format(type(param), old))

    def convert_get_attr(self, old):
        attr = old['get_attr']
        if not isinstance(attr, list):
            raise RuntimeError(
                'Attributes for get_attr conversion must of type list.')

        if 'MinViableMtu' in attr:
            return self.to_j2_var('min_viable_mtu')
        elif 'MinViableMtuBondApi' in attr:
            return self.to_j2_var('min_viable_mtu_ctlplane')
        elif 'MinViableMtuBondData' in attr:
            return self.to_j2_var('min_viable_mtu_dataplane')
        else:
            print('WARNING - only MinViableMtu and combined '
                  'MinViableMtuBondApi + MinViableMtuBondData attribute can '
                  'be converted. Please review the Ansible Jinja2 template '
                  'and convert this manually.')
            return 'NEED MANUAL CONVERSION: {}'.format(str(old))

    def convert_list_join(self, list_join_attrs):
        to_join = list()
        for x in list_join_attrs[1]:
            to_join.append(self.recursive_convert(x))

        return list_join_attrs[0].join(to_join)

    def convert_list_concat(self, list_concat_attrs):
        ansible_concat_tpl = "{} | flatten"
        to_concatenate = list()
        if not isinstance(list_concat_attrs, list):
            raise RuntimeError('list_concat_args must be a list')

        for x in list_concat_attrs:
            to_concatenate.append(self.recursive_convert(x))

        to_concatenate = self.normalize_complex(to_concatenate)
        new = ansible_concat_tpl.format(to_concatenate)

        return self.to_j2_var(new)

    def convert_list_concat_unique(self, list_concat_unique_attrs):
        ansible_concat_unique_tpl = "{} | flatten | unique"
        to_concatenate = list()
        if not isinstance(list_concat_unique_attrs, list):
            raise RuntimeError('list_concat_unique_attrs must be a list')

        for x in list_concat_unique_attrs:
            to_concatenate.append(self.recursive_convert(x))

        to_concatenate = self.normalize_complex(to_concatenate)
        new = ansible_concat_unique_tpl.format(to_concatenate)

        return self.to_j2_var(new)

    @staticmethod
    def convert_unsupported(old, fn):
        print('WARNING - can not convert unsupported heat intrinsic function '
              ' {}. Please review the Ansible Jinja2 template and convert '
              'this manually.'.format(fn))
        return ('UNSUPPORTED HEAT INTRINSIC FUNCTION {} '
                'REQUIRES MANUAL CONVERSION {}'.format(fn, old))

    def recursive_convert(self, old):
        if isinstance(old, (bool, str, int)):
            new = old
        elif isinstance(old, dict):
            for fn in UNSUPPORTED_HEAT_INTRINSIC_FUNCTIONS:
                if fn in old:
                    return self.convert_unsupported(old, fn)

            if 'get_param' in old:
                return self.convert_get_param(old)
            elif 'get_attr' in old:
                return self.convert_get_attr(old)
            elif 'list_join' in old:
                return self.convert_list_join(old['list_join'])
            elif 'list_concat_unique' in old:
                return self.convert_list_concat_unique(
                    old['list_concat_unique'])
            else:
                new = collections.OrderedDict()
                for k, v in old.items():
                    if isinstance(v, (bool, str, int)):
                        new[k] = v
                    elif isinstance(v, (list, dict)):
                        new[k] = self.recursive_convert(v)
                    else:
                        raise RuntimeError(
                            'Unexpected Type {} for key: {}'.format(
                                type(v), k))

        elif isinstance(old, list):
            new = list()
            for x in old:
                new.append(self.recursive_convert(x))
        else:
            raise RuntimeError(
                'Unknown type {} for recursive convert'.format(type(old)))

        return new

    def convert_template(self, template):
        with open(template, 'r') as f:
            heat_tpl = yaml.safe_load(f.read())

        resources = set(heat_tpl['resources'].keys())

        if not resources.issubset({'OsNetConfigImpl',
                                   'MinViableMtu',
                                   'MinViableMtuBondApi',
                                   'MinViableMtuBondData'}):
            msg = ('Only OsNetConfigImpl and MinViableMtu resources '
                   'supported. Found resources: {}'.format(resources))
            raise RuntimeError(msg)

        net_config_res = heat_tpl['resources'].get('OsNetConfigImpl')
        mtu_header = None
        if heat_tpl['resources'].get('MinViableMtu'):
            mtu_header = 'single'
        elif (heat_tpl['resources'].get('MinViableMtuBondApi')
                     and heat_tpl['resources'].get('MinViableMtuBondData')):
            mtu_header = 'dual'

        if not net_config_res:
            raise RuntimeError('OsNetConfigImpl resource not found in '
                               'template.')

        net_config_res_props = net_config_res['properties']

        if net_config_res['type'] == 'OS::Heat::Value':
            h_net_conf = net_config_res_props['value']['network_config']
        elif net_config_res['type'] == 'OS::Heat::SoftwareConfig':
            h_net_conf = net_config_res_props['config']['str_replace'][
                'params']['$network_config']['network_config']
        else:
            raise RuntimeError('No network config found in provided template.')

        j2_config = collections.OrderedDict({'network_config': []})
        j2_net_conf = j2_config['network_config']

        j2_net_conf.extend(self.recursive_convert(h_net_conf))

        j2_header = None
        if self.hard_coded_parameters:
            j2_header = (
                '{# The values of the following custom heat parameters was '
                'hard-coded into this template:\n')
            for param in self.hard_coded_parameters:
                j2_header += ' * {}\n'.format(param)
            j2_header += (
                'To parameterize use the {{role.name}}ExtraGroupVars THT '
                'interface and update the template to use an ansible var.\n'
                '#}\n')

        return j2_config, mtu_header, j2_header


def write_j2_template(j2_template, j2_config, mtu_header, j2_header):
    """Write the Jinja2 template file

    This is done in three steps because the YAML dumper insists
    to add quotes:
      write the template file
      read the template file
      re-write it with quotes removed
    """
    with open(j2_template, 'w') as f:
        if j2_header:
            f.write(j2_header)
        f.write('---\n')
        if mtu_header:
            if mtu_header == 'single':
                f.write(MIN_VIABLE_MTU_HEADER)
            elif mtu_header == 'dual':
                f.write(DUAL_MIN_VIABLE_MTU_HEADER)
        yaml.dump(j2_config, f, TemplateDumper, width=256,
                  default_flow_style=False)

    with open(j2_template, 'r') as f:
        data = f.read()
        # Remove quote before jinja2 var reference
        data = data.replace('\'{{', '{{')
        # Remove quote after jinja2 var reference
        data = data.replace('}}\'', '}}')
        # Remove quote before value imported from stack environment
        data = data.replace('\'' + QUOTE_FIX, '')
        # Remove quote after value imported from stack environment
        data = data.replace(QUOTE_FIX + '\'', '')
        # Remove quote before value imported from stack environment
        data = data.replace('\'\'' + DBL_QUOTE_FIX, '')
        # Remove quote after value imported from stack environment
        data = data.replace(DBL_QUOTE_FIX + '\'\'', '')
        # Remove quote_fix string
        data = data.replace(QUOTE_FIX, '')
        data = data.replace(DBL_QUOTE_FIX, '')

    with open(j2_template, 'w') as f:
        f.write(data)


def validate_files(opts, template, networks_file, j2_template):
    if not os.path.exists(template):
        raise RuntimeError('Template file not found {}.'.format(template))
    if not os.path.isfile(template):
        raise RuntimeError('Template {} is not a file.'.format(template))
    if not os.path.exists(networks_file):
        raise RuntimeError('Networks file not found, {}.'.format(
            networks_file))
    if not os.path.isfile(networks_file):
        raise RuntimeError('Networks file {} is not a file.'.format(
            networks_file))
    if os.path.exists(j2_template) and not opts.yes:
        raise RuntimeError('Ansible Jinja2 template {} already exists'.format(
            j2_template))
    if os.path.exists(j2_template) and not os.path.isfile(j2_template):
        raise RuntimeError('Existing {} is not a file.'.format(j2_template))
    pass


def get_stack_environment(stack_name):
    try:
        conn = openstack.connect('undercloud')
        stack = conn.orchestration.find_stack(stack_name)
        if not stack:
            print('INFO: Heat stack {} not found.'.format(stack_name))
            return {}
        stack_env = conn.orchestration.get_stack_environment(stack)
    except Exception as e:
        print('ERROR: Unable to get stack environment.')
        raise e

    return stack_env


def main():
    opts = parse_opts(sys.argv)

    template = os.path.abspath(opts.template)
    networks_file = os.path.abspath(opts.networks_file)
    j2_template = os.path.splitext(template)[0] + '.j2'
    validate_files(opts, template, networks_file, j2_template)

    if not opts.standalone:
        stack_env = get_stack_environment(opts.stack)
    else:
        stack_env = None

    converter = ConvertToAnsibleJ2(stack_env, networks_file)

    j2_config, mtu_header, j2_header = converter.convert_template(template)
    write_j2_template(j2_template, j2_config, mtu_header, j2_header)


if __name__ == '__main__':
    main()
