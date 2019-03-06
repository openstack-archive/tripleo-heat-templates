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

import logging
from optparse import OptionParser
import os
import socket
import subprocess
import sys
import time


from keystoneauth1 import loading
from keystoneauth1 import session

from novaclient import client

from six.moves.configparser import SafeConfigParser

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
LOG = logging.getLogger('nova_cell_v2_discover_host')

nova_cfg = '/etc/nova/nova.conf'

if __name__ == '__main__':
    parser = OptionParser(usage="usage: %prog [options]")
    parser.add_option('-k', '--insecure',
                      action="store_false",
                      dest='insecure',
                      default=True,
                      help='Allow insecure connection when using SSL')

    (options, args) = parser.parse_args()
    LOG.debug('Running with parameter insecure = %s',
              options.insecure)

    if os.path.isfile(nova_cfg):
        config = SafeConfigParser()
        config.read(nova_cfg)
    else:
        LOG.error('Nova configuration file %s does not exist', nova_cfg)
        sys.exit(1)

    my_host = config.get('DEFAULT', 'host')
    if not my_host:
        # If host isn't set nova defaults to this
        my_host = socket.gethostname()

    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(
        auth_url=config.get('neutron',
                            'auth_url'),
        username=config.get('neutron',
                            'username'),
        password=config.get('neutron',
                            'password'),
        project_name=config.get('neutron',
                                'project_name'),
        project_domain_name=config.get('neutron',
                                       'project_domain_name'),
        user_domain_name=config.get('neutron',
                                    'user_domain_name'))
    sess = session.Session(auth=auth, verify=options.insecure)
    nova = client.Client('2.11', session=sess, endpoint_type='internal')

    # Wait until this host is listed in the service list then
    # run cellv2 host discovery
    retries = 10
    for i in range(retries):
        try:
            service_list = nova.services.list(binary='nova-compute')
            for entry in service_list:
                host = getattr(entry, 'host', '')
                zone = getattr(entry, 'zone', '')
                if host == my_host and zone != 'internal':
                    LOG.info('(cellv2) Service registered, running discovery')
                    sys.exit(subprocess.call([
                        '/usr/bin/nova-manage',
                        'cell_v2',
                        'discover_hosts',
                        '--by-service',
                        '--verbose'
                    ]))
                if len(service_list) == 0:
                    LOG.warning('(cellv2) no nova-compute service registered' +
                                ' after %i checks', i)
            LOG.info('(cellv2) Waiting for service to register')
        except subprocess.CalledProcessError:
            LOG.info('(cellv2) Retrying')
        except Exception as e:
            LOG.exception('Error during host discovery:')
        time.sleep(30)
sys.exit(1)

# vim: set et ts=4 sw=4 :
