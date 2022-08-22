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
from collections import defaultdict
import difflib
import json
from pprint import pformat
import sys
import yaml

COMPARE_SECTIONS = ['parameters', 'conditions', 'resources', 'outputs']


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument('--details', '-d',
                   action='count',
                   default=0,
                   help='Show details, deeper comparison with -dd')
    p.add_argument('--common', '-c',
                   action='store_true',
                   help='Show common items when comparing sections')
    p.add_argument('--out', '-o',
                   action='store',
                   choices=['pformat', 'json'],
                   default='json',
                   help='Output format, either using pformat or json')
    p.add_argument('--width', '-w',
                   action='store',
                   default=80,
                   type=int,
                   help='When using pformat, this is the max width')
    p.add_argument('--section', '-s',
                   action='store',
                   nargs='*',
                   help="Sections to compare",
                   default=COMPARE_SECTIONS)
    p.add_argument('path_args', action='store', nargs='*')

    args = p.parse_args()
    if len(args.path_args) != 2:
        p.error("Need two files to compare")

    return args


def diff_list(list_a, list_b):
    """Takes 2 lists and returns the differences between them"""
    list_a = sorted(list_a)
    list_b = sorted(list_b)
    diffs = defaultdict(list)
    sequence = difflib.SequenceMatcher(None, list_a, list_b).get_opcodes()
    for tag, i, j, k, l in sequence:
        if tag == 'equal' and show_common:
            diffs['common'].extend(list_a[i:j])
        if tag in ('delete', 'replace'):
            diffs[FILE_A].extend(list_a[i:j])
        if tag in ('insert', 'replace'):
            diffs[FILE_B].extend(list_b[k:l])
    return "\n".join([f"{fn} {dl}" for fn, dl in diffs.items()])


def diff_dict(dict_a, dict_b):
    """Compares two dicts

    Converts 2 dicts to strings with pformat and returns
    a unified diff formatted string
    """
    if output_format == "pformat":
        str_a = pformat(dict_a, width=output_width)
        str_b = pformat(dict_b, width=output_width)
    else:
        str_a = json.dumps(dict_a, indent=2)
        str_b = json.dumps(dict_b, indent=2)
    return "\n".join([d for d in difflib.unified_diff(
        str_a.splitlines(),
        str_b.splitlines(),
        fromfile=FILE_A,
        tofile=FILE_B)])


args = parse_args()

path_args = args.path_args
show_details = args.details
show_common = args.common
sections = args.section
output_format = args.out
output_width = args.width

FILE_A = path_args[0]
FILE_B = path_args[1]

with open(FILE_A, 'r') as file_a:
    a = yaml.safe_load(file_a)

with open(FILE_B, 'r') as file_b:
    b = yaml.safe_load(file_b)

exit = "Files are different" if a != b else 0

if not show_details:
    sys.exit(exit)

# With -ddd, we print the full diff dict and exit
if show_details >= 3:
    print(diff_dict(a, b))
    sys.exit(exit)

section_diff = diff_list(list(a.keys()), list(a.keys()))
if section_diff:
    print(f"Sections list\n{section_diff}")

for item in sections:
    keys_a = list(a.get(item).keys())
    keys_b = list(b.get(item).keys())
    section_item_diff = diff_list(keys_a, keys_b)
    if section_item_diff:
        print(f"\n\nSection {item}\n{section_item_diff}")
    if show_details > 1:
        for key in list(set(keys_a + keys_b)):
            key_a = a.get(item, {}).get(key, {})
            key_b = b.get(item, {}).get(key, {})
            diff = diff_dict(key_a, key_b)
            # If a key is missing from either list, we don't want
            # to see the full diff, it's already flagged when
            # show_details == 1
            # We just want to see if child dict is existent on both sides
            # and different
            if diff and key_a and key_b:
                print(f"\n\n{item}/{key}\n{diff}")

sys.exit(exit)
