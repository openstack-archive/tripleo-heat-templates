#!/usr/bin/env python
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
from __future__ import print_function
import os
import pwd
import socket
import subprocess
import sys
import time

# Delete this immediataly as it contains auth info
os.unlink(__file__)

# Only need root to read this script, drop to nova user
nova_uid, nova_gid = pwd.getpwnam('nova')[2:4]
os.setgid(nova_gid)
os.setuid(nova_uid)


os.environ.update(
    OS_PROJECT_DOMAIN_NAME='__OS_PROJECT_DOMAIN_NAME',
    OS_USER_DOMAIN_NAME='__OS_PROJECT_USER_NAME',
    OS_PROJECT_NAME='__OS_PROJECT_NAME',
    OS_USERNAME='__OS_USERNAME',
    OS_PASSWORD='__OS_PASSWORD',
    OS_AUTH_URL='__OS_AUTH_URL',
    OS_AUTH_TYPE='password',
    OS_IDENTITY_API_VERSION='3'
)

try:
    my_host = subprocess.check_output([
        'crudini',
        '--get',
        '/etc/nova/nova.conf',
        'DEFAULT',
        'host'
    ]).rstrip()
except subprocess.CalledProcessError:
    # If host isn't set nova defaults to this
    my_host = socket.gethostname()

# Wait until this host is listed in the service list then
# run cellv2 host discovery
retries = 10
for i in range(retries):
    try:
        service_list = subprocess.check_output([
            'openstack',
            '-q',
            '--os-interface',
            'internal',
            'compute',
            'service',
            'list',
            '-c',
            'Host',
            '-c',
            'Zone',
            '-f',
            'value'
        ]).split('\n')
        for entry in service_list:
            host, zone = entry.split()
            if host == my_host and zone != 'internal':
                print('(cellv2) Service registered, running discovery')
                sys.exit(subprocess.call([
                    '/usr/bin/nova-manage',
                    'cell_v2',
                    'discover_hosts',
                    '--by-service',
                    '--verbose'
                ]))
        print('(cellv2) Waiting for service to register')
    except subprocess.CalledProcessError:
        print('(cellv2) Retrying')
    time.sleep(30)
sys.exit(1)
