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
# log records when health check run was successful
HEALTHY_REXS = [
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'Started (?P<service>[\w-]+) (container|healthcheck)'),
    re.compile(r'(?P<host>[\w\-\.\:]*) healthcheck_(?P<service>[\w-]+)'
               r'\[(?P<pid>\d+)\]: (?P<output>(?![Ee][Rr][Rr][Oo][Rr]).*)'),
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'tripleo_(?P<service>[\w-]+)_healthcheck.service: Succeeded')
]
# log records when health check run failed
UNHEALTHY_REXS = [
    re.compile(r'(?P<host>[\w\-\.\:]*) healthcheck_(?P<service>[\w-]+)'
               r'\[(?P<pid>\d+)\]: [Ee][Rr][Rr][Oo][Rr]: (?P<error>.+)'),
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'Failed to start (?P<service>[\w-]+) healthcheck'),
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'tripleo_(?P<service>[\w-]+)_healthcheck.service: Failed with result'),
]
# log records when health check is executed, contains additional data
EXEC_REXS = [
    # osp-16.2
    re.compile(r'(?P<host>[\w\-\.\:]*) podman\[(?P<pid>\d*)\]: '
               r'(?P<trash>.*) container exec (?P<container_id>\w*) '
               r'\(.*container_name=(?P<service>[\w-]+).*\)'),
    # osp-16.1
    re.compile(r'(?P<host>[\w\-\.\:]*) podman\[(?P<pid>\d*)\]: '
               r'(?P<trash>.*) container exec (?P<container_id>\w*) '
               r'\(.*name=(?P<service>[\w-]+).*\)')
]
# log records when container is down
DEAD_REXS = [
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'Dependency failed for (?P<service>[\w-]+) healthcheck'),
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'tripleo_(?P<service>((?!_healthcheck).)+).service: Failed with result'),
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'Failed to start (?P<service>[\w-]+) container'),
    re.compile(r'(?P<host>[\w\-\.\:]*) systemd\[.*\]: '
               r'tripleo_(?P<service>((?!_healthcheck).)+)(_healthcheck)?.service: '
               r'(Control|Main) process exited.*status=[^0]'),
    re.compile(r'(?P<host>[\w\-\.\:]*) podman\[(?P<pid>\d*)\]: '
               r'(?P<trash>.*) container died (?P<container_id>\w*) '
               r'\(.*name=(?P<service>[\w-]+).*\)'),
    re.compile(r'(?P<host>[\w\-\.\:]*) podman\[(?P<pid>\d*)\]: '
               r'(?P<trash>.*) container stop (?P<container_id>\w*) '
               r'\(.*container_name=(?P<service>[\w-]+).*\)')
]


def process_healthcheck_output(logfile):
    """Process saved output of health checks and returns list of healthy and
    unhealthy containers.
    """
    with open(logfile, 'r') as logs:
        data = {}
        for line in logs:
            for rex_list, default in [
                    (EXEC_REXS, {'status': 'checking', 'healthy': 1}),
                    (HEALTHY_REXS, {'status': 'healthy', 'healthy': 1}),
                    (UNHEALTHY_REXS, {'status': 'unhealthy', 'healthy': 0}),
                    (DEAD_REXS, {'status': 'stopped', 'healthy': 0})]:
                for rex in rex_list:
                    match = rex.search(line)
                    if match:
                        groups = match.groupdict()
                        item = data.setdefault(groups['service'], {
                            'service': groups['service'],
                            'container': 'unknown',
                        })
                        it = data[groups['service']] = {**item, **default}
                        if 'container_id' in groups:
                            it['container'] = groups['container_id'][:12]
                        break

    # truncate
    with open(logfile, 'w') as logs:
        pass

    ret_code, output = 0, []
    for _, opt in data.items():
        if opt['healthy'] < 1 and ret_code != 2:
            ret_code = 2
        output.append(opt)
    return ret_code, output

if __name__ == "__main__":
    RET_CODE, STATUS = process_healthcheck_output(HCLOG)
    print(json.dumps(STATUS))
    sys.exit(RET_CODE)
