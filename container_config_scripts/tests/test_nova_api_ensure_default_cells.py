#
# Copyright 2022 Red Hat Inc.
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

from container_config_scripts.nova_api_ensure_default_cells import parse_list_cells
from container_config_scripts.nova_api_ensure_default_cells import replace_db_name
from container_config_scripts.nova_api_ensure_default_cells import template_netloc_credentials
from container_config_scripts.nova_api_ensure_default_cells import template_url
from oslotest import base


class TemplateNetlocCredentialsCase(base.BaseTestCase):
    def test_host(self):
        test_netloc = 'example.com'
        expected_netloc = test_netloc
        templated_netloc = template_netloc_credentials(test_netloc)
        self.assertEqual(expected_netloc, templated_netloc)

    def test_host_port(self):
        test_netloc = 'example.com:1234'
        expected_netloc = test_netloc
        templated_netloc = template_netloc_credentials(test_netloc)
        self.assertEqual(expected_netloc, templated_netloc)

    def test_host_port_ipv6(self):
        test_netloc = '[dead:beef::1]:1234'
        expected_netloc = test_netloc
        templated_netloc = template_netloc_credentials(test_netloc)
        self.assertEqual(expected_netloc, templated_netloc)

    def test_username(self):
        test_netloc = 'foo@example.com'
        expected_netloc = '{username}@example.com'
        templated_netloc = template_netloc_credentials(test_netloc)
        self.assertEqual(expected_netloc, templated_netloc)

    def test_userpass(self):
        test_netloc = 'foo:bar@example.com'
        expected_netloc = '{username}:{password}@example.com'
        templated_netloc = template_netloc_credentials(test_netloc)
        self.assertEqual(expected_netloc, templated_netloc)

    def test_username_index(self):
        test_netloc = 'foo@example.com'
        expected_netloc = '{username5}@example.com'
        templated_netloc = template_netloc_credentials(test_netloc, index=5)
        self.assertEqual(expected_netloc, templated_netloc)

    def test_userpass_index(self):
        test_netloc = 'foo:bar@example.com'
        expected_netloc = '{username5}:{password5}@example.com'
        templated_netloc = template_netloc_credentials(test_netloc, index=5)
        self.assertEqual(expected_netloc, templated_netloc)


class TemplateUrlCase(base.BaseTestCase):
    def test_simple_url(self):
        test_url = 'scheme://foo:bar@example.com:12345/?param=foo&param=bar#blah'
        expected_url = 'scheme://{username}:{password}@example.com:12345/?param=foo&param=bar#blah'
        templated_url = template_url(test_url)
        self.assertEqual(expected_url, templated_url)

    def test_ha_url(self):
        test_url = 'scheme://foo:bar@example.com:12345,foo2:bar2@example2.com:6789,foo3:bar3@example3.com:4321/?param=foo&param=bar#blah'
        expected_url = 'scheme://{username1}:{password1}@example.com:12345,{username2}:{password2}@example2.com:6789,{username3}:{password3}@example3.com:4321/?param=foo&param=bar#blah'
        templated_url = template_url(test_url)
        self.assertEqual(expected_url, templated_url)

    def test_ha_ipv6_url(self):
        test_url = 'scheme://foo:bar@[dead:beef::1]:12345,foo2:bar2@[dead:beef::2]:6789,foo3:bar3@[dead:beef::3]:4321/?param=foo&param=bar#blah'
        expected_url = 'scheme://{username1}:{password1}@[dead:beef::1]:12345,{username2}:{password2}@[dead:beef::2]:6789,{username3}:{password3}@[dead:beef::3]:4321/?param=foo&param=bar#blah'
        templated_url = template_url(test_url)
        self.assertEqual(expected_url, templated_url)


class ParseListCellsCase(base.BaseTestCase):
    def test_no_output(self):
        test_output = ''
        self.assertRaises(ValueError, parse_list_cells, test_output)

    def test_no_cells(self):
        test_output = '''\
+------+------+---------------+---------------------+----------+
| Name | UUID | Transport URL | Database Connection | Disabled |
+------+------+---------------+---------------------+----------+
+------+------+---------------+---------------------+----------+
'''
        expected_cell_dicts = ({}, {})
        cell_dicts = parse_list_cells(test_output)
        self.assertEqual(expected_cell_dicts, cell_dicts)

    def test_cell0(self):
        test_output = '''\
+-------+--------------------------------------+---------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------+
|  Name |                 UUID                 | Transport URL |                                                                         Database Connection                                                                         | Disabled |
+-------+--------------------------------------+---------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------+
| cell0 | 00000000-0000-0000-0000-000000000000 |    none:///   | mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova_cell0?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo |  False   |
+-------+--------------------------------------+---------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------+
'''
        expected_cell0_dict = {
            'name': 'cell0',
            'uuid': '00000000-0000-0000-0000-000000000000',
            'transport_url': 'none:///',
            'database_connection': 'mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova_cell0?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo'
        }
        expected_cell_dicts = (
            {
                'cell0': expected_cell0_dict
            },
            {
                '00000000-0000-0000-0000-000000000000': expected_cell0_dict
            }
        )
        cell_dicts = parse_list_cells(test_output)
        self.assertEqual(expected_cell_dicts, cell_dicts)

    def test_default_cells(self):
        test_output = '''\
+---------+--------------------------------------+--------------------------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------+
|   Name  |                 UUID                 |                                       Transport URL                                        |                                                                         Database Connection                                                                         | Disabled |
+---------+--------------------------------------+--------------------------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------+
|  cell0  | 00000000-0000-0000-0000-000000000000 |                                          none:///                                          | mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova_cell0?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo |  False   |
| default | 541ca4e9-15f7-4178-95de-8af9e3659daf | rabbit://guest:oLniT3uE12BLP4VsyoFt29k3U@controller-0.internalapi.redhat.local:5672/?ssl=1 |    mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo    |  False   |
+---------+--------------------------------------+--------------------------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------+
'''
        expected_cell0_dict = {
            'name': 'cell0',
            'uuid': '00000000-0000-0000-0000-000000000000',
            'transport_url': 'none:///',
            'database_connection': 'mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova_cell0?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo'
        }
        expected_default_dict = {
            'name': 'default',
            'uuid': '541ca4e9-15f7-4178-95de-8af9e3659daf',
            'transport_url': 'rabbit://guest:oLniT3uE12BLP4VsyoFt29k3U@controller-0.internalapi.redhat.local:5672/?ssl=1',
            'database_connection': 'mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo'
        }
        expected_cell_dicts = (
            {
                'cell0': expected_cell0_dict,
                'default': expected_default_dict
            },
            {
                '00000000-0000-0000-0000-000000000000': expected_cell0_dict,
                '541ca4e9-15f7-4178-95de-8af9e3659daf': expected_default_dict
            }
        )
        cell_dicts = parse_list_cells(test_output)
        self.assertEqual(expected_cell_dicts, cell_dicts)


class ReplaceDbNameCase(base.BaseTestCase):
    def test_replace_db_name(self):
        test_db_url = 'mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/nova?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo'
        expected_db_url = 'mysql+pymysql://nova:GsrvXnnW6Oam6Uz1CraPS46PV@overcloud.internalapi.redhat.local/foobar?read_default_file=/etc/my.cnf.d/tripleo.cnf&read_default_group=tripleo'
        db_url = replace_db_name(test_db_url, 'foobar')
        self.assertEqual(expected_db_url, db_url)
