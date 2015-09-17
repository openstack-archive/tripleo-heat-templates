#!/usr/bin/env python
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

import os
import sys
import traceback
import yaml

base_path = sys.argv[1]
exit_val = 0
failed_files = []

def validate(filename):
    try:
        yaml.load(open(filename).read())
    except Exception:
        print(traceback.format_exc())
        return 1
    return 0

for subdir, dirs, files in os.walk(base_path):
    for f in files:
        if f.endswith('.yaml'):
            file_path = os.path.join(subdir, f)
            failed = validate(file_path)
            if failed:
                failed_files.append(file_path)
            exit_val |= failed

if failed_files:
    print('Validation failed on:')
    for f in failed_files:
        print(f)
else:
    print('Validation successful!')
sys.exit(exit_val)
