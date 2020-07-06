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
retries=0

if [ -d /var/lib/mysql/neutron ] ; then
  # check whether the database is available and returning responses
  until mysql -e "SELECT 1;" &>/dev/null; do
    retries=$(( retries + 1 ))
    # 12 retries = 12 x 10sec = 2 minutes
    if [ $retries -ge 12 ]; then
      echo "Database still not available. Terminating ..."
      exit 1
    else
      echo "$retries: Waiting for database availability ..."
      sleep 10
    fi
  done

  mysql -e "CREATE DATABASE IF NOT EXISTS \`ovs_neutron\`;"
  for table in `mysql -B -N -e "SHOW TABLES;" neutron`; do
    mysql -e "RENAME TABLE \`neutron\`.\`$table\` to \`ovs_neutron\`.\`$table\`"
  done
  mysql -e "DROP DATABASE \`neutron\`;"
fi
