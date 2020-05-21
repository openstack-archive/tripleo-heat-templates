#!/usr/bin/env python

#
# Copyright 2019 Red Hat Inc.
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

import json
import os
import re
import yaml

from oslo_concurrency import processutils


_PASSTHROUGH_WHITELIST_KEY = 'nova::compute::pci::passthrough'
_PCI_DEVICES_PATH = '/sys/bus/pci/devices'
_SYS_CLASS_NET_PATH = '/sys/class/net'


def get_sriov_configs():
    configs = []
    try:
        with open('/var/lib/os-net-config/sriov_config.yaml') as sriov_config:
            configs = yaml.safe_load(sriov_config)
    except IOError:
        configs = []
    return configs


def get_sriov_nic_partition_pfs(configs):
    pfs = []
    for config in configs:
        device_type = config.get('device_type', None)
        if device_type and 'vf' in device_type:
            device = config.get('device', None)
            if device:
                dev_name = device.get('name', None)
                if dev_name and dev_name not in pfs:
                    pfs.append(dev_name)
    return pfs


def get_sriov_non_nic_partition_pfs(configs):
    all_pfs = []
    non_nicp_pfs = []
    nicp_pfs = get_sriov_nic_partition_pfs(configs)

    for config in configs:
        device_type = config.get('device_type', None)
        if device_type and 'pf' in device_type:
            name = config.get('name', None)
            if name and name not in all_pfs:
                all_pfs.append(name)
    non_nicp_pfs = [x for x in all_pfs if x not in nicp_pfs]
    return non_nicp_pfs


def get_pci_device_info_by_ifname(pci_dir, sub_dir):
    if not os.path.isdir(os.path.join(pci_dir, sub_dir)):
        return None
    try:
        # ids located in files inside PCI devices
        # directory are stored in hex format (0x1234 for example)
        with open(os.path.join(pci_dir, sub_dir,
                               'vendor')) as vendor_file:
            vendor = vendor_file.read().strip()
        with open(os.path.join(pci_dir, sub_dir,
                               'device')) as product_file:
            product = product_file.read().strip()
        return (vendor, product)
    except IOError:
        return None


def get_pci_addresses_by_ifname(pfs, allocated_pci):
    pci_addresses = {}
    device_info = {}
    pci_dir = _PCI_DEVICES_PATH
    if os.path.isdir(pci_dir):
        for sub_dir in os.listdir(pci_dir):
            if sub_dir in allocated_pci:
                continue
            pci_phyfn_dir = os.path.join(pci_dir, sub_dir, 'physfn/net')
            if os.path.isdir(pci_phyfn_dir):
                phyfn_dirs = os.listdir(pci_phyfn_dir)
                for phyfn in phyfn_dirs:
                    if phyfn in pfs:
                        if phyfn not in pci_addresses:
                            pci_addresses[phyfn] = [sub_dir]
                        else:
                            pci_addresses[phyfn].append(sub_dir)
                        if phyfn not in device_info:
                            dev_info = get_pci_device_info_by_ifname(pci_dir,
                                                                     sub_dir)
                            if dev_info:
                                device_info[phyfn] = dev_info
    return (pci_addresses, device_info)


def get_allocated_pci_addresses(configs):
    alloc_pci_info = []
    for config in configs:
        pci = config.get('pci_address', None)
        if pci:
            alloc_pci_info.append(pci)
    return alloc_pci_info


def get_pci_passthrough_whitelist(user_config, pf, pci_addresses,
                                  device_info):
    pci_passthrough_list = []

    for pci in pci_addresses:
        pci_passthrough = {}
        address = {}
        pci_params = re.split('[:.]+', pci)
        address['domain'] = '.*'
        address['bus'] = pci_params[1]
        address['slot'] = pci_params[2]
        address['function'] = pci_params[3]
        pci_passthrough['address'] = address
        pci_passthrough['vendor_id'] = device_info[pf][0]
        pci_passthrough['product_id'] = device_info[pf][1]
        if 'trusted' in user_config:
            pci_passthrough['trusted'] = user_config['trusted']
        pci_passthrough_list.append(pci_passthrough)
    return pci_passthrough_list


def user_passthrough_config():
    try:
        out, err = processutils.execute(
            'hiera', '-c', '/etc/puppet/hiera.yaml',
            _PASSTHROUGH_WHITELIST_KEY
            )
        if not err:
            return json.loads(out)
    except processutils.ProcessExecutionError:
        raise


def get_regex_pattern(config_regex, size):
    if config_regex == ".*":
        regex_pattern = "[0-9a-fA-F]{%d}" % size
    else:
        regex_pattern = config_regex
    return regex_pattern


def get_passthrough_config(user_config, pf, allocated_pci):
    sel_addr = []
    if 'address' in user_config:
        addr_dict = user_config['address']
        user_address_pattern = "%s:%s:%s.%s" % (
            get_regex_pattern(addr_dict['domain'], 4),
            get_regex_pattern(addr_dict['bus'], 2),
            get_regex_pattern(addr_dict['slot'], 2),
            addr_dict['function'])
    else:
        user_address_pattern = ("[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:"
                                "[0-9a-fA-F]{2}.[0-7]")
    pci_addresses, dev_info = get_pci_addresses_by_ifname(pf, allocated_pci)
    for pci_addr in pci_addresses[pf]:
        user_address_regex = re.compile(user_address_pattern)
        if user_address_regex.match(pci_addr):
            sel_addr.append(pci_addr)
    pci_passthrough = get_pci_passthrough_whitelist(
        user_config, pf, sel_addr, dev_info)

    return pci_passthrough


def get_passthrough_config_by_address(user_config,
                                      system_configs,
                                      allocated_pci):
    nic_part_config = []
    non_nic_part_config = []
    nic_partition_pfs = get_sriov_nic_partition_pfs(system_configs)
    non_nic_partition_pfs = get_sriov_non_nic_partition_pfs(system_configs)
    for pf in nic_partition_pfs:
        passthrough_tmp = get_passthrough_config(
            user_config, pf, allocated_pci)
        nic_part_config.extend(passthrough_tmp)

    if len(nic_part_config) == 0:
        return []

    for pf in non_nic_partition_pfs:
        passthrough_tmp = get_passthrough_config(
            user_config, pf, allocated_pci)
        non_nic_part_config.extend(passthrough_tmp)
    return nic_part_config + non_nic_part_config


def get_passthrough_config_by_product(user_config,
                                      system_configs,
                                      allocated_pci):
    nic_part_config = []
    non_nic_part_config = []
    nic_partition_pfs = get_sriov_nic_partition_pfs(system_configs)
    non_nic_partition_pfs = get_sriov_non_nic_partition_pfs(system_configs)
    for pf in nic_partition_pfs:
        pf_path = _SYS_CLASS_NET_PATH + "/%s/device" % pf
        vendor, product = get_pci_device_info_by_ifname(pf_path, 'virtfn0')
        if (user_config['product_id'][-4:] == product[-4:] and
                user_config['vendor_id'][-4:] == vendor[-4:]):
            passthrough_tmp = get_passthrough_config(
                user_config, pf, allocated_pci)
            nic_part_config.extend(passthrough_tmp)

    if len(nic_part_config) == 0:
        return []

    for pf in non_nic_partition_pfs:
        pf_path = _SYS_CLASS_NET_PATH + "/%s/device" % pf
        vendor, product = get_pci_device_info_by_ifname(pf_path, 'virtfn0')
        if (user_config['product_id'][-4:] == product[-4:] and
                user_config['vendor_id'][-4:] == vendor[-4:]):
            passthrough_tmp = get_passthrough_config(
                user_config, pf, allocated_pci)
            non_nic_part_config.extend(passthrough_tmp)
    return nic_part_config + non_nic_part_config


def get_pf_name_from_phy_network(physical_network):
    try:
        out, err = processutils.execute(
            'hiera', '-c', '/etc/puppet/hiera.yaml',
            'neutron::agents::ml2::sriov::physical_device_mappings')
        if not err:
            phys_dev_mappings = json.loads(out)
            for phy_dev_map in phys_dev_mappings:
                net_name, nic_name = phy_dev_map.split(':')
                if net_name == physical_network:
                    return nic_name
            return None

    except processutils.ProcessExecutionError:
        raise


def generate_combined_configuration(user_configs, system_configs):
    """Derived configuration = user_config - system_configs

    Identify the user_defined configuration that overlaps with the
    NIC Partitioned VFs and remove those VFs from the derived configuration
    In case of no overlap, the user defined configuration shall be used
    as it is.
    :param user_configs: THT param NovaPCIPassthrough
    :param system_configs: Derived from sriov-mapping.yaml
    """

    non_nic_part_config = []
    nic_part_config = []

    allocated_pci = get_allocated_pci_addresses(system_configs)
    nic_partition_pfs = get_sriov_nic_partition_pfs(system_configs)

    for user_config in user_configs:
        if ('devname' in user_config and
                (user_config['devname'] in nic_partition_pfs)):
            passthru_tmp = get_passthrough_config(
                user_config, user_config['devname'], allocated_pci)
            nic_part_config.extend(passthru_tmp)
        elif 'physical_network' in user_config:
            pf = get_pf_name_from_phy_network(user_config['physical_network'])
            if pf in nic_partition_pfs:
                passthru_tmp = get_passthrough_config(
                    user_config, pf, allocated_pci)
                nic_part_config.extend(passthru_tmp)
            else:
                non_nic_part_config.append(user_config)
        elif 'address' in user_config:
            passthrough_tmp = get_passthrough_config_by_address(
                user_config, system_configs, allocated_pci)
            if len(passthrough_tmp) == 0:
                non_nic_part_config.append(user_config)
            else:
                nic_part_config.extend(passthrough_tmp)
        elif ('product_id' in user_config and 'vendor_id' in user_config):
            passthrough_tmp = get_passthrough_config_by_product(
                user_config, system_configs, allocated_pci)
            if len(passthrough_tmp) == 0:
                non_nic_part_config.append(user_config)
            else:
                nic_part_config.extend(passthrough_tmp)
        else:
            non_nic_part_config.append(user_config)
    return (non_nic_part_config, nic_part_config)


if __name__ == "__main__":
    pci_passthrough = {}
    pci_file_path = '/etc/puppet/hieradata/pci_passthrough_whitelist.json'
    system_configs = get_sriov_configs()
    user_configs = user_passthrough_config()

    non_nic_part, nic_part = generate_combined_configuration(
        user_configs, system_configs)

    if len(nic_part) > 0:
        pci_passthrough[_PASSTHROUGH_WHITELIST_KEY] = (non_nic_part +
                                                       nic_part)

        with open(pci_file_path, 'w') as pci_file:
            json.dump(pci_passthrough, pci_file)
