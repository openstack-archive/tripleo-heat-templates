#!/bin/bash

set -e

# Wait until we know the mysql server is up and responding
timeout ${DB_MAX_TIMEOUT:-60} /bin/bash -c 'until mysqladmin -uroot ping 2>/dev/null; do sleep 1; done'

# After an upgrade, make sure that the running mysql had a chance to
# update its data table on disk.
mysql_upgrade

# Upgrade to 10.3: the default table row format changed from COMPACT
# to DYNAMIC, so upgrade the existing tables.
compact_tables=$(mysql -se 'SELECT CONCAT("`",TABLE_SCHEMA,"`.`",TABLE_NAME,"`") FROM information_schema.tables WHERE ENGINE = "InnoDB" and ROW_FORMAT = "Compact";');
for i in $compact_tables; do echo converting row format of table $i; mysql -e "ALTER TABLE $i ROW_FORMAT=DYNAMIC;"; done;
