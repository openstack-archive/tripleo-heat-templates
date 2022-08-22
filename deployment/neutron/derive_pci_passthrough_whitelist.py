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
_DERIVED_PCI_WHITELIST_FILE = '/etc/puppet/hieradata/pci_passthrough_whitelist.json'

MAX_FUNC = 0x7
MAX_DOMAIN = 0xFFFF
MAX_BUS = 0xFF
MAX_SLOT = 0x1F
ANY = '*'
REGEX_ANY = '.*'

ADD_PF_PCI_ADDRESS = 0x1
ADD_VF_PCI_ADDRESS = 0x2
DEL_USER_CONFIG = 0x3
KEEP_USER_CONFIG = 0x4


class InvalidConfigException(ValueError):
    pass


def get_pci_field_val(
    prop: str, maxval: int, hex_value: str
) -> None:
    if prop == ANY:
        return REGEX_ANY
    try:
        v = int(prop, 16)
    except ValueError:
        raise InvalidConfigException('Invalid PCI address specified {!r}'.format(prop))
    if v > maxval:
        raise InvalidConfigException('PCI address specified {!r} is out of range'.format(prop))
    return hex_value % v


def get_pciaddr_dict_from_usraddr(pci_addr: str):
    """Convert PCI address in STRING format to DICT
    (this is done for uniformity in PCI address)
    """
    pci_dict = {}
    dbs, sep, func = pci_addr.partition('.')
    pci_dict['function'] = ANY
    if func:
        func = func.strip()
        pci_dict['function'] = func
    if dbs:
        dbs_fields = dbs.split(':')
        if len(dbs_fields) > 3:
            raise InvalidConfigException('Invalid PCI address specified {!r}'.format(pci_addr))
        # If we got a partial address like ":00.", we need to turn this
        # into a domain of ANY, a bus of ANY, and a slot of 00. This code
        # allows the address,bus and/or domain to be left off
        dbs_all = [ANY] * (3 - len(dbs_fields))
        dbs_all.extend(dbs_fields)
        dbs_checked = [s.strip() or ANY for s in dbs_all]

        ''' domain, bus, slot = dbs_checked '''
        pci_dict['domain'], pci_dict['bus'], pci_dict['slot'] = dbs_checked

    pci_dict['domain'] = get_pci_field_val(pci_dict['domain'], MAX_DOMAIN, '%04x')
    pci_dict['slot'] = get_pci_field_val(pci_dict['slot'], MAX_SLOT, '%02x')
    pci_dict['bus'] = get_pci_field_val(pci_dict['bus'], MAX_BUS, '%02x')
    pci_dict['function'] = get_pci_field_val(pci_dict['function'], MAX_FUNC, '%1x')
    return pci_dict


def get_pci_regex_pattern(config_regex: str, size: int, maxval: int, hex_value: str):
    if config_regex in [ANY, REGEX_ANY]:
        config_regex = "[0-9a-fA-F]{%d}" % size

    try:
        re.compile(config_regex)
    except re.error:
        msg = "Invalid regex pattern identified %s" % config_regex
        raise InvalidConfigException(msg)
    try:
        v = int(config_regex, 16)
    except ValueError:
        return config_regex
    if v > maxval:
        msg = "Invalid pci address"
        raise InvalidConfigException(msg)
    return hex_value % v


def get_user_regex_from_addrdict(addr_dict):
    if isinstance(addr_dict, dict):
        domain_regex = get_pci_regex_pattern(addr_dict['domain'], 4, MAX_DOMAIN, '%04x')
        bus_regex = get_pci_regex_pattern(addr_dict['bus'], 2, MAX_BUS, '%02x')
        slot_regex = get_pci_regex_pattern(addr_dict['slot'], 2, MAX_SLOT, '%02x')
        function_regex = get_pci_regex_pattern(addr_dict['function'], 1, MAX_FUNC, '%1x')

        user_address_regex = '%s:%s:%s.%s' % (
           domain_regex, bus_regex, slot_regex,
           function_regex)
        return user_address_regex
    else:
        return None


def get_pci_addr_from_ifname(ifname: str):
    """Given the device name, returns the PCI address of a device
    and returns True if the address is in a physical function.
    """
    dev_path = os.path.join(_SYS_CLASS_NET_PATH, ifname, "device")
    if os.path.isdir(dev_path):
        try:
            return (os.readlink(dev_path).strip("./"))
        except OSError:
            raise
    return None


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
        return vendor, product
    except IOError:
        return None


def get_available_vf_pci_addresses_by_ifname(pf_name, allocated_pci):
    """It gets the list of all VF's of a PF minus the VFs allocated for
    NIC Partitioning. If the PF has 10 VFs and VFs 0,1 are allocated then
    the PCI address of VFs from 2 to 9 along with the device info wout be returned
    """
    vf_pci_addresses = {}
    pci_dir = _PCI_DEVICES_PATH
    if os.path.isdir(pci_dir):
        for sub_dir in os.listdir(pci_dir):
            if sub_dir in allocated_pci:
                continue
            pci_phyfn_dir = os.path.join(pci_dir, sub_dir, 'physfn/net')
            if os.path.isdir(pci_phyfn_dir):
                phyfn_dirs = os.listdir(pci_phyfn_dir)
                for phyfn in phyfn_dirs:
                    if phyfn in pf_name:
                        if phyfn not in vf_pci_addresses:
                            vf_pci_addresses[phyfn] = [sub_dir]
                        else:
                            vf_pci_addresses[phyfn].append(sub_dir)
    return vf_pci_addresses


def get_allocated_pci_addresses(configs):
    alloc_pci_info = []
    for config in configs:
        pci = config.get('pci_address', None)
        if pci:
            alloc_pci_info.append(pci)
    return alloc_pci_info


def get_pci_passthrough_whitelist(user_config, pf, pci_addresses):
    pci_passthrough_list = []

    for pci in pci_addresses:
        pci_passthrough = dict(user_config)
        pci_passthrough['address'] = str(pci)

        # devname and address fields can't co exist
        if 'devname' in pci_passthrough:
            del pci_passthrough['devname']

        pci_passthrough_list.append(pci_passthrough)
    return pci_passthrough_list


def user_passthrough_config():
    try:
        out, err = processutils.execute(
            'hiera', '-f', 'json', '-c', '/etc/puppet/hiera.yaml',
            _PASSTHROUGH_WHITELIST_KEY
            )
        if not err:
            data = json.loads(out)
            # Check the data type of first json decode
            if isinstance(data, str):
                # Decode once again to get the list
                return (json.loads(data))
            elif isinstance(data, list):
                return data
    except processutils.ProcessExecutionError:
        raise


def match_pf_details(user_config, pf_name, is_non_nic_pf: bool):
    """Decide the action for whitelist_pci_addr, based on user config

    :param user_config: THT param NovaPCIPassthrough
    :param pf_name: Interface/device name (str)
    :param is_non_nic_pf: Indicates whether the PF is noc-partitioned or not
    :return: Return the actions to be done, based on match criteria
    """

    # get the vendor and product id of the PF and VF
    pf_path = os.path.join(_SYS_CLASS_NET_PATH, pf_name, "device")
    vendor, vf_product = get_pci_device_info_by_ifname(pf_path, 'virtfn0')
    vendor, pf_product = get_pci_device_info_by_ifname(pf_path, '')

    if ('product_id' not in user_config or
         vf_product[-4:] == user_config['product_id'][-4:]):
        if is_non_nic_pf:
            # If NON NIC Part PF matches, then add the complete device
            return ADD_PF_PCI_ADDRESS
        else:
            """ In case of NIC Partitioning PF, add the VFs only (excluding NIC Part VFs)
                when the product id is not given or product_id matches that of VF
            """
            return ADD_VF_PCI_ADDRESS
    elif ('product_id' not in user_config or
            pf_product[-4:] == user_config['product_id'][-4:]):
        if is_non_nic_pf:
            # If product id of NON NIC Part VF matches, then add the complete device
            return ADD_PF_PCI_ADDRESS
        else:
            """ When the user_config address matches that of the NIC Partitioned PF,
                the PF must be removed from the user_config. So return the status such
                that the caller ignores this user_config if this user_config is very
                specific to the NIC Partitioned PF
            """
            return DEL_USER_CONFIG
    else:
        """ The Product ID neither belongs to VF nor PF, simply ignore matching
        """
        return KEEP_USER_CONFIG


# +------------+-----------------------+---------------------------+-------------------+
# |   USER     |     product_id        |       product_id          |  Product ID       |
# |   CONFIG   |     is VF             |       is PF               |  NOT mentioned    |
# +------------+-----------------------+---------------------------+-------------------+
# |   PCI addr |                       |                           |                   |
# |   is VF    |     Matching VF       |       INVALID             |  add only VFs     |
# |            |                       |                           |                   |
# |            |                       |                           |                   |
# +------------+-----------------------+---------------------------+-------------------+
# |            |                       |                           |                   |
# |   PCI addr |     ALL VFs of this   |       Matching PFs        | Add both PF and   |
# |   is PF    |     addr -            |      - NIC Part PFs       | available VFs     |
# |            |     NIC Part VFs      |                           |                   |
# |            |                       |                           |                   |
# +------------+-----------------------+---------------------------+-------------------+
# |            |                       |                           |                   |
# |  PCI addr  |     All matching      |       All matching        |  INVALID CASE     |
# |     not    |     VFs               |       PFs - NIC Part PF   |                   |
# |  specified |     NIC Part VFs      |                           |                   |
# |            |                       |                           |                   |
# +------------+-----------------------+---------------------------+-------------------+
def get_passthrough_config(user_config, pf_name,
  allocated_pci, is_non_nic_pf: bool):
    """Handle all variations of user specified pci addr format

    Arrive at the address fields of the whitelist.  Check the address fields of
    the pci.passthrough_whitelist configuration option, validating the address fields.

    :param user_config: THT param NovaPCIPassthrough
    :param pf_name: Interface/device name (str)
    :param allocated_pci: List of VFs (for nic-partitioned PF), which are used by host
    :param is_non_nic_pf: Indicates whether the PF is non-partitioned or not
    :return: pci_passthrough: Derived config list
    :return del_user_config: Flag to state if the user_config is to be deleted or not

    Example format for user_config:
    | [pci] in standard string format
    | passthrough_whitelist = {"address":"*:0a:00.*",
                          "physical_network":"physnet1"}
    | passthrough_whitelist = {"address": {"domain": ".*",
                                       "bus": "02",
                                       "slot": "01",
                                       "function": "[0-2]"},
                            "physical_network":"net1"}
    """
    sel_addr = []
    pci_passthrough = []
    del_user_config = False

    """ Get the regex of the address fields """
    if 'address' in user_config:
        if isinstance(user_config['address'], dict):
            addr_dict = user_config['address']
        elif isinstance(user_config['address'], str):
            addr_dict = get_pciaddr_dict_from_usraddr(user_config['address'])
        user_address_pattern = get_user_regex_from_addrdict(addr_dict)
    else:
        user_address_pattern = ("[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:"
                                    "[0-9a-fA-F]{2}.[0-7]")

    """ If address mentioned in user_config is PF, then get all VFs belonging to that PF
    """
    available_vfs = get_available_vf_pci_addresses_by_ifname(pf_name, allocated_pci)

    # get the pci address of the PF
    parent_pci_address = get_pci_addr_from_ifname(pf_name)
    user_address_regex = re.compile(user_address_pattern)

    # Match the user_config address with the PF's address
    if user_address_regex.match(parent_pci_address):
        match_id = match_pf_details(user_config, pf_name, is_non_nic_pf)
        """ if the address matches and there is no mismatch in
        product id's of PF, then add the PF's provided its not a
        NIC Partitioning PF
        """
        if match_id == ADD_PF_PCI_ADDRESS:
            sel_addr.append(parent_pci_address)
        elif match_id == ADD_VF_PCI_ADDRESS:
            if pf_name in available_vfs:
                for vf_addr in available_vfs[pf_name]:
                    sel_addr.append(vf_addr)
            if not sel_addr:
                del_user_config = True
        elif match_id == DEL_USER_CONFIG:
            del_user_config = True

        """ Match the user_config address with the VF's address
        A Regex of addresses could match both the VF and PF's.
        If it matches the PF, all available VFs would be included anyway,
        so it will be inclusive even if the address matches the VFs of the same PF
        Also if product id is specified, it must match that of the VF's.
        If product id is not mentioned in user_config, its assumed to have
        matched and is left to address matching for derived configuration.
        If Address is not mentioned, then all available VF's (excluding NIC partitioned VFs)
        with the matching product id shall be added to the derived configuration.
        """
    else:
        pf_path = os.path.join(_SYS_CLASS_NET_PATH, pf_name, "device")
        vendor, vf_product = get_pci_device_info_by_ifname(pf_path, 'virtfn0')
        if (('product_id' not in user_config or
            user_config['product_id'][-4:] == vf_product[-4:]) and
            pf_name in available_vfs):
            for vf_addr in available_vfs[pf_name]:
                user_address_regex = re.compile(user_address_pattern)
                if user_address_regex.match(vf_addr):
                    sel_addr.append(vf_addr)
            if not sel_addr:
                for vf_addr in allocated_pci:
                    if user_address_regex.match(vf_addr):
                        """ When the user_config address matches that of the NIC Partitioned VF,
                        the VF must be removed from the user_config. So return the status such
                        that the caller ignores this user_config if this user_config is very
                        specific to the NIC Partitioned VF. If the user_config resulted in the
                        derivations of other configurations, the derived configuration shall
                        replace the original user_config.
                        """
                        del_user_config = True

    if sel_addr:
        pci_passthrough = get_pci_passthrough_whitelist(
            user_config, pf_name, sel_addr)
    return pci_passthrough, del_user_config


def get_passthrough_config_for_all_pf(user_config,
                                  system_configs,
                                  allocated_pci):
    derived_config = []
    nic_partition_pfs = get_sriov_nic_partition_pfs(system_configs)
    non_nic_partition_pfs = get_sriov_non_nic_partition_pfs(system_configs)
    del_user_config = False

    """
    For each user_config, do the matching for NIC Partitioning PFs/VFs
    """
    for pf in nic_partition_pfs:
        passthrough_tmp, status = get_passthrough_config(
            user_config, pf, allocated_pci, False)
        del_user_config = del_user_config or status
        if passthrough_tmp:
            derived_config.extend(passthrough_tmp)

    """
    If there is no config added from NIC Part nics, then skip parsing the
    NON NIC Partitioned PFs.
    """
    if (derived_config or del_user_config):
        for pf in non_nic_partition_pfs:
            passthrough_tmp, status = get_passthrough_config(
                user_config, pf, allocated_pci, True)
            derived_config.extend(passthrough_tmp)

    if derived_config:
        return derived_config, False
    else:
        return derived_config, del_user_config


def get_pf_name_from_phy_network(physical_network):
    try:
        out, err = processutils.execute(
            'hiera', '-c', '/etc/puppet/hiera.yaml',
            'neutron::agents::ml2::sriov::physical_device_mappings')
        if not err:
            phys_dev_mappings = json.loads(out)
            ''' Check the data type of first json decode '''
            if not isinstance(phys_dev_mappings, list):
                msg = f'ml2::sriov::physical_device_mappings specified is not a list {phys_dev_mappings}'
                raise InvalidConfigException(msg)

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
    :return user_config_copy: Any non-nic partitioned cfg will be returned in this list
    :return derived_config: All nic partitioned cfg will be returned after derivation in this list
    """

    user_config_copy = []
    derived_config = []

    allocated_pci = get_allocated_pci_addresses(system_configs)
    nic_partition_pfs = get_sriov_nic_partition_pfs(system_configs)

    for user_config in user_configs:
        if 'address' in user_config and 'devname' in user_config:
            msg = f"Both devname and address can't be present in {_PASSTHROUGH_WHITELIST_KEY}"
            raise InvalidConfigException(msg)

        keys = ['address', 'product_id', 'devname']
        if not any(k in user_config for k in keys):
            # address or product_id or devname not present in user_config
            pf = get_pf_name_from_phy_network(user_config['physical_network'])
            user_config['address'] = get_pci_addr_from_ifname(pf)

        if 'devname' in user_config:
            if user_config['devname'] in nic_partition_pfs:
                user_config['address'] = get_pci_addr_from_ifname(user_config['devname'])
                del user_config['devname']
            else:
                user_config_copy.append(user_config)
                continue
        if ('address' in user_config or
           'product_id' in user_config):
            passthrough_tmp, del_user_config = get_passthrough_config_for_all_pf(
                user_config, system_configs, allocated_pci)

            """ If del_user_config is set, do not add to derived_config or
                user_config_copy
            """
            if not del_user_config:
                if passthrough_tmp:
                    derived_config.extend(passthrough_tmp)
                else:
                    user_config_copy.append(user_config)
        else:
            user_config_copy.append(user_config)
    return (user_config_copy, derived_config)


if __name__ == "__main__":
    pci_passthrough = {}
    pci_file_path = _DERIVED_PCI_WHITELIST_FILE
    system_configs = get_sriov_configs()
    user_configs = user_passthrough_config()

    # Check if user config list is valid
    if not isinstance(user_configs, list):
        raise InvalidConfigException('user_config specified is not a list {!r}'.format(user_configs))

    user_config_copy, derived = generate_combined_configuration(
        user_configs, system_configs)

    """ If the derivation does not bring in any changes, the user_config_copy list
        and user_configs shall be same. The pci_passthrough_whitelist.json
        shall be updated only when there is a change needed due to NIC Partition
    """
    if user_config_copy != user_configs:
        pci_passthrough[_PASSTHROUGH_WHITELIST_KEY] = (user_config_copy +
                                                       derived)
        with open(pci_file_path, 'w') as pci_file:
            json.dump(pci_passthrough, pci_file)
    else:
        print("user_configs is good, nothing to be modified")
