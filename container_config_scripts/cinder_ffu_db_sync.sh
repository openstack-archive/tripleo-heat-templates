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
    echo "Usage: cinder_ffu_db_sync.sh <sync|online>"
}

if [ $# -lt 1 ]
then
    show_usage
    exit 1
fi

DB_VERSION=$( sudo -u cinder cinder-manage db version )
_RPM_VERSION=$(ls /usr/lib/python3.6/site-packages/cinder/db/sqlalchemy/migrate_repo/versions/ | grep -e '[0-9]_.*.py' | cut -d '_' -f1 | sort | tail -n1)
RPM_VERSION=$(expr $_RPM_VERSION + 0)
if (( $RPM_VERSION >= $DB_VERSION )); then
    if [[ "$1" == "online" ]]; then
        sudo -u cinder cinder-manage service list | grep -v Binary| tr '@' ' ' | awk '{print $1 " " $2}' | while read i ; do
            sudo -u cinder cinder-manage service remove $i
        done
        sudo -u cinder cinder-manage db online_data_migrations
    elif [[ "$1" == "sync" ]]; then
        sudo -u cinder cinder-manage db sync --bump-versions
    fi
else
    echo DB_VERSION: $DB_VERSION RPM_VERSION: $RPM_VERSION;
fi
