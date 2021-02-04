#!/usr/bin/env python
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

import os
import tempfile
import yaml

from oslotest import base

from tools import convert_heat_nic_config_to_ansible_j2 as converter

FAKE_PARAM_TO_VAR_MAP = {
    'ControlPlaneDefaultRoute': '{{ ctlplane_gateway_ip }}',
    'ControlPlaneIp': '{{ ctlplane_ip }}',
    'ControlPlaneMtu': '{{ ctlplane_mtu }}',
    'ControlPlaneStaticRoutes': '{{ ctlplane_host_routes }}',
    'ControlPlaneSubnetCidr': '{{ ctlplane_subnet_cidr }}',
    'DnsSearchDomains': '{{ dns_search_domains }}',
    'DnsServers': '{{ ctlplane_dns_nameservers }}',
    'InternalApiInterfaceDefaultRoute': '{{ internal_api_gateway_ip }}',
    'InternalApiInterfaceRoutes': '{{ internal_api_host_routes }}',
    'InternalApiIpSubnet': '{{ internal_api_ip }}/{{ internal_api_cidr }}',
    'InternalApiMtu': '{{ internal_api_mtu }}',
    'InternalApiNetworkVlanID': '{{ internal_api_vlan_id }}',
    'NumDpdkInterfaceRxQueues': '{{ num_dpdk_interface_rx_queues }}',
    'BondInterfaceOvsOptions': '{{ bond_interface_ovs_options }}',
    'TenantInterfaceDefaultRoute': '{{ tenant_gateway_ip }}',
    'TenantInterfaceRoutes': '{{ tenant_host_routes }}',
    'TenantIpSubnet': '{{ tenant_ip }}/{{ tenant_cidr }}',
    'TenantMtu': '{{ tenant_mtu }}',
    'TenantNetworkVlanID': '{{ tenant_vlan_id }}',
}


class ConvertToAnsibleJ2TestCase(base.BaseTestCase):

    def setUp(self):
        super(ConvertToAnsibleJ2TestCase, self).setUp()
        self.fake_param_to_var_map = FAKE_PARAM_TO_VAR_MAP
        stack_env_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/stack_env_simple.yaml')
        networks_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/networks_file_simple.yaml')
        with open(stack_env_file, 'r') as f:
            self.fake_stack_env = yaml.safe_load(f.read())
        self.convert = converter.ConvertToAnsibleJ2(self.fake_stack_env,
                                                    networks_file)

    def test_to_j2_var(self):
        self.assertEqual('{{ some_var }}',
                         converter.ConvertToAnsibleJ2.to_j2_var('some_var'))

    def test_to_j2_var_raises_on_unsupported_type(self):
        for _type in [list(), dict(), int(), bool()]:
            self.assertRaises(RuntimeError,
                              converter.ConvertToAnsibleJ2.to_j2_var,
                              _type)

    def test_create_param_to_var_map(self):
        networks_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/networks_file_simple.yaml')
        param_to_var_map = self.convert.create_param_to_var_map(networks_file)
        self.assertEqual(self.fake_param_to_var_map.keys(),
                         param_to_var_map.keys())
        for key in param_to_var_map:
            self.assertEqual(self.fake_param_to_var_map[key],
                             param_to_var_map[key])

    def test_convert_get_param(self):
        for k, v in self.fake_param_to_var_map.items():
            old = {'get_param': k}
            new = self.convert.convert_get_param(old)
            self.assertEqual(v, new)

        for k, v in self.fake_stack_env['parameter_defaults'].items():
            old = {'get_param': k}
            new = self.convert.convert_get_param(old)
            if isinstance(v, str):
                self.assertTrue(v in new)
                self.assertTrue(new.startswith(converter.QUOTE_FIX + v))
            elif isinstance(v, (bool, int, list, dict)):
                self.assertEqual(v, new)

    def test_convert_get_param_unable_param_not_defined(self):
        old = {'get_param': 'UNKNOWN_PARAM'}
        new = self.convert.convert_get_param(old)
        self.assertEqual(converter.QUOTE_FIX
                         + ('NEED MANUAL CONVERSION: {\'get_param\': '
                           '\'UNKNOWN_PARAM\'}') + converter.QUOTE_FIX, new)

    def test_convert_get_param_comlex_data_struct_not_supported(self):
        old = {'get_param': ['COMPLEX', 'DATA']}
        new = self.convert.convert_get_param(old)
        self.assertEqual(converter.QUOTE_FIX
                         + ('NEED MANUAL CONVERSION: {\'get_param\': '
                            '[\'COMPLEX\', \'DATA\']}') + converter.QUOTE_FIX,
                         new)

    def test_convert_get_attr(self):
        old = {'get_attr': ['MinViableMtu', 'value']}
        new = self.convert.convert_get_attr(old)
        self.assertEqual('{{ min_viable_mtu }}', new)

    def test_convert_get_attr_not_suported(self):
        old = {'get_attr': ['UNSUPPORTED', 'value']}
        new = self.convert.convert_get_attr(old)
        self.assertEqual(('NEED MANUAL CONVERSION: '
                          '{\'get_attr\': [\'UNSUPPORTED\', \'value\']}'), new)

    def test_convert_list_join(self):
        list_join_attrs = ['/', ['foo', 'bar']]
        new = self.convert.convert_list_join(list_join_attrs)
        self.assertEqual('foo/bar', new)

    def test_convert_list_concat(self):
        list_concat_attrs = [['a_list', 'list_a'], ['list_b', 'b_list']]
        new = self.convert.convert_list_concat(list_concat_attrs)
        self.assertEqual(
            ("{{ [['%_fix_quote_%a_list%_fix_quote_%', "
             "'%_fix_quote_%list_a%_fix_quote_%'], "
             "['%_fix_quote_%list_b%_fix_quote_%', "
             "'%_fix_quote_%b_list%_fix_quote_%']] "
             "| flatten }}"), new)

    def test_convert_list_concat_raise_if_not_list(self):
        list_concat_attrs = 'NOT_A_LIST'
        self.assertRaises(RuntimeError,
                          self.convert.convert_list_concat,
                          list_concat_attrs)

    def test_convert_list_concat_unique(self):
        convert_list_concat_unique = [['a_list', 'b_list'],
                                      ['list_b', 'b_list']]
        new = self.convert.convert_list_concat_unique(
            convert_list_concat_unique)
        self.assertEqual(
            ("{{ [['%_fix_quote_%a_list%_fix_quote_%', "
             "'%_fix_quote_%b_list%_fix_quote_%'], "
             "['%_fix_quote_%list_b%_fix_quote_%', "
             "'%_fix_quote_%b_list%_fix_quote_%']] "
             "| flatten | unique }}"), new)

    def test_convert_list_concat_unique_raise_if_not_list(self):
        convert_list_concat_unique = 'NOT_A_LIST'
        self.assertRaises(RuntimeError,
                          self.convert.convert_list_concat_unique,
                          convert_list_concat_unique)

    def test_recursive_convert_str_bool_int_not_converted(self):
        # old is a string
        self.assertEqual('string', self.convert.recursive_convert('string'))
        # old is a boolean
        self.assertEqual(True, self.convert.recursive_convert(True))
        # old is a number
        self.assertEqual(1, self.convert.recursive_convert(1))

    def test_recursive_convert_nothing_to_convert(self):
        old = {'foo': 'bar', 'baz': ['a', 'b', {'c': 'd'}]}
        self.assertEqual(old, self.convert.recursive_convert(old))

    def test_recursive_convert_complex(self):
        addresses = [
            {'ip_netmask': {
                'list_join': ['/',
                              [{'get_param': 'ControlPlaneIp'},
                               {'get_param': 'ControlPlaneSubnetCidr'}]
                              ]}}]
        old = {'type': 'interface', 'name': 'nic1', 'use_dhcp': 'false',
               'addresses': addresses}
        expected = {'name': 'nic1', 'type': 'interface', 'use_dhcp': 'false',
                    'addresses': [
                        {'ip_netmask':
                             '{{ ctlplane_ip }}/{{ ctlplane_subnet_cidr }}'}]}
        self.assertEqual(expected, self.convert.recursive_convert(old))

    def test_recursive_convert_unsupported_intrinsic_fn(self):
        for fn in converter.UNSUPPORTED_HEAT_INTRINSIC_FUNCTIONS:
            old = {'foo': 'bar', 'baz': ['a', 'b', {fn: 'd'}]}
            unsupported_str = (
                "UNSUPPORTED HEAT INTRINSIC FUNCTION {x} REQUIRES MANUAL "
                "CONVERSION {{'{x}': 'd'}}".format(x=fn))
            new = {'foo': 'bar', 'baz': ['a', 'b', unsupported_str]}
            self.assertEqual(new, self.convert.recursive_convert(old))

    def test_convert_template(self):
        template_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/heat_templates/simple.yaml')
        j2_config, mtu_header, j2_header = self.convert.convert_template(
            template_file)
        self.assertIsNone(mtu_header)
        self.assertIsNone(j2_header)
        expected = [
            {'name': 'nic1',
             'type': 'interface',
             'use_dhcp': False,
             'addresses': [{
                 'ip_netmask': '{{ ctlplane_ip }}/{{ ctlplane_subnet_cidr }}'}
             ]},
            {'name': 'nic2',
             'type': 'interface',
             'use_dhcp': False},
            {'type': 'vlan',
             'device': 'nic2',
             'vlan_id': '{{ internal_api_vlan_id }}',
             'addresses': [{
                 'ip_netmask': '{{ internal_api_ip }}/{{ internal_api_cidr }}'}
             ]},
            {'type': 'ovs_bridge',
             'name': 'bridge_name',
             'dns_servers': '{{ ctlplane_dns_nameservers }}',
             'members': [
                 {'type': 'interface',
                  'name': 'nic3',
                  'primary': True},
                 {'type': 'vlan',
                  'vlan_id': '{{ tenant_vlan_id }}',
                  'addresses': [{
                      'ip_netmask': '{{ tenant_ip }}/{{ tenant_cidr }}'}
                  ]},
             ]},
        ]
        self.assertEqual(expected, j2_config['network_config'])

    def convert_heat_to_ansible_j2(self, heat_template, j2_reference,
                                   networks_file='network_file_complex.yaml',
                                   stack_env='stack_env_simple.yaml'):
        networks_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/' + networks_file)
        template_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/heat_templates/' + heat_template)
        reference_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/j2_references/' + j2_reference)
        stack_env_file = os.path.join(
            os.path.dirname(__file__),
            'nic_config_convert_samples/' + stack_env)

        with open(stack_env_file, 'r') as f:
            stack_env = yaml.safe_load(f.read())
        convert = converter.ConvertToAnsibleJ2(stack_env, networks_file)
        j2_config, mtu_header, j2_header = convert.convert_template(
            template_file)

        with tempfile.TemporaryDirectory() as temp_dir:
            j2_template = os.path.abspath(temp_dir) + '/j2_template.j2'
            converter.write_j2_template(j2_template, j2_config, mtu_header,
                                        j2_header)
            with open(reference_file, 'r') as a:
                with open(j2_template, 'r') as b:
                    reference = a.read()
                    result = b.read()

        self.assertEqual(reference, result)

    def test_convert_and_write_file_simple(self):
        self.convert_heat_to_ansible_j2(
            'simple.yaml', 'simple.j2',
            networks_file='networks_file_simple.yaml')

    def test_convert_and_write_file_complex01_incomplete(self):
        self.convert_heat_to_ansible_j2('complex.yaml',
                                        'complex_incomplete.j2')

    def test_convert_and_write_file_complex01_complete(self):
        self.convert_heat_to_ansible_j2('complex.yaml', 'complex_complete.j2',
                                        stack_env='stack_env_complex.yaml')

    def test_convert_2_linux_bonds_vlan_controller(self):
        self.convert_heat_to_ansible_j2('2-linux-bonds-vlans-controller.yaml',
                                        '2-linux-bonds-vlans-controller.j2')

    def test_convert_bond_vlans_controller(self):
        self.convert_heat_to_ansible_j2('bond-vlans-controller.yaml',
                                        'bond-vlans-controller.j2')

    def test_convert_multiple_nics_vlans_controller(self):
        self.convert_heat_to_ansible_j2('multiple-nics-vlans-controller.yaml',
                                        'multiple-nics-vlans-controller.j2')

    def test_convert_single_nic_linux_bridge_vlans_controller(self):
        self.convert_heat_to_ansible_j2(
            'single-nic-linux-bridge-vlans-controller.yaml',
            'single-nic-linux-bridge-vlans-controller.j2')

    def test_convert_single_nic_vlans_controller(self):
        self.convert_heat_to_ansible_j2('single-nic-vlans-controller.yaml',
                                        'single-nic-vlans-controller.j2')
