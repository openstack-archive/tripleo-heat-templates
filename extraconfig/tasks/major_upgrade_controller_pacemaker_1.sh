#!/bin/bash

set -eu

check_cluster
check_pcsd
if [[ -n $(is_bootstrap_node) ]]; then
    check_clean_cluster
fi
check_python_rpm
check_galera_root_password
check_disk_for_mysql_dump

# We want to disable fencing during the cluster --stop as it might fence
# nodes where a service fails to stop, which could be fatal during an upgrade
# procedure. So we remember the stonith state. If it was enabled we reenable it
# at the end of this script
if [[ -n $(is_bootstrap_node) ]]; then
    STONITH_STATE=$(pcs property show stonith-enabled | grep "stonith-enabled" | awk '{ print $2 }')
    # We create this empty file if stonith was set to true so we can reenable stonith in step2
    rm -f /var/tmp/stonith-true
    if [ $STONITH_STATE == "true" ]; then
        touch /var/tmp/stonith-true
    fi
    pcs property set stonith-enabled=false
fi

# Migrate to HA NG and fix up rabbitmq queues
# We fix up the rabbitmq ha queues after the migration because it will
# restart the rabbitmq resource. Doing it after the migration means no other
# services will be restart as there are no other constraints
if [[ -n $(is_bootstrap_node) ]]; then
    migrate_full_to_ng_ha
    rabbitmq_newton_ocata_upgrade
fi

