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

# manila-manage db sync is idempotent, as long as the code contains the version
# that the database is at. However, this helper script is to ensure that the
# command is always idempotent, and when the database is at a higher version
# than the version in the code, we'll just bail out rather than hard exiting.
set -e

DB_VERSION=$( sudo -u manila manila-manage db version )
REPO_VERSIONS=$( grep -h -r -Po "(?<=^revision \=).*" /usr/lib/python3.6/site-packages/manila/db/migrations/alembic/versions/ | tr -d  \'\" | uniq )
REPO_MAX=$( for v in $REPO_VERSIONS; do grep -r -q -e "^down_revision.*$v" /usr/lib/python3.6/site-packages/manila/db/migrations/alembic/versions/ || echo $v; done )

if [[ $DB_VERSION == $REPO_MAX ]]; then
    echo "Manila DB is already up to date: $DB_VERSION"
elif [[ $REPO_VERSIONS == *"$DB_VERSION"* ]]; then
    # Package provides a newer version, we must upgrade
    sudo -u manila manila-manage db sync
    echo "Manila DB is upgraded to: $REPO_MAX"
else
    echo "Manila DB version: $DB_VERSION is higher than the maximum provided by the package $REPO_MAX. Nothing to do"
fi
