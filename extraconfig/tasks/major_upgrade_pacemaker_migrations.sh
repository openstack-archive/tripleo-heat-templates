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

# This function will be called during a liberty->mitaka upgrade after init and
# after the aodh upgrade. It assumes that a special puppet snippet configuring
# keystone under wsgi has alread been run (i.e. /etc/httpd/conf.d/10*keystone*.conf
# files are already set).
function liberty_to_mitaka_keystone {
    # If the "openstack-core-clone" resource already exists we do not need to make this transition
    # as the function needs to be idempotent
    if pcs resource show "openstack-core-clone"; then
        return 0
    fi
    # Only run this on the bootstrap node
    if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
        CIB="/root/liberty-cib.xml"
        CIB_BACKUP="/root/liberty-cib-orig.xml"
        rm -f $CIB $CIB_BACKUP || /bin/true

        pcs cluster cib $CIB

        cp -f $CIB $CIB_BACKUP || /bin/true
        PCS="pcs -f $CIB"

        # Create dummy resource
        $PCS resource create openstack-core ocf:heartbeat:Dummy --clone

        # change all constraints from keystone to dummy
        CONSTR="$($PCS config | grep keystone | grep start | grep then)"
        echo "$CONSTR" | {
            while read i; do
                ACT=$(echo "$i" | awk '{print $1}')
                SRC=$(echo "$i" | awk '{print $2}')
                DST=$(echo "$i" | awk '{print $5}')
                CID=$(echo "$i" | awk '{print $7}' | sed -e 's/.*id\://g' -e 's/)//g')
                if [ "$SRC" == "openstack-keystone-clone" ]; then
                    $PCS constraint order $ACT openstack-core-clone then $DST
                else
                    $PCS constraint order $ACT $SRC then openstack-core-clone
                fi
                $PCS constraint remove $CID
            done;
        }
        # We push the CIB after removing the keystone resource as we want
        # to be sure that the httpd resource is untouched. Otherwise we risk
        # httpd being restarted before keystone is stopped which would give
        # us a conflicting listening port, because during this step httpd already
        # has the keystone wsgi configuration but was not restarted
        $PCS resource delete openstack-keystone-clone
        pcs cluster cib-push $CIB

        # make sure httpd (which provides keystone now) are started after dummy
        pcs constraint order start openstack-core-clone then httpd-clone
    fi
}

function add_missing_openstack_core_constraints {
    # The CIBs are saved under /root as they might contain sensitive data
    if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
        CIB="/root/migration.cib"
        CIB_BACKUP="/root/backup.cib"
        CIB_PUSH_NEEDED=n

        rm -f "$CIB" "$CIB_BACKUP" || /bin/true
        pcs cluster cib "$CIB"
        cp "$CIB" "$CIB_BACKUP"

        # sahara is not necessarily always present
        if pcs -f "$CIB" resource | grep 'openstack-sahara-api-clone'; then
            if ! pcs -f "$CIB" constraint --full | grep 'start openstack-sahara-api-clone then start openstack-sahara-engine-clone'; then
                pcs -f "$CIB" constraint order start openstack-sahara-api-clone then start openstack-sahara-engine-clone
                CIB_PUSH_NEEDED=y
            fi
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
    fi
}

function remove_ceilometer_alarm {
    if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
        if pcs status | grep openstack-ceilometer-alarm; then
            # Disable pacemaker resources for ceilometer-alarms
            pcs resource disable openstack-ceilometer-alarm-evaluator
            check_resource openstack-ceilometer-alarm-evaluator stopped 600
            pcs resource delete openstack-ceilometer-alarm-evaluator
            pcs resource disable openstack-ceilometer-alarm-notifier
            check_resource openstack-ceilometer-alarm-notifier stopped 600
            pcs resource delete openstack-ceilometer-alarm-notifier
        fi

        # remove constraints
        if  pcs constraint order show  | grep "start delay-clone then start openstack-ceilometer-alarm-evaluator-clone"; then
            pcs constraint remove order-delay-clone-openstack-ceilometer-alarm-evaluator-clone-mandatory
        fi

        if  pcs constraint order show  | grep "start openstack-ceilometer-alarm-notifier-clone then start openstack-ceilometer-notification-clone"; then
            pcs constraint remove order-openstack-ceilometer-alarm-notifier-clone-openstack-ceilometer-notification-clone-mandatory
        fi

        if  pcs constraint order show  | grep "start openstack-ceilometer-alarm-evaluator-clone then start openstack-ceilometer-alarm-notifier-clone"; then
            pcs constraint remove order-openstack-ceilometer-alarm-evaluator-clone-openstack-ceilometer-alarm-notifier-clone-mandatory
        fi

        if  pcs constraint colocation show  | grep "openstack-ceilometer-notification-clone with openstack-ceilometer-alarm-notifier-clone"; then
            pcs constraint remove colocation-openstack-ceilometer-notification-clone-openstack-ceilometer-alarm-notifier-clone-INFINITY
        fi

        if  pcs constraint colocation show  | grep "openstack-ceilometer-alarm-notifier-clone with openstack-ceilometer-alarm-evaluator-clone"; then
            pcs constraint remove colocation-openstack-ceilometer-alarm-notifier-clone-openstack-ceilometer-alarm-evaluator-clone-INFINITY
        fi

        if  pcs constraint colocation show  | grep "openstack-ceilometer-alarm-evaluator-clone with delay-clone"; then
            pcs constraint remove colocation-openstack-ceilometer-alarm-evaluator-clone-delay-clone-INFINITY
        fi
    fi

    # uninstall openstack-ceilometer-alarm package
    yum -y remove openstack-ceilometer-alarm
}
