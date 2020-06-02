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

# shell script to check if placement API is up after X attempts.
# Default max is 60 iterations with 10s (default) timeout in between.

import logging
import os
import re
import six
import sys
import time

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client
import requests

# In python3 SafeConfigParser was renamed to ConfigParser and the default
# for duplicate options default to true. In case of nova it is valid to
# have duplicate option lines, e.g. passthrough_whitelist which leads to
# issues reading the nova.conf
# https://bugs.launchpad.net/tripleo/+bug/1827775
if six.PY3:
    from six.moves.configparser import ConfigParser
    config = ConfigParser(strict=False)
else:
    from six.moves.configparser import SafeConfigParser
    config = SafeConfigParser()


debug = os.getenv('__OS_DEBUG', 'false')

if debug.lower() == 'true':
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO

logging.basicConfig(stream=sys.stdout, level=loglevel)
LOG = logging.getLogger('placement_wait_for_service')

iterations = 60
timeout = 10
placement_cfg = '/etc/placement/placement.conf'

if __name__ == '__main__':
    if os.path.isfile(placement_cfg):
        try:
            config.read(placement_cfg)
        except Exception:
            LOG.exception('Error while reading placement.conf:')
    else:
        LOG.error('Placement configuration file %s does not exist',
                  placement_cfg)
        sys.exit(1)

    # get keystone client with details from [keystone_authtoken] section
    auth = v3.Password(
        user_domain_name=config.get('keystone_authtoken', 'user_domain_name'),
        username=config.get('keystone_authtoken', 'username'),
        password=config.get('keystone_authtoken', 'password'),
        project_name=config.get('keystone_authtoken', 'project_name'),
        project_domain_name=config.get('keystone_authtoken',
                                       'project_domain_name'),
        auth_url=config.get('keystone_authtoken', 'auth_url') + '/v3')
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

            # get placement endpoint
            # Note: puppet-placement does not support setting the interface
            #       until we have https://review.opendev.org/688862.
            #       Lets hard code 'internal' for now.
            placement_endpoint_url = keystone.endpoints.list(
                service=placement_service_id,
                region=config.get('keystone_authtoken', 'region_name'),
                interface='internal')[0].url
            if not placement_endpoint_url:
                LOG.error('Failed to get placement service endpoint!')
            else:
                break
        except Exception:
            LOG.exception('Retry - Failed to get placement service endpoint:')
        time.sleep(timeout)

    if not placement_endpoint_url:
        LOG.error('Failed to get placement service endpoint!')
        sys.exit(1)

    # we should have CURRENT in the request response from placement:
    # {"versions": [{"status": "CURRENT", "min_version": "1.0", "max_version":
    # "1.29", "id": "v1.0", "links": [{"href": "", "rel": "self"}]}]}
    response_reg = re.compile('.*CURRENT,*')

    while iterations > 1:
        iterations -= 1
        try:
            r = requests.get(placement_endpoint_url + '/', verify=False)
            if r.status_code == 200 and response_reg.match(r.text):
                LOG.info('Placement service up! - %s', r.text)
                sys.exit(0)
                break
            else:
                LOG.info('response - %r', r)
                LOG.info('Placement service not up - %s, %s',
                         r.status_code,
                         r.text)
        except Exception:
            LOG.exception('Error query the placement endpoint:')
        time.sleep(timeout)

    sys.exit(1)

# vim: set et ts=4 sw=4 :
