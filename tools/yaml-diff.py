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

import sys
import yaml

if len(sys.argv) != 3:
    raise RuntimeError('Not enough arguemnts')

FILE_A = sys.argv[1]
FILE_B = sys.argv[2]

with open(FILE_A, 'r') as file_a:
    a = yaml.safe_load(file_a)

with open(FILE_B, 'r') as file_b:
    b = yaml.safe_load(file_b)

if a != b:
    sys.exit("Files are different")

sys.exit(0)
