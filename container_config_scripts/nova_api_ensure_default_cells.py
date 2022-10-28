#!/usr/bin/env python
#
# Copyright 2022 Red Hat Inc.
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

from configparser import ConfigParser
import logging
import os
import subprocess
import sys
from urllib import parse as urlparse

config = ConfigParser(strict=False)

debug = os.getenv('__OS_DEBUG', 'false')

if debug.lower() == 'true':
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO

logging.basicConfig(stream=sys.stdout, level=loglevel)
LOG = logging.getLogger('nova_api_ensure_default_cells')

NOVA_CFG = '/etc/nova/nova.conf'
CELL0_ID = '00000000-0000-0000-0000-000000000000'
DEFAULT_CELL_NAME = 'default'


def template_netloc_credentials(netloc, index=None):
    if '@' in netloc:
        userpass, hostport = netloc.split('@', 1)
        has_pass = ':' in userpass
        if index is None:
            cred_template = '{username}'
            if has_pass:
                cred_template += ':{password}'
        else:
            cred_template = '{{username{index}}}'.format(index=index)
            if has_pass:
                cred_template += ':{{password{index}}}'.format(index=index)
        return '@'.join((cred_template, hostport))
    else:
        return netloc


def template_url(url):
    parsed = urlparse.urlparse(url)
    if ',' in parsed.netloc:
        orig_netlocs = parsed.netloc.split(',')
        templ_netlocs = []
        index = 0
        for netloc in orig_netlocs:
            index += 1
            templ_netlocs.append(template_netloc_credentials(netloc, index))
        new_netloc = ','.join(templ_netlocs)
    else:
        new_netloc = template_netloc_credentials(parsed.netloc)
    return parsed._replace(netloc=new_netloc).geturl()


def parse_list_cells(list_cells_output):
    list_cells_lines = list_cells_output.split('\n')
    if len(list_cells_lines) < 5:
        raise ValueError('Invalid nova-manage cell_v2 list_cells output')

    data_rows = list_cells_lines[3:-2]
    by_name = {}
    by_uuid = {}

    for row in data_rows:
        parts = row.split('|')
        entry = {
            'name': parts[1].strip(),
            'uuid': parts[2].strip(),
            'transport_url': parts[3].strip(),
            'database_connection': parts[4].strip(),
        }
        by_name[entry['name']] = entry
        by_uuid[entry['uuid']] = entry

    return by_name, by_uuid


def create_or_update_default_cells(cell0_db, default_db, default_transport_url):
    list_cells_cmd = ['/usr/bin/nova-manage', 'cell_v2', 'list_cells', '--verbose']
    list_cells_output = subprocess.check_output(list_cells_cmd, encoding='utf-8')
    cells_by_name, cells_by_uuid = parse_list_cells(list_cells_output)

    if CELL0_ID in cells_by_uuid:
        LOG.info('Setting cell0 database connection to \'{}\''.format(cell0_db))
        cmd = [
            '/usr/bin/nova-manage', 'cell_v2', 'update_cell',
            '--cell_uuid', CELL0_ID,
            '--database_connection', cell0_db,
            '--transport-url', 'none:///'
        ]
    else:
        LOG.info('Creating cell0 with database connection \'{}\''.format(cell0_db))
        cmd = [
            '/usr/bin/nova-manage', 'cell_v2', 'map_cell0',
             '--database_connection', cell0_db
        ]
    subprocess.check_call(cmd)

    if DEFAULT_CELL_NAME in cells_by_name:
        LOG.info('Setting default cell database connection to \'{}\' and transport url to \'{}\''.format(
            default_db, default_transport_url))
        cmd = [
            '/usr/bin/nova-manage', 'cell_v2', 'update_cell',
            '--cell_uuid', cells_by_name[DEFAULT_CELL_NAME]['uuid'],
            '--database_connection', default_db,
            '--transport-url', default_transport_url
        ]
    else:
        LOG.info('Creating default cell with database connection \'{}\' and transport url \'{}\''.format(
            default_db, default_transport_url))
        cmd = [
            '/usr/bin/nova-manage', 'cell_v2', 'create_cell',
            '--name', DEFAULT_CELL_NAME,
             '--database_connection', default_db,
            '--transport-url', default_transport_url
        ]
    subprocess.check_call(cmd)


def replace_db_name(db_url, db_name):
    return urlparse.urlparse(db_url)._replace(path=db_name).geturl()


if __name__ == '__main__':
    if os.path.isfile(NOVA_CFG):
        try:
            config.read(NOVA_CFG)
        except Exception:
            LOG.exception('Error while reading nova.conf:')
            sys.exit(1)
    else:
        LOG.error('Nova configuration file %s does not exist', NOVA_CFG)
        sys.exit(1)

    default_database_connection = config.get('database', 'connection')
    cell0_database_connection = replace_db_name(default_database_connection, 'nova_cell0')
    default_transport_url = config.get('DEFAULT', 'transport_url')

    create_or_update_default_cells(
        template_url(cell0_database_connection),
        template_url(default_database_connection),
        template_url(default_transport_url)
    )
