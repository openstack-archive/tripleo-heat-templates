#!/bin/bash
#
# Copyright 2017 Red Hat, Inc.
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
#
set -e

SCRIPT_DIR=$(cd `dirname $0` && pwd -P)
OUTPUT_DIR=${OUTPUT_DIR:-$(cd "${SCRIPT_DIR}/../" && pwd -P)}

echo "Generating ${OUTPUT_DIR}/roles_data.yaml"
$SCRIPT_DIR/roles-data-generate.py Controller Compute BlockStorage ObjectStorage CephStorage > $OUTPUT_DIR/roles_data.yaml

echo "Generating ${OUTPUT_DIR}/roles_data_undercloud.yaml"
$SCRIPT_DIR/roles-data-generate.py Undercloud > $OUTPUT_DIR/roles_data_undercloud.yaml

echo "Generating ${OUTPUT_DIR}/roles_data_standalone.yaml"
$SCRIPT_DIR/roles-data-generate.py Standalone > $OUTPUT_DIR/roles_data_standalone.yaml
