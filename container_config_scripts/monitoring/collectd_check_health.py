#!/usr/bin/env python3
# Copyright 2018 Red Hat Inc.
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
import re
import sys

HCLOG = '/var/log/collectd/healthchecks.log'
SERVICE_REGX = re.compile(r"""
    \shealthcheck_(?P<service_name>\w+)             # service
    \[(?P<id>\d+)\]                                 # pid
    """, re.VERBOSE)
ERROR_REGX = re.compile(r"""
    \shealthcheck_(?P<service_name>\w+)             # service
    \[(?P<id>\d+)\]                                 # pid
    :\s[Ee]rror: (?P<error>.+)                      # error
    """, re.VERBOSE)


def process_healthcheck_output(logfile):
    """Process saved output of health checks and returns list of healthy and
    unhealthy containers.
    """
    with open(logfile, 'r') as logs:
        data = {}
        for line in logs:
            match = SERVICE_REGX.search(line)
            if match and not match.group('service_name') in data:
                data[match.group('service_name')] = {
                    'service': match.group('service_name'),
                    'container': match.group('id'),
                    'status': 'healthy',
                    'healthy': 1
                }
            match = ERROR_REGX.search(line)
            if match:
                data[match.group('service_name')] = {
                    'service': match.group('service_name'),
                    'container': match.group('id'),
                    'status': 'unhealthy',
                    'healthy': 0
                }

    # truncate
    with open(logfile, 'w') as logs:
        pass

    ret_code, output = 0, []
    for _, opt in data.items():
        if opt['healthy'] > 0 and ret_code != 2:
            ret_code = 2
        output.append(opt)
    return ret_code, output

if __name__ == "__main__":
    RET_CODE, STATUS = process_healthcheck_output(HCLOG)
    print(json.dumps(STATUS))
    sys.exit(RET_CODE)
