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
import logging
import os
import random
import subprocess
import sys
import time

random.seed()

debug = os.getenv('__OS_DEBUG', 'false')

if debug.lower() == 'true':
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO

logging.basicConfig(stream=sys.stdout, level=loglevel)
LOG = logging.getLogger('nova_cell_v2_discover_hosts')

iterations = 10
timeout_max = 30
nova_cfg = '/etc/nova/nova.conf'

if __name__ == '__main__':
    if not os.path.isfile(nova_cfg):
        LOG.error('Nova configuration file %s does not exist', nova_cfg)
        sys.exit(1)

    for i in range(iterations):
        try:
            subprocess.check_call([
                '/usr/bin/nova-manage',
                'cell_v2',
                'discover_hosts',
                '--by-service',
                '--verbose'
            ])
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            LOG.error('Cell v2 discovery failed with exit code %d, retrying',
                      e.returncode)
        except Exception as e:
            LOG.exception('Error during host discovery')
        time.sleep(random.randint(1, timeout_max))
sys.exit(1)

# vim: set et ts=4 sw=4 :
