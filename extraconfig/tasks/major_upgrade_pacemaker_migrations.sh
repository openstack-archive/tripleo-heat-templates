#!/bin/bash

# Special pieces of upgrade migration logic go into this
# file. E.g. Pacemaker cluster transitions for existing deployments,
# matching changes to overcloud_controller_pacemaker.pp (Puppet
# handles deployment, this file handles migrations).
#
# This file shouldn't execute any action on its own, all logic should
# be wrapped into bash functions. Upgrade scripts will source this
# file and call the functions defined in this file where appropriate.
#
# The migration functions should be idempotent. If the migration has
# been already applied, it should be possible to call the function
# again without damaging the deployment or failing the upgrade.

function add_missing_openstack_core_constraints {
    # The CIBs are saved under /root as they might contain sensitive data
    CIB="/root/migration.cib"
    CIB_BACKUP="/root/backup.cib"
    CIB_PUSH_NEEDED=n

    rm -f "$CIB" "$CIB_BACKUP" || /bin/true
    pcs cluster cib "$CIB"
    cp "$CIB" "$CIB_BACKUP"

    if ! pcs -f "$CIB" constraint --full | grep 'start openstack-sahara-api-clone then start openstack-sahara-engine-clone'; then
        pcs -f "$CIB" constraint order start openstack-sahara-api-clone then start openstack-sahara-engine-clone
        CIB_PUSH_NEEDED=y
    fi

    if ! pcs -f "$CIB" constraint --full | grep 'start openstack-core-clone then start openstack-ceilometer-notification-clone'; then
        pcs -f "$CIB" constraint order start openstack-core-clone then start openstack-ceilometer-notification-clone
        CIB_PUSH_NEEDED=y
    fi

    if ! pcs -f "$CIB" constraint --full | grep 'start openstack-aodh-evaluator-clone then start openstack-aodh-listener-clone'; then
        pcs -f "$CIB" constraint order start openstack-aodh-evaluator-clone then start openstack-aodh-listener-clone
        CIB_PUSH_NEEDED=y
    fi

    if pcs -f "$CIB" constraint --full | grep 'start openstack-core-clone then start openstack-heat-api-clone'; then
        CID=$(pcs -f "$CIB" constraint --full | grep 'start openstack-core-clone then start openstack-heat-api-clone' | sed -e 's/.*id\://g' -e 's/)//g')
        pcs -f "$CIB" constraint remove $CID
        CIB_PUSH_NEEDED=y
    fi

    if [ "$CIB_PUSH_NEEDED" = 'y' ]; then
        pcs cluster cib-push "$CIB"
    fi
}

function remove_ceilometer_alarm {
    if pcs status | grep openstack-ceilometer-alarm; then
        # Disable pacemaker resources for ceilometer-alarms
        pcs resource disable openstack-ceilometer-alarm-evaluator
        check_resource openstack-ceilometer-alarm-evaluator stopped 600
        pcs resource delete openstack-ceilometer-alarm-evaluator
        pcs resource disable openstack-ceilometer-alarm-notifier
        check_resource openstack-ceilometer-alarm-notifier stopped 600
        pcs resource delete openstack-ceilometer-alarm-notifier

        # remove constraints
        pcs constraint remove ceilometer-delay-then-ceilometer-alarm-evaluator-constraint
        pcs constraint remove ceilometer-alarm-evaluator-with-ceilometer-delay-colocation
        pcs constraint remove ceilometer-alarm-evaluator-then-ceilometer-alarm-notifier-constraint
        pcs constraint remove ceilometer-alarm-notifier-with-ceilometer-alarm-evaluator-colocation
        pcs constraint remove ceilometer-alarm-notifier-then-ceilometer-notification-constraint
        pcs constraint remove ceilometer-notification-with-ceilometer-alarm-notifier-colocation

    fi

    # uninstall openstack-ceilometer-alarm package
    yum -y remove openstack-ceilometer-alarm

}
