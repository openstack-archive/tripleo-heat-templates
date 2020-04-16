#!/bin/bash
# Copyright 2020 Red Hat Inc.
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

set -e

show_usage() {
    echo "Usage: nova_ffu_db_sync.sh <api_db|db>"
}

if [ $# -lt 1 ]
then
    show_usage
    exit 1
fi

if [[ "$1" == "api_db" ]]; then
  RPM_MIGRATIONS_PATH="/usr/lib/python3.6/site-packages/nova/db/sqlalchemy/api_migrations/migrate_repo/versions"
elif [[ "$1" == "db" ]]; then
  RPM_MIGRATIONS_PATH="/usr/lib/python3.6/site-packages/nova/db/sqlalchemy/migrate_repo/versions"
fi

DB_VERSION=$( sudo -u nova /usr/bin/nova-manage $1 version )
_RPM_VERSION=$(ls ${RPM_MIGRATIONS_PATH} | grep -e '[0-9]_.*.py' | cut -d '_' -f1 | sort | tail -n1)
RPM_VERSION=$(expr $_RPM_VERSION + 0)

if (( $RPM_VERSION >= $DB_VERSION )); then
    sudo -u nova /usr/bin/nova-manage $1 sync
    if [[ "$1" == "db" ]]; then
        sudo -u nova /usr/bin/nova-manage db online_data_migrations
    fi
else
    echo DB_VERSION: $DB_VERSION RPM_VERSION: $RPM_VERSION;
fi
