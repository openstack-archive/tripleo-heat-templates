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

# shell script to check if nova API DB migrations finished after X attempts.
# Default max is 60 iterations with 10s (default) timeout in between.

from __future__ import print_function

import logging
import os
import re
import sys
import time

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client
import requests
from six.moves.configparser import SafeConfigParser


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
LOG = logging.getLogger('nova_wait_for_placement_service')

iterations = 60
timeout = 10
nova_cfg = '/etc/nova/nova.conf'

if __name__ == '__main__':
    if os.path.isfile(nova_cfg):
        config = SafeConfigParser()
        config.read(nova_cfg)
    else:
        LOG.error('Nova configuration file %s does not exist', nova_cfg)
        sys.exit(1)

    # get keystone client with details from [placement] section
    auth = v3.Password(
        user_domain_name=config.get('placement', 'user_domain_name'),
        username=config.get('placement', 'username'),
        password=config.get('placement', 'password'),
        project_name=config.get('placement', 'project_name'),
        project_domain_name=config.get('placement', 'user_domain_name'),
        auth_url=config.get('placement', 'auth_url')+'/v3')
    sess = session.Session(auth=auth, verify=False)
    keystone = client.Client(session=sess, interface='internal')

    iterations_endpoint = iterations
    placement_endpoint_url = None
    while iterations_endpoint > 1:
        iterations_endpoint -= 1
        try:
            # get placement service id
            placement_service_id = keystone.services.list(
                name='placement')[0].id

            # get placement endpoint (os_interface)
            placement_endpoint_url = keystone.endpoints.list(
                service=placement_service_id,
                interface=config.get('placement', 'os_interface'))[0].url
            if not placement_endpoint_url:
                LOG.error('Failed to get placement service endpoint!')
            else:
                break
        except Exception as e:
            LOG.exception('Retry - Failed to get placement service endpoint:')
        time.sleep(timeout)

    if not placement_endpoint_url:
        LOG.error('Failed to get placement service endpoint!')
        sys.exit(1)

    # we should have versions in the request response from placement,
    # queens has not the CURRENT in the response:
    # {"versions": [{"status": "CURRENT", "min_version": "1.0", "max_version":
    # "1.29", "id": "v1.0", "links": [{"href": "", "rel": "self"}]}]}
    response_reg = re.compile('.*versions,*')

    while iterations > 1:
        iterations -= 1
        try:
            r = requests.get(placement_endpoint_url+'/', verify=False)
            if r.status_code == 200 and response_reg.match(r.text):
                LOG.info('Placement service up! - %s', r.text)
                sys.exit(0)
                break
            else:
                LOG.info('response - %r', r)
                LOG.info('Placement service not up - %s, %s',
                         r.status_code,
                         r.text)
        except Exception as e:
            LOG.exception('Error query the placement endpoint:')
        time.sleep(timeout)

    sys.exit(1)

# vim: set et ts=4 sw=4 :
