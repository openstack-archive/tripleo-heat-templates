#!/bin/bash
#
# This delivers the aodh data migration script to be invoked as part of the tripleo
# major upgrade workflow to migrate all the alarm data from mongodb to mysql.
# This needs to run post controller node upgrades so new aodh mysql db configured and
# running.
#
set -eu

#Get existing mongodb connection
MONGO_DB_CONNECTION="$(crudini --get /etc/ceilometer/ceilometer.conf database connection)"

# Get the aodh database string from hiera data
MYSQL_DB_CONNECTION="$(crudini --get /etc/aodh/aodh.conf database connection)"

#Run migration
/usr/bin/aodh-data-migration --nosql-conn $MONGO_DB_CONNECTION --sql-conn $MYSQL_DB_CONNECTION


