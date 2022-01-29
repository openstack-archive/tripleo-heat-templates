#
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

import errno
import fixtures
import os
import shutil
import sys
import tempfile
import testtools

base = os.path.dirname(__file__)
pci_file = os.path.join(base, "../../deployment/neutron/")

sys.path.insert(0, pci_file)
import derive_pci_passthrough_whitelist as pci  # noqa: E402


class TestDerivePciPassthru(testtools.TestCase):

    def setUp(self):
        super(TestDerivePciPassthru, self).setUp()

        tmpdir = tempfile.mkdtemp()
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist._PCI_DEVICES_PATH', tmpdir))
        sys_class_tmpdir = tempfile.mkdtemp()
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist._SYS_CLASS_NET_PATH', sys_class_tmpdir))

    def tearDown(self):
        super(TestDerivePciPassthru, self).tearDown()
        shutil.rmtree(pci._PCI_DEVICES_PATH)
        shutil.rmtree(pci._SYS_CLASS_NET_PATH)

    def write_file(self, path, filename, data):
        path = os.path.join(path, filename)
        f = open(path, "w")
        f.write(data)
        f.close()

    def create_dirs(self, path):
        if os.path.isdir(path):
            return
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def sysfs_map_create(self, sysfs_map):
        for entry in sysfs_map:
            src = os.path.join(pci._PCI_DEVICES_PATH, entry['pci_addr'], 'net', entry['device'])
            dev = os.path.join(pci._SYS_CLASS_NET_PATH, entry['device'])
            self.create_dirs(src)
            os.symlink(src, dev)
            src = os.path.join(src, 'device')
            rel_pci_path = os.path.join("../../../", entry['pci_addr'])
            os.symlink(rel_pci_path, src)
            self.write_file(src, "device", entry['pf_prod'])
            self.write_file(src, "vendor", entry['vendor'])
            self.write_file(src, "sriov_totalvfs", entry['total_vfs'])
            self.write_file(src, "sriov_numvfs", str(entry['numvfs']))

            vf_id = 0
            for vf in entry['vf_addr']:
                vf_pci_path = os.path.join(pci._PCI_DEVICES_PATH, vf)
                vf_path = os.path.join(src, 'virtfn' + str(vf_id))
                self.create_dirs(vf_pci_path)
                os.symlink(vf_pci_path, vf_path)
                physfn_net_path = os.path.join(vf_path, "physfn/net")
                self.create_dirs(physfn_net_path)
                physfn_dev_path = os.path.join(physfn_net_path, entry['device'])
                os.symlink(dev, physfn_dev_path)
                self.write_file(vf_pci_path, "device", entry['vf_prod'])
                self.write_file(vf_pci_path, "vendor", entry['vendor'])
                vf_id = vf_id + 1

    def test_get_passthrough_prodID_with_sysfsmap(self):
        system_configs_nicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno2', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno2', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
                'min_tx_rate': 0, 'name': 'eno4v3', 'pci_address': '0000:18:0c.3', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        system_configs_nicpart2 = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno2', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno2', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno4v3', 'pci_address': '0000:18:0c.3', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno2', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno2", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0c.0", "0000:18:0c.1", "0000:18:0c.2", "0000:18:0c.3"]},
                {"device": "eno3", "pci_addr": "0000:18:00.3", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.4", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0d.0", "0000:18:0d.1", "0000:18:0d.2", "0000:18:0d.3"]}
                ]

        self.sysfs_map_create(sysfs_map)

        ''' Usecase: ProductID, with nicpart and non-nicpart PFs '''

        user_config1 = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, [])

        user_config_pfaddr = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config_pfaddr, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, user_config_pfaddr)

        user_config_pfaddr = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config_pfaddr, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, [])

        user_config_pfaddr = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'},
                              {'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]
        expected_output = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config_pfaddr, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, expected_output)

        user_config_pfaddr = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.4'},
                              {'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'}]
        expected_output = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.4'},
                           {'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config_pfaddr, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, expected_output)

        user_config_vfaddr = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.2'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config_vfaddr, system_configs_nicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertEqual(pci_passthro, user_config_vfaddr)

        user_config1 = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nicpart2)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.4'}])

    def test_get_passthrough_config_by_product_vf_with_sysfsmap(self):
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.3", "numvfs": 5, "total_vfs": "32", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0e.0", "0000:18:0e.1", "0000:18:0e.2", "0000:18:0e.3", "0000:18:0e.4"]}
                ]

        self.sysfs_map_create(sysfs_map)

        ''' Usecase: ProductID, with nicpart and non-nicpart VFs '''
        user_config1 = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true'}]
        expected_output1 = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.1'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.2'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.3'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]

        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output1)

        user_config2 = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'}]
        expected_output2 = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.1'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.2'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output2)

        user_config3 = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]
        expected_output3 = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config3, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output3)

        user_config4 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config4, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, user_config4)

        user_config5 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0.3'}]
        expected_output5 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config5, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output5)

        # Special case - VF_product_id, but PCI regex matches both PF and VF
        user_config6 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:*.*'}]
        expected_output6 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.1'},
                           {'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.2'},
                           {'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.3'},
                           {'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:00.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config6, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output6)

        user_config7 = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true'}]
        expected_output7 = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config7, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output7)

        user_config8 = [{'product_id': '1592', 'vendor_id': '8086', 'trusted': 'true'}]
        expected_output8 = [{'product_id': '1592', 'vendor_id': '8086', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config8, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output8)

        user_config9 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:*.*'},
                        {'product_id': '1592', 'vendor_id': '8086', 'trusted': 'true'}]
        expected_output9 = [{'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.1'},
                           {'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.2'},
                           {'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:0a.3'},
                           {'product_id': '154c', 'vendor_id': '8086', 'address': '0000:18:00.3'},
                           {'product_id': '1592', 'vendor_id': '8086', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config9, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_output9)

    def test_get_passthrough_config_by_address_sysfsmap(self):
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.3", "numvfs": 5, "total_vfs": "32", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0e.0", "0000:18:0e.1", "0000:18:0e.2", "0000:18:0e.3", "0000:18:0e.4"]}
                ]

        self.sysfs_map_create(sysfs_map)

        ''' Usecase: pci address of PF and physical network - nicpart PFs '''
        user_config1 = [{'address': '0000:18:00.2', 'physical_network': 'sriov1', 'trusted': 'true'}]
        expected_list1 = [{'address': '0000:18:0a.1', 'physical_network': 'sriov1', 'trusted': 'true'},
                           {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'},
                           {'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_list1)

        user_config2 = [{'address': '0000:18:00.3', 'physical_network': 'sriov2', 'trusted': 'true'}]
        expected_list2 = [{'address': '0000:18:00.3', 'physical_network': 'sriov2', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_list2)

        user_config2 = [{'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'}]
        expected_list2 = [{'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_list2)

        user_config3 = [{'address': '0000:18:0a.0', 'physical_network': 'sriov1', 'trusted': 'true'},
                        {'address': '0000:18:0a.1', 'physical_network': 'sriov1', 'trusted': 'true'}]
        expected_list3 = [{'address': '0000:18:0a.1', 'physical_network': 'sriov1', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config3, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_list3)

        user_config4 = [{'address': '0000:18:0a.0', 'physical_network': 'sriov1', 'trusted': 'true'}]
        expected_list4 = []
        non_nicp, nicp = pci.generate_combined_configuration(user_config4, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, expected_list4)

        user_config5 = [
            {"address": "0000:18:0a.2", "trusted": "true"},
            {"address": "0000:18:0e.3", "trusted": "true"}
        ]
        non_nicp, nicp = pci.generate_combined_configuration(user_config5, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, user_config5)

        user_config6 = [{'address': '0000:18:07.0', 'physical_network': 'sriov1', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config6, system_configs)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, user_config6)

    def test_get_pciwhitelist_dict_with_sysfsmap(self):
        system_configs_nicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno4', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno4v3', 'pci_address': '0000:18:0e.3', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.3", "numvfs": 5, "total_vfs": "32", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0e.0", "0000:18:0e.1", "0000:18:0e.2", "0000:18:0e.3", "0000:18:0e.4"]}
                ]

        self.sysfs_map_create(sysfs_map)

        ''' Usecases: PCI addr in DICT format (regex, range, etc. ), with nicpart and non-nicpart PFs in user config '''

        dict_usrcfg1 = [{"trusted": "true", "address": "0000:18:00.2"},
                        {"trusted": "true", "address": {"domain": "0000", "bus": "18", "slot": "00", "function": "3"}}]

        dict_output1 = [{"trusted": "true", "address": "0000:18:0a.1"},
                           {"trusted": "true", "address": "0000:18:0a.3"},
                           {"trusted": "true", "address": "0000:18:0e.0"},
                           {"trusted": "true", "address": "0000:18:0e.1"},
                           {"trusted": "true", "address": "0000:18:0e.2"},
                           {"trusted": "true", "address": "0000:18:0e.4"}
                          ]
        non_nicp, nicp = pci.generate_combined_configuration(dict_usrcfg1, system_configs_nicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, dict_output1)

        dict_output2 = [{"trusted": "true", "address": "0000:18:0a.0"},
                           {"trusted": "true", "address": "0000:18:0a.1"},
                           {"trusted": "true", "address": "0000:18:0a.3"},
                           {"trusted": "true", "address": {"domain": "0000", "bus": "18", "slot": "00", "function": "3"}}
                          ]
        non_nicp, nicp = pci.generate_combined_configuration(dict_usrcfg1, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, dict_output2)

        dict_usrcfg3 = [{"trusted": "true", "address": {"domain": "0000", "bus": "18", "slot": "00", "function": ".*"}},
                        {"trusted": "true", "address": {"domain": "0000", "bus": "18", "slot": ".*", "function": "3"}}]

        dict_output3 = [{"trusted": "true", "address": "0000:18:0a.1"},
                           {"trusted": "true", "address": "0000:18:0a.3"},
                           {"trusted": "true", "address": "0000:18:0e.0"},
                           {"trusted": "true", "address": "0000:18:0e.1"},
                           {"trusted": "true", "address": "0000:18:0e.2"},
                           {"trusted": "true", "address": "0000:18:0e.4"}
                           ]
        non_nicp, nicp = pci.generate_combined_configuration(dict_usrcfg3, system_configs_nicpart)
        pci_passthro = (non_nicp + nicp)
        for pf in pci_passthro:
            self.assertIn(pf, dict_output3)

        dict_usrcfg4 = [{"trusted": "true", "address": {"domain": "0000", "bus": "18", "slot": "0[0-a]", "function": "3"}}]
        dict_output4 = [{"trusted": "true", "address": "0000:18:00.3"},
                        {"trusted": "true", "address": "0000:18:0a.3"}]

        non_nicp, nicp = pci.generate_combined_configuration(dict_usrcfg4, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, dict_output4)

        dict_usrcfg5 = [{"trusted": "true", "address": {"domain": ".*", "bus": "18", "slot": "0[0-e]", "function": "2"}}]
        dict_output5 = [{"trusted": "true", "address": "0000:18:0a.0"},
                           {"trusted": "true", "address": "0000:18:0a.1"},
                           {"trusted": "true", "address": "0000:18:0a.3"},
                           {"trusted": "true", "address": "0000:18:0e.2"}
                          ]

        non_nicp, nicp = pci.generate_combined_configuration(dict_usrcfg5, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        for pf in pci_passthro:
            self.assertIn(pf, dict_output5)

    def test_get_passthrough_devname_with_sysfsmap(self):
        system_configs_nicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno4', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno4v3', 'pci_address': '0000:18:0e.3', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.3", "numvfs": 5, "total_vfs": "32", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0e.0", "0000:18:0e.1", "0000:18:0e.2", "0000:18:0e.3", "0000:18:0e.4"]}
                ]

        self.sysfs_map_create(sysfs_map)

        def get_pf_name_from_phy_network_stub(phy_net):
            if phy_net == 'sriov1':
                return 'eno3'
            elif phy_net == 'sriov2':
                return 'eno4'
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pf_name_from_phy_network', get_pf_name_from_phy_network_stub))

        ''' Usecase: Devname, with nicpart and non-nicpart PFs '''
        devname_usrcfg1 = [{"devname": "eno3", "physical_network": "sriov1", "trusted": "true"},
                           {"devname": "eno4", "physical_network": "sriov2", "trusted": "true"}]
        devname_output1 = [{"physical_network": "sriov1", "trusted": "true", "address": "0000:18:0a.1"},
                          {"physical_network": "sriov1", "trusted": "true", "address": "0000:18:0a.3"},
                          {"physical_network": "sriov2", "trusted": "true", "address": "0000:18:0e.0"},
                          {"physical_network": "sriov2", "trusted": "true", "address": "0000:18:0e.1"},
                          {"physical_network": "sriov2", "trusted": "true", "address": "0000:18:0e.2"},
                          {"physical_network": "sriov2", "trusted": "true", "address": "0000:18:0e.4"}
                         ]

        non_nicp, nicp = pci.generate_combined_configuration(devname_usrcfg1, system_configs_nicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, devname_output1)

        devname_usrcfg2 = [{"devname": "eno3", "physical_network": "sriov1", "trusted": "true"},
                           {"devname": "eno4", "physical_network": "sriov2", "trusted": "true"}]
        devname_output2 = [{"physical_network": "sriov1", "trusted": "true", "address": "0000:18:0a.1"},
                          {"physical_network": "sriov1", "trusted": "true", "address": "0000:18:0a.3"},
                          {"physical_network": "sriov1", "trusted": "true", "address": "0000:18:0a.0"},
                          {"devname": "eno4", "physical_network": "sriov2", "trusted": "true"}]

        non_nicp, nicp = pci.generate_combined_configuration(devname_usrcfg2, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, devname_output2)

        user_config3 = [
            {"address": "0000:18:0a.1", "trusted": "true"},
            {"address": "0000:18:0e.1", "trusted": "true"}
        ]
        user_output3 = [{"trusted": "true", "address": "0000:18:0a.1"},
                        {"trusted": "true", "address": "0000:18:0e.1"}]

        non_nicp, nicp = pci.generate_combined_configuration(user_config3, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, user_output3)

        devname_usrcfg4 = [{"devname": "eno3", "physical_network": "sriov1", "trusted": "true", "product_id": "1572"},
                {"devname": "eno4", "physical_network": "sriov2", "trusted": "true", "product_id": "1572"}]
        devname_output4 = [{"devname": "eno4", "physical_network": "sriov2", "trusted": "true", "product_id": "1572"}]
        non_nicp, nicp = pci.generate_combined_configuration(devname_usrcfg4, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, devname_output4)

        devname_usrcfg5 = [{"devname": "eno7", "physical_network": "sriov1", "trusted": "true", "product_id": "1572"},
                {"devname": "eno4", "physical_network": "sriov2", "trusted": "true", "product_id": "1572"}]
        devname_output5 = [{"devname": "eno7", "physical_network": "sriov1", "trusted": "true", "product_id": "1572"},
                {"devname": "eno4", "physical_network": "sriov2", "trusted": "true", "product_id": "1572"}]
        non_nicp, nicp = pci.generate_combined_configuration(devname_usrcfg5, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, devname_output5)

        devname_usrcfg6 = [{"devname": "eno3", "physical_network": "sriov1", "trusted": "true", "product_id": "1572"},
                {"devname": "eno4", "physical_network": "sriov2", "trusted": "true", "product_id": "1572"}]
        devname_output6 = []
        non_nicp, nicp = pci.generate_combined_configuration(devname_usrcfg6, system_configs_nicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, devname_output6)

        devname_usrcfg7 = [{"devname": "eno3", "physical_network": "sriov1", "trusted": "true", "product_id": "1572", "address": "0000:12:00.1"}]
        self.assertRaises(pci.InvalidConfigException, pci.generate_combined_configuration, devname_usrcfg7, system_configs_nicpart)

        devname_usrcfg8 = [{"devname": "eno4", "physical_network": "sriov1", "trusted": "true", "product_id": "1572", "address": "0000:12:00.1"}]
        self.assertRaises(pci.InvalidConfigException, pci.generate_combined_configuration, devname_usrcfg8, system_configs_nonnicpart)

    def test_get_passthrough_config_nonmatch_usrcfgs(self):
        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        system_configs_nicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 5, 'promisc': 'on'},
            {'device': {'name': 'eno4', 'vfid': 5}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno4v5', 'pci_address': '0000:18:0e.5', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.2", "numvfs": "8", "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3", "0000:18:0a.4", "0000:18:0a.5", "0000:18:0a.6", "0000:18:0a.7"]},
                {"device": "eno4", "pci_addr": "0000:18:00.3", "numvfs": "6", "total_vfs": "32", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0e.0", "0000:18:0e.1", "0000:18:0e.2", "0000:18:0e.3", "0000:18:0e.4", "0000:18:0e.5"]}
                ]
        self.sysfs_map_create(sysfs_map)

        ''' Usecase: Non-matching PCI-addr and ProductID, with nicpart and non-nicpart VFs '''

        user_config1 = [{'product_id': '134f', 'vendor_id': '8086', 'trusted': 'true'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nicpart)
        pci_passthrough = (non_nicp + nicp)
        self.assertEqual(pci_passthrough, user_config1)
        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nonnicpart)
        pci_passthrough = (non_nicp + nicp)
        self.assertEqual(pci_passthrough, user_config1)

        user_config2 = [{'product_id': '134f', 'vendor_id': '8086', 'address': '4440:22:1f.1', 'trusted': 'true'},
                        {"trusted": "true", "address": {"domain": "3000", "bus": "08", "slot": "05", "function": "3"}}
                       ]
        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs_nicpart)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, user_config2)
        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs_nonnicpart)
        pci_passthrough = (non_nicp + nicp)
        self.assertCountEqual(pci_passthrough, user_config2)

        user_config3 = [{'product_id': '', 'vendor_id': '8086', 'trusted': 'true'},
                        {"trusted": "true", "address": {"domain": "3000", "bus": "ff", "slot": "05", "function": "3"}}
                       ]
        non_nicp, nicp = pci.generate_combined_configuration(user_config3, system_configs_nicpart)
        pci_passthrough = (non_nicp + nicp)
        self.assertEqual(pci_passthrough, user_config3)

    def test_generate_combined_configuration_pass1(self):
        user_configs = [
            {
                "physical_network": "sriov1",
                "devname": "eno3",
                "trusted": "true"
            }
        ]
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        def get_pf_name_from_phy_network_stub(phy_net):
            return 'eno3'
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pf_name_from_phy_network', get_pf_name_from_phy_network_stub))

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "16", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]}
                ]

        self.sysfs_map_create(sysfs_map)

        result1, result2 = pci.generate_combined_configuration(user_configs, system_configs)
        expected2 = [
                        {'address': '0000:18:0a.1', 'physical_network': 'sriov1', 'trusted': 'true'},
                        {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'},
                        {'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'}
                    ]
        self.assertCountEqual(result2, expected2)

    def test_get_allocated_pci_addresses_pass1(self):
        configs = [
            {
                "device_type": "pf",
                "link_mode": "legacy",
                "name": "eno3",
                "numvfs": 5
            },
            {
                "device_type": "vf",
                "pci_address": "0000:00:01.1"
            }
        ]
        result = pci.get_allocated_pci_addresses(configs)
        expected = ["0000:00:01.1"]
        self.assertEqual(result, expected)

    def test_get_pci_regex_pattern_pass1(self):
        config_regex = '.*'

        result = pci.get_pci_regex_pattern(config_regex, 4, pci.MAX_DOMAIN, '%04x')
        expected = '[0-9a-fA-F]{4}'
        self.assertEqual(result, expected)

    def test_get_pci_regex_pattern_pass2(self):
        config_regex = ['18', '[0-1]', 'aA', '00']
        config_expected = {"18": "18", "[0-1]": "[0-1]", "aA": "aa", "00": "00"}

        for config in config_regex:
            result = pci.get_pci_regex_pattern(config, 2, 0xFF, '%02x')
            self.assertEqual(result, config_expected[config])

    def test_get_sriov_nic_partition_pfs_pass1(self):
        configs = [
            {
                "device": {"name": "eno3"},
                "device_type": "vf",
                "name": "eno3v0",
                "pci_address": "0000:18:0a.0",
                "trust": "on"
            }
        ]
        result = pci.get_sriov_nic_partition_pfs(configs)
        expected = ["eno3"]
        self.assertEqual(result, expected)

    def test_get_sriov_nic_partition_pfs_pass2(self):
        configs = [
            {
                "link_mode": "legacy",
                "device_type": "pf",
                "name": "eno4",
                "pci_address": "0000:18:00.3",
                "trust": "on"
            }
        ]
        result = pci.get_sriov_nic_partition_pfs(configs)
        expected = []
        self.assertEqual(result, expected)

    def test_get_sriov_non_nic_partition_pfs_pass1(self):
        configs = [
            {
                "device": {"name": "eno3"},
                "device_type": "vf",
                "name": "eno3v0",
                "pci_address": "0000:18:0a.0",
                "trust": "on"
            },
            {
                "link_mode": "legacy",
                "device_type": "pf",
                "name": "eno4",
                "pci_address": "0000:18:00.3",
                "trust": "on"
            }
        ]
        result = pci.get_sriov_non_nic_partition_pfs(configs)
        expected = ["eno4"]
        self.assertEqual(result, expected)

    def test_get_pci_addresses_by_ifname_pass1(self):
        pfs = ['eno3']
        allocated_pci = ['0000:18:0a.0']
        os.makedirs(pci._PCI_DEVICES_PATH + "/0000:18:0a.1/physfn/net/eno3")
        os.makedirs(pci._PCI_DEVICES_PATH + "/0000:18:0a.2/physfn/net/eno3")

        f = open(pci._PCI_DEVICES_PATH + "/0000:18:0a.1/vendor",
                 "w+")
        f.write("0x8086")
        f.close()
        f = open(pci._PCI_DEVICES_PATH + "/0000:18:0a.1/device",
                 "w+")
        f.write("0x154c")
        f.close()

        f = open(pci._PCI_DEVICES_PATH + "/0000:18:0a.2/vendor",
                 "w+")
        f.write("0x8086")
        f.close()
        f = open(pci._PCI_DEVICES_PATH + "/0000:18:0a.2/device",
                 "w+")
        f.write("0x154c")
        f.close()
        pci_addresses = pci.get_available_vf_pci_addresses_by_ifname(pfs, allocated_pci)
        expected_pci_addresses = {'eno3': ['0000:18:0a.2', '0000:18:0a.1']}
        for pf in expected_pci_addresses.keys():
            for addr in expected_pci_addresses[pf]:
                self.assertIn(addr, pci_addresses[pf])

    def test_get_passthrough_config_pass1(self):
        user_config = {'devname': 'eno3', 'physical_network': 'sriov1', 'trusted': 'true'}
        pf = 'eno3'
        allocated_pci = ['0000:18:0a.0']

        def get_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_pci_addresses_by_ifname_stub))

        def get_pci_device_info_by_ifname_stub1(pf_path, subdir):
            if subdir == 'virtfn0':
                vendor = '8086'
                product = '154c'
                return vendor, product
            else:
                vendor = '8086'
                product = '1572'
                return vendor, product
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub1))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno2'):
                addr = '0000:18:00.1'
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        pci_passthro, stats = pci.get_passthrough_config(user_config, pf, allocated_pci, False)
        expected_pci_passthro = [
                                   {'address': '0000:18:0a.1', 'physical_network': 'sriov1', 'trusted': 'true'},
                                   {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}
                                ]
        self.assertCountEqual(pci_passthro, expected_pci_passthro)

    def test_get_pci_passthrough_whitelist_pass1(self):
        user_config = {'devname': 'eno3', 'physical_network': 'sriov1', 'trusted': 'true'}
        pf = 'eno3'
        pci_addresses = ['0000:18:0a.3', '0000:18:0a.1', '0000:18:0a.2']

        pci_whitelist_list = pci.get_pci_passthrough_whitelist(user_config, pf, pci_addresses)
        expected_pci_whitelist_list = [
               {'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'},
               {'address': '0000:18:0a.1', 'physical_network': 'sriov1', 'trusted': 'true'},
               {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}
           ]
        self.assertEqual(len(pci_whitelist_list), len(expected_pci_whitelist_list))
        for addr in pci_whitelist_list:
            self.assertIn(addr, expected_pci_whitelist_list)

    def test_get_pciaddr_dict_from_usraddr_pass(self):
        pci_addr_1 = "000a:0b:f.5"
        pci_addr_2 = "000a:*:f.7"
        pci_addr_3 = "0000:03:*.7"
        pci_addr_4 = "000c:03:f.*"
        pci_addr_5 = ":5.7"
        pci_addr_6 = ":00"
        pci_addr_7 = ":5:00"
        pci_addr_8 = "*:0A:*.7"
        pci_addr_9 = "*:0A:2*.7"
        addr_0 = {"domain": ".*", "bus": "1f", "slot": "02", "function": "7"}
        addr_1 = {"domain": ".*", "bus": "0[a-b]", "slot": "0[2-9]", "function": "7"}
        addr_2 = {"domain": "[", "bus": "0a[", "slot": "0[2-9]", "function": "7"}
        addr_3 = {"domain": "*", "bus": "0a", "slot": "0[2-9]", "function": "5"}
        addr_4 = {"domain": "*", "bus": "0", "slot": "0", "function": "5"}
        addr_5 = {"domain": "*", "bus": "08", "slot": "33", "function": "5"}
        addr_6 = {"domain": "*", "bus": "08", "slot": "12", "function": "9"}
        addr_7 = {"domain": "*", "bus": "08", "slot": "2*", "function": "1"}
        addr_8 = {"domain": "*", "bus": "08", "slot": "1dd", "function": "1"}

        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_1)
        self.assertEqual({'function': '5', 'domain': '000a', 'bus': '0b', 'slot': '0f'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_2)
        self.assertEqual({'function': '7', 'domain': '000a', 'bus': '.*', 'slot': '0f'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_3)
        self.assertEqual({'function': '7', 'domain': '0000', 'bus': '03', 'slot': '.*'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_4)
        self.assertEqual({'function': '.*', 'domain': '000c', 'bus': '03', 'slot': '0f'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_5)
        self.assertEqual({'function': '7', 'domain': '.*', 'bus': '.*', 'slot': '05'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_6)
        self.assertEqual({'function': '.*', 'domain': '.*', 'bus': '.*', 'slot': '00'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_7)
        self.assertEqual({'function': '.*', 'domain': '.*', 'bus': '05', 'slot': '00'}, result)
        result = pci.get_pciaddr_dict_from_usraddr(pci_addr_8)
        self.assertRaises(pci.InvalidConfigException, pci.get_pciaddr_dict_from_usraddr, pci_addr_9)

        self.assertEqual({'function': '7', 'domain': '.*', 'bus': '0a', 'slot': '.*'}, result)
        result = pci.get_user_regex_from_addrdict(addr_0)
        self.assertEqual(result, '[0-9a-fA-F]{4}:1f:02.7')
        result = pci.get_user_regex_from_addrdict(addr_1)
        self.assertEqual(result, '[0-9a-fA-F]{4}:0[a-b]:0[2-9].7')
        self.assertRaises(pci.InvalidConfigException, pci.get_user_regex_from_addrdict, addr_2)
        result = pci.get_user_regex_from_addrdict(addr_3)
        self.assertEqual(result, '[0-9a-fA-F]{4}:0a:0[2-9].5')
        result = pci.get_user_regex_from_addrdict(addr_4)
        self.assertEqual(result, '[0-9a-fA-F]{4}:00:00.5')
        self.assertRaises(pci.InvalidConfigException, pci.get_user_regex_from_addrdict, addr_5)
        self.assertRaises(pci.InvalidConfigException, pci.get_user_regex_from_addrdict, addr_6)
        result = pci.get_user_regex_from_addrdict(addr_7)
        self.assertEqual(result, '[0-9a-fA-F]{4}:08:2*.1')
        self.assertRaises(pci.InvalidConfigException, pci.get_user_regex_from_addrdict, addr_8)

    def test_get_passthrough_config_pciformat_basic1(self):
        user_config1 = {'address': '0000:18:00.2', 'product_id': '154c', 'physical_network': 'sriov1', 'trusted': 'true'}

        allocated_pci = ['0000:18:0a.0']

        def get_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_pci_addresses_by_ifname_stub))

        def get_pci_device_info_by_ifname_stub1(pf_path, subdir):
            if subdir == 'virtfn0':
                vendor = '8086'
                product = '154c'
                return vendor, product
            else:
                vendor = '8086'
                product = '1572'
                return vendor, product
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub1))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno2'):
                addr = '0000:18:00.1'
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        expected_1 = [{'address': '0000:18:0a.1', 'product_id': '154c', 'physical_network': 'sriov1', 'trusted': 'true'},
                      {'address': '0000:18:0a.2', 'product_id': '154c', 'physical_network': 'sriov1', 'trusted': 'true'}]
        pci_passthro, parse_non_nic_pfs = pci.get_passthrough_config(user_config1, 'eno3', allocated_pci, False)
        self.assertEqual(len(pci_passthro), len(expected_1))
        for config in pci_passthro:
            self.assertIn(config, expected_1)

    def test_get_passthrough_config_pciformat_basic2(self):
        user_config2 = {'address': '0000:18:00.3', 'physical_network': 'sriov2', 'trusted': 'true'}
        allocated_pci = ['0000:18:0a.0']

        def get_available_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_available_pci_addresses_by_ifname_stub))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno2'):
                addr = '0000:18:00.1'
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        def get_pci_device_info_by_ifname_stub(pf_path, subdir):
            vendor = '8086'
            product = '154c'
            return str(vendor), str(product)
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub))

        pci_passthro, parse_non_nic_p = pci.get_passthrough_config(user_config2, 'eno3', allocated_pci, False)
        self.assertEqual(pci_passthro, [])

    def test_get_passthrough_config_pciformat_basic3(self):
        user_config3 = {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}
        allocated_pci = ['0000:18:0a.0']

        def get_available_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_available_pci_addresses_by_ifname_stub))

        def get_pci_device_info_by_ifname_stub(pf_path, subdir):
            vendor = '8086'
            product = '154c'
            return str(vendor), str(product)
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub))

        def get_addr_from_ifname_stub(str):
            addr = '0000:18:00.2'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        pci_passthro, parse_non_nic_p = pci.get_passthrough_config(user_config3, 'eno3', allocated_pci, False)
        self.assertEqual(pci_passthro, [{'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}])

    def test_get_passthrough_config_by_address_pciaddr_notsingle(self):
        user_config = {'address': '0000:18:*.*', 'physical_network': 'sriov1', 'trusted': 'true'}
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        allocated_pci = ['0000:18:0a.0']

        def get_available_vf_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.3', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_available_vf_pci_addresses_by_ifname_stub))

        def get_pci_addr_from_ifname_stub(str):
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_pci_addr_from_ifname_stub))

        def get_pci_device_info_by_ifname_stub(pf_path, subdir):
            vendor = '8086'
            product = '154c'
            return str(vendor), str(product)
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub))

        pci_passthro, stats = pci.get_passthrough_config_for_all_pf(user_config, system_configs, allocated_pci)
        expected_pci_passthro = [
                                   {'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'},
                                   {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}
                                ]
        self.assertCountEqual(pci_passthro, expected_pci_passthro)

    def test_get_passthrough_config_by_address_pciaddr_mix_notsingle(self):
        user_config = {'address': '0000:18:*.3', 'physical_network': 'sriov1', 'trusted': 'true'}
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        allocated_pci = ['0000:18:0a.2']

        def get_available_vf_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.3', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_available_vf_pci_addresses_by_ifname_stub))

        def get_pci_device_info_by_ifname_stub1(pf_path, subdir):
            if subdir == 'virtfn0':
                vendor = '8086'
                product = '154c'
                return vendor, product
            else:
                vendor = '8086'
                product = '1572'
                return vendor, product
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub1))

        def get_pci_addr_from_ifname_stub(str):
            return '0000:18:00.2'
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_pci_addr_from_ifname_stub))

        pci_passthro, stats = pci.get_passthrough_config_for_all_pf(user_config, system_configs, allocated_pci)
        expected_pci_passthro = [
                                   {'address': '0000:18:0a.3', 'physical_network': 'sriov1', 'trusted': 'true'}
                                ]

        self.assertCountEqual(pci_passthro, expected_pci_passthro)

    def test_get_passthrough_config_by_address_pciaddr_single(self):
        user_config1 = {'address': '0000:18:0.3', 'physical_network': 'sriov2', 'trusted': 'true'}
        user_config2 = {'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        allocated_pci = ['0000:18:0a.0']

        def get_available_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_available_pci_addresses_by_ifname_stub))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        def get_pci_device_info_by_ifname_stub1(pf_path, subdir):
            if subdir == 'virtfn0':
                vendor = '8086'
                product = '154c'
                return vendor, product
            else:
                vendor = '8086'
                product = '1572'
                return vendor, product
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub1))

        pci_passthro, stats = pci.get_passthrough_config_for_all_pf(user_config1, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, [])
        pci_passthro, stats = pci.get_passthrough_config_for_all_pf(user_config2, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, [{'address': '0000:18:0a.2', 'physical_network': 'sriov1', 'trusted': 'true'}])

    def test_get_passthrough_config_by_pciaddr_wildcard_1(self):
        user_config1 = {'address': '0000:18:0a.*', 'trusted': 'true'}
        user_config2 = {'address': '0000:18:00.*', 'trusted': 'true'}
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        allocated_pci = ['0000:18:0a.0']

        def get_available_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2', '0000:18:0a.3']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_available_pci_addresses_by_ifname_stub))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        def get_pci_device_info_by_ifname_stub(pf_path, subdir):
            vendor = '8086'
            product = '154c'
            return str(vendor), str(product)
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub))

        expected_list1 = [{'address': '0000:18:0a.2', 'trusted': 'true'}, {'address': '0000:18:0a.1', 'trusted': 'true'}, {'address': '0000:18:0a.3', 'trusted': 'true'}]
        pci_passthro, stats = pci.get_passthrough_config_for_all_pf(user_config1, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected_list1)
        pci_passthro, stats = pci.get_passthrough_config_for_all_pf(user_config2, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected_list1)

    def test_get_passthrough_config_by_product_vf(self):
        user_config1 = {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true'}
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        allocated_pci = ['0000:18:0a.0']

        def get_sriov_nic_partition_pfs_stub(sys_cfg):
            return ['eno3']
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_sriov_nic_partition_pfs', get_sriov_nic_partition_pfs_stub))

        def get_pci_device_info_by_ifname_stub1(pf_path, subdir):
            if subdir == 'virtfn0':
                vendor = '8086'
                product = '154c'
                return vendor, product
            else:
                vendor = '8086'
                product = '1572'
                return vendor, product
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub1))

        def get_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': ['0000:18:0a.1', '0000:18:0a.2', '0000:18:0a.3']}
            return pci_addresses
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_pci_addresses_by_ifname_stub))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno2'):
                addr = '0000:18:00.1'
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        expected_list = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.3'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.1'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.2'}]
        pci_passthro, status = pci.get_passthrough_config_for_all_pf(user_config1, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected_list)

    def test_get_passthrough_config_by_product_pf(self):
        system_configs = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno2', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno2', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno2v3', 'pci_address': '0000:18:0c.3', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'}
        ]
        allocated_pci = ['0000:18:0a.0', '0000:18:0a.2', '0000:18:0c.3']

        def get_sriov_nic_partition_pfs_stub1(sys_cfg):
            return ['eno2', 'eno3']
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_sriov_nic_partition_pfs', get_sriov_nic_partition_pfs_stub1))

        def get_pci_device_info_by_ifname_stub1(pf_path, subdir):
            if subdir == 'virtfn0':
                vendor = '8086'
                product = '154c'
                return vendor, product
            else:
                vendor = '8086'
                product = '1572'
                return vendor, product
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_device_info_by_ifname', get_pci_device_info_by_ifname_stub1))

        def get_pci_addresses_by_ifname_stub(ifname, allocated_pci):
            pci_addresses = {'eno3': {'eno3': ['0000:18:0a.1', '0000:18:0a.3']},
                    'eno2': {'eno2': ['0000:18:0c.0', '0000:18:0c.1', '0000:18:0c.2']},
                    'eno4': {'eno4': ['0000:18:0e.0', '0000:18:0e.1', '0000:18:0e.2', '0000:18:0e.3']}}
            return pci_addresses[ifname]
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_available_vf_pci_addresses_by_ifname', get_pci_addresses_by_ifname_stub))

        def get_addr_from_ifname_stub(str):
            if (str == 'eno2'):
                addr = '0000:18:00.1'
            if (str == 'eno3'):
                addr = '0000:18:00.2'
            if (str == 'eno4'):
                addr = '0000:18:00.3'
            return addr
        self.useFixture(fixtures.MonkeyPatch('derive_pci_passthrough_whitelist.get_pci_addr_from_ifname', get_addr_from_ifname_stub))

        user_config1 = {'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true'}
        user_config2 = {'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}
        user_config3 = {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}
        user_config4 = {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.2'}
        expected1_list = [{'product_id': '1572', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:00.3'}]

        # No need to override the default configuration and hence, empty list is expected
        expected2_list = []
        expected3_list = []
        expected4_list = [{'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.1'},
                          {'product_id': '154c', 'vendor_id': '8086', 'trusted': 'true', 'address': '0000:18:0a.3'}]
        pci_passthro, status = pci.get_passthrough_config_for_all_pf(user_config1, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected1_list)
        pci_passthro, status = pci.get_passthrough_config_for_all_pf(user_config2, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected2_list)
        pci_passthro, status = pci.get_passthrough_config_for_all_pf(user_config3, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected3_list)
        pci_passthro, status = pci.get_passthrough_config_for_all_pf(user_config4, system_configs, allocated_pci)
        self.assertCountEqual(pci_passthro, expected4_list)

    def test_get_passthrough_multiple_vendor_sysfsmap(self):
        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno1', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno2', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v3', 'pci_address': '0000:18:0a.3', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno2', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno2v3', 'pci_address': '0000:08:0c.3', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno1", "pci_addr": "0000:18:00.1", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1016", "vendor": "0x15b3", "vf_prod": "0x1013", "vf_addr": ["0000:08:09.0", "0000:08:09.1", "0000:08:09.2", "0000:08:09.3"]},
                {"device": "eno2", "pci_addr": "0000:18:00.2", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1016", "vendor": "0x15b3", "vf_prod": "0x1013", "vf_addr": ["0000:08:0c.0", "0000:08:0c.1", "0000:08:0c.2", "0000:08:0c.3"]},
                {"device": "eno3", "pci_addr": "0000:18:00.3", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.4", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0d.0", "0000:18:0d.1", "0000:18:0d.2", "0000:18:0d.3"]}
                ]

        self.sysfs_map_create(sysfs_map)

        ''' Usecase: ProductID and VendorID, with mixed vendor NICs in sysfs_map  '''
        user_config1 = [{'product_id': '1016', 'vendor_id': '15b3', 'trusted': 'true'}]
        user_config2 = [{'product_id': '1572', 'vendor_id': '15b3', 'trusted': 'true', 'address': '0000:18:00.3'}]
        user_config3 = [{'product_id': '1013', 'trusted': 'true', 'address': '0000:08:0c.*'}]

        expected1_list = [{'product_id': '1016', 'vendor_id': '15b3', 'trusted': 'true', 'address': '0000:18:00.1'}]
        expected3_list = [{'product_id': '1013', 'trusted': 'true', 'address': '0000:08:0c.0'},
                           {'product_id': '1013', 'trusted': 'true', 'address': '0000:08:0c.1'},
                           {'product_id': '1013', 'trusted': 'true', 'address': '0000:08:0c.2'}]

        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, expected1_list)

        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertEqual(pci_passthro, [])

        non_nicp, nicp = pci.generate_combined_configuration(user_config3, system_configs_nonnicpart)
        pci_passthro = (non_nicp + nicp)
        self.assertCountEqual(pci_passthro, expected3_list)

    def test_get_passthrough_allVFsused(self):
        '''Usecase: Corner case where all VFs of device is used'''
        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 4, 'promisc': 'on'},
            {'device': {'name': 'eno3', 'vfid': 0}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v0', 'pci_address': '0000:18:0a.0', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 1}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v1', 'pci_address': '0000:18:0a.1', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 2}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v2', 'pci_address': '0000:18:0a.2', 'spoofcheck': 'off', 'trust': 'on'},
            {'device': {'name': 'eno3', 'vfid': 3}, 'device_type': 'vf', 'max_tx_rate': 0,
              'min_tx_rate': 0, 'name': 'eno3v3', 'pci_address': '0000:18:0a.3', 'spoofcheck': 'off', 'trust': 'on'}
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.3", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.4", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0d.0", "0000:18:0d.1", "0000:18:0d.2", "0000:18:0d.3"]}
                ]
        self.sysfs_map_create(sysfs_map)

        user_config1 = [{'trusted': 'true', 'address': '0000:18:00.*'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nonnicpart)
        self.assertEqual(nicp, [{'trusted': 'true', 'address': '0000:18:00.4'}])
        self.assertEqual(non_nicp, [])

        user_config2 = [{'trusted': 'true', 'product_id': '0x1572'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config2, system_configs_nonnicpart)
        self.assertEqual(nicp, [{'trusted': 'true', 'product_id': '0x1572', 'address': '0000:18:00.4'}])
        self.assertEqual(non_nicp, [])

        user_config3 = [{'trusted': 'true', 'product_id': '0x154c'}]
        non_nicp, nicp = pci.generate_combined_configuration(user_config3, system_configs_nonnicpart)
        self.assertEqual(nicp, [{'trusted': 'true', 'product_id': '0x154c', 'address': '0000:18:00.4'}])
        self.assertEqual(non_nicp, [])

    def test_get_passthrough_err_devandaddr(self):
        '''Usecase: Corner case where all VFs of device is used'''
        system_configs_nonnicpart = [
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno3', 'numvfs': 4, 'promisc': 'on'},
            {'device_type': 'pf', 'link_mode': 'legacy', 'name': 'eno4', 'numvfs': 4, 'promisc': 'on'},
        ]

        sysfs_map = [
                {"device": "eno3", "pci_addr": "0000:18:00.3", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0a.0", "0000:18:0a.1", "0000:18:0a.2", "0000:18:0a.3"]},
                {"device": "eno4", "pci_addr": "0000:18:00.4", "numvfs": 4, "total_vfs": "64", "pf_prod": "0x1572", "vendor": "0x8086", "vf_prod": "0x154c", "vf_addr": ["0000:18:0d.0", "0000:18:0d.1", "0000:18:0d.2", "0000:18:0d.3"]}
                ]
        self.sysfs_map_create(sysfs_map)

        user_config1 = [{'trusted': 'true', 'address': '0000:18:00.*', 'devname': 'eno3'}]
        try:
            non_nicp, nicp = pci.generate_combined_configuration(user_config1, system_configs_nonnicpart)
        except pci.InvalidConfigException:
            pass
