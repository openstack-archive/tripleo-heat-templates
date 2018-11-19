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
import sys
import time

from migrate.versioning import api as versioning_api

from nova import config
from nova.db.sqlalchemy import migration


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
LOG = logging.getLogger('nova_wait_for_db_sync')

iterations = 60
timeout = 10
nova_cfg = '/etc/nova/nova.conf'

if __name__ == '__main__':
    if os.path.isfile(nova_cfg):
        config.parse_args(sys.argv)
    else:
        LOG.error('Nova configuration file %s does not exist', nova_cfg)
        sys.exit(1)

    repo = migration._find_migrate_repo('api')
    max_migration_number = versioning_api.version(repo.path)
    LOG.info("Max migration number from files: %i", max_migration_number)

    # wait for db miration to be finished, or fail
    while iterations > 1:
        iterations -= 1
        try:
            db_migration_number = migration.db_version('api')
            if db_migration_number == max_migration_number:
                LOG.info('Nova API DB sync finished. Migration number %i',
                         db_migration_number)
                sys.exit(0)
                break
            else:
                LOG.info('Nova API DB sync not yet finished. Migration' +
                         'number DB/files (%i/%i)',
                         db_migration_number,
                         max_migration_number)
                time.sleep(timeout)
        except Exception as e:
            LOG.error('uuups something went wrong: %s ' + e.message)
            break

    sys.exit(1)

# vim: set et ts=4 sw=4 :
