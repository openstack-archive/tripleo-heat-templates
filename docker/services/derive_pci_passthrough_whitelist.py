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
    except IOError as exc:
        return None


def get_pci_addresses_by_ifname(pfs, allocated_pci):
    pci_addresses = {}
    device_info = {}
    pci_dir = '/sys/bus/pci/devices'
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
                            dev_info = get_pci_device_info_by_ifname(pci_dir, sub_dir)
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


def get_pci_passthrough_whitelist(pci_addresses, device_info):
    pci_passthrough_whitelist = {}
    pci_passthrough_list = []
    for pf, pci_list in pci_addresses.items():
        for pci in pci_list:
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
            pci_passthrough_list.append(pci_passthrough)
        pci_passthrough_whitelist['nova::compute::pci::passthrough'] = str(json.dumps(pci_passthrough_list))
    return pci_passthrough_whitelist


if __name__ == "__main__":
    pci_file_path = '/etc/puppet/hieradata/pci_passthrough_whitelist.json'
    configs = get_sriov_configs()
    nic_partition_pfs = get_sriov_nic_partition_pfs(configs)
    allocated_pci = get_allocated_pci_addresses(configs)
    pci_addresses, device_info = get_pci_addresses_by_ifname(nic_partition_pfs, allocated_pci)
    pci_passthrough = get_pci_passthrough_whitelist(pci_addresses, device_info)
    with open(pci_file_path, 'w') as pci_file:
        json.dump(pci_passthrough, pci_file)
