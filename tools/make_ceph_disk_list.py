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
import json
import sys


def parse_opts(argv):
    parser = argparse.ArgumentParser(
            description='Create JSON environment file with NodeDataLookup for '
                        'all disks (except root disk) found in introspection data. '
                        'May be run for each CephStorage node. '
                        'Converts the output of `openstack baremetal introspection '
                        'data save <node>` into a Heat environment file to be '
                        'passed to `openstack overcloud deploy` such that '
                        'all discovered disks will be configured as Ceph OSDs.')
    parser.add_argument('-i', '--introspection-data', metavar='INTROSPECTION_DATA',
                        nargs='+', help="Relative path to the JSON file(s) produced "
                        "by `openstack baremetal introspection data save <node>` for "
                        "each node; e.g. '-i node0.json node1.json ... nodeN.json'",
                        required=True)
    parser.add_argument('-o', '--tht-env-file', metavar='THT_ENV_FILE',
                        help=("Relative path to the tripleo-heat-template (THT) "
                              "environment JSON file to be produced by this tool. "
                              "Default: node_data_lookup.json"))
    parser.add_argument('-k', '--key', metavar='KEY',
                        help=("Key of ironic disk data structure to use to identify "
                              "disk. Must be one of name, wwn, serial, by_path "
                              "default: by_path"), default='by_path',
                              choices=['name', 'wwn', 'serial', 'by_path'])
    parser.add_argument('-e', '--exclude-list', metavar='EXCLUDES', nargs='*',
                        help=("List of devices to exclude identified "
                              "by value mapped by key; e.g. if '-k name' "
                              "and '-e /dev/sdb /dev/sdc' is passed, then "
                              "sdb and sdc will not be in the output file"),
                        default=[])
    opts = parser.parse_args(argv[1:])

    return opts


def parse_ironic(ironic_file):
    """Extracts relevant data from each ironic input file
    """
    with open(ironic_file, 'r') as f:
        try:
            ironic = json.load(f)
        except Exception:
            raise RuntimeError(
                'Invalid JSON file: {ironic_data_file}'.format(
                ironic_data_file=ironic_file))
        try:
            uuid = ironic['extra']['system']['product']['uuid']
        except Exception:
            raise RuntimeError(
                'The Machine Unique UUID is not defined in '
                'data file: {ironic_data_file}'.format(
                ironic_data_file=ironic_file))
        try:
            disks = ironic['inventory']['disks']
        except Exception:
            raise RuntimeError(
                'No disks were found in '
                'data file: {ironic_data_file}'.format(
                ironic_data_file=ironic_file))
        try:
            root_disk = ironic['root_disk']
        except Exception:
            raise RuntimeError(
                'No root disk was found in '
                'data file: {ironic_data_file}'.format(
                ironic_data_file=ironic_file))
    return uuid.lower(), root_disk, disks


def get_devices_list(root_disk, disks, ironic_file):
    """returns devices list without root disk and other excludes based on key
    """
    if root_disk[OPTS.key] is None:
        raise RuntimeError(
            'The requested --key "{key}" for the root disk is not defined '
            'in data file: {ironic_data_file}. Please use a different key.'
            .format(key=OPTS.key, ironic_data_file=ironic_file))
    exclude = OPTS.exclude_list
    # by default the root disk is excluded as it cannot be an OSD
    exclude.append(root_disk[OPTS.key])
    devices = []
    for disk_dict in disks:
        if disk_dict[OPTS.key] not in exclude:
            devices.append(disk_dict[OPTS.key])
    return devices


def wrap_node_data_lookup(uuid_to_devices):
    """given a uuid to devices map, returns dictionary like the following:
    {'parameter_defaults':
      {'NodeDataLookup':
        {'32e87b4c-c4a7-41be-865b-191684a6883b': {'devices': ['/dev/sdc']}},
        {'ea6a84d6-cf89-4fe2-b7bd-869b3fe4dd6b': {'devices': ['/dev/sdc']}}}}
    """
    node_data_lookup = {}
    node_data_lookup['NodeDataLookup'] = uuid_to_devices
    output = {}
    output['parameter_defaults'] = node_data_lookup
    return output


def write_to_file(node_data_lookup):
    """Writes THT env file in JSON containing NodeDataLookup
    To node_data_lookup.json or <file>.json if '-o <file>'
    """
    if OPTS.tht_env_file:
        file_name = OPTS.tht_env_file
    else:
        file_name = 'node_data_lookup.json'
    with open(file_name, 'w') as outfile:
        json.dump(node_data_lookup, outfile, indent=2)


OPTS = parse_opts(sys.argv)

node_data_lookup = {}
for ironic_data in OPTS.introspection_data:
    uuid, root_disk, disks = parse_ironic(ironic_data)
    devices = get_devices_list(root_disk, disks, ironic_data)
    devices_map = {}
    devices_map['devices'] = devices
    node_data_lookup[uuid] = devices_map

write_to_file(wrap_node_data_lookup(node_data_lookup))
