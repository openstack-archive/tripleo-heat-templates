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
import os

import ruamel.yaml
from ruamel.yaml import YAML

# Not all policy variables across services in THT are consistent. This mapping
# associates the service name to the right THT variable.
_SERVICE_MAP = {
    'barbican': 'BarbicanPolicies',
    'cinder': 'CinderApiPolicies',
    'designate': 'DesignateApiPolicies',
    'glance': 'GlanceApiPolicies',
    'ironic': 'IronicApiPolicies',
    'keystone': 'KeystonePolicies',
    'manila': 'ManilaApiPolicies',
    'neutron': 'NeutronApiPolicies',
    'nova': 'NovaApiPolicies',
    'octavia': 'OctaviaApiPolicies',
    'placement': 'PlacementPolicies'
}
_SCALAR = ruamel.yaml.scalarstring.DoubleQuotedScalarString

parser = argparse.ArgumentParser()
parser.add_argument(
    '-d', '--policy-dir', required=True,
    help=(
        'Directory containing policy.yaml files for OpenStack services. '
        'This script expects files to be named $SERVICE.yaml. For example '
        'nova.yaml for nova\'s policies.'
    )
)
args = parser.parse_args()

heat_template = {'parameter_defaults': {'EnforceSecureRbac': False}}
for filename in os.listdir(args.policy_dir):
    service = filename.split('.')[0]
    tht_var_name = _SERVICE_MAP.get(service)
    filepath = os.path.join(args.policy_dir, filename)
    with open(filepath, 'r') as f:
        safe_handler = YAML(typ='safe')
        # A lot of policy files have duplicate keys, which violates YAML. Allow
        # duplicate keys for the time being.
        safe_handler.allow_duplicate_keys = True
        policies = safe_handler.load(f)

    template = {}
    for name, value in policies.items():
        rule = name.split(':')[-1]
        rule = name.replace(':', '_')
        key = service + '-' + rule
        template[key] = {'key': _SCALAR(name), 'value': _SCALAR(value)}
    heat_template['parameter_defaults'][tht_var_name] = template

print(
    ruamel.yaml.dump(
        heat_template, Dumper=ruamel.yaml.RoundTripDumper, width=500
    )
)
