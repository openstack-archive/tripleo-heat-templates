#!/usr/bin/env python3
#
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

import datetime
import re
import sys

HCLOG = '/var/log/collectd/healthchecks.stdout'
START_RE = re.compile(
    r'(?P<timestamp>\w{3} \d{2} \d{2}\:\d{2}\:\d{2}) (?P<host>[\w\-\.\:]*) systemd\[.*\]: Started /usr/bin/podman healthcheck run (?P<container_id>\w*)')
EXEC_RE = re.compile(
    r'(?P<timestamp>\w{3} \d{2} \d{2}\:\d{2}\:\d{2}) (?P<host>[\w\-\.\:]*) podman\[(?P<pid>\d*)\]: (?P<trash>.*) container exec (?P<container_id>\w*) \(.*name=(?P<container_name>\w*).*\)')
RESULT_RE = re.compile(
    r'(?P<timestamp>\w{3} \d{2} \d{2}\:\d{2}\:\d{2}) (?P<host>[\w\-\.\:]*) podman\[(?P<pid>\d*)\]: (?P<result>(un)?healthy)')


def process_healthcheck_output(path_to_log):
    """Process saved output of health checks and returns list of unhealthy
    containers.
    """
    data = {}
    pid_map = {}
    with open(path_to_log, "r+") as logfile:
        for line in logfile:
            match = START_RE.search(line)
            if match:
                item = data.setdefault(match.group('container_id'), {})
                item['timestamp_start'] = match.group('timestamp')
                item['host'] = match.group('host')
                continue
            match = EXEC_RE.search(line)
            if match:
                item = data.setdefault(match.group('container_id'), {})
                item['container_name'] = match.group('container_name')
                item['host'] = match.group('host')
                item['pid'] = match.group('pid')
                pid_map[match.group('pid')] = match.group('container_id')
                continue
            match = RESULT_RE.search(line)
            if match:
                if match.group('pid') not in pid_map:
                    continue
                item = data[pid_map[match.group('pid')]]
                item['result'] = match.group('result')
                if 'timestamp_start' not in item:
                    continue
                try:
                    start = datetime.datetime.strptime(item['timestamp_start'],
                                                       '%b %d %H:%M:%S')
                    end = datetime.datetime.strptime(match.group('timestamp'),
                                                     '%b %d %H:%M:%S')
                    item['duration'] = (end - start).seconds
                except Exception as ex:
                    err = "[WARN] Failure during calculating duration: {}"
                    print(err.format(ex))
                    continue
        logfile.truncate()

    # truncate the file
    with open(HCLOG, "w") as logfile:
        pass

    unhealthy = []
    for container in data.values():
        if 'result' not in container:
            continue
        if container['result'] == 'healthy':
            continue
        log = ('{container_name}: Container health check on host {host} '
               'results as {result} after {duration}s.')
        unhealthy.append(log.format(**container))
    return unhealthy


if __name__ == "__main__":
    unhealthy = process_healthcheck_output(HCLOG)
    if unhealthy:
        print(' ; '.join(unhealthy))
        sys.exit(2)
