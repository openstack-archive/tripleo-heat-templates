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
        # LP #1599798
        # We first create openstack-core and wait for it to be started, so that
        # when we change the constraints the resource won't be stopped so no spurious restarts
        # will take place
        pcs resource create openstack-core ocf:heartbeat:Dummy --clone  interleave=true
        check_resource openstack-core started 600

        # We unmanage the httpd resource to make sure that pacemaker won't race
        # with the keystone deletion/stopping during the CIB transaction that
        # will take place later
        pcs resource unmanage httpd-clone
        CIB="/root/liberty-cib.xml"
        CIB_BACKUP="/root/liberty-cib-orig.xml"
        rm -f $CIB $CIB_BACKUP || /bin/true

        pcs cluster cib $CIB
        cp -f $CIB $CIB_BACKUP || /bin/true
        PCS="pcs -f $CIB"

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
        pcs cluster cib-push $CIB
        # We make sure there are no outstanding transactions before removing
        # and stopping keystone
        timeout -k 10 600 crm_resource --wait
        pcs resource delete openstack-keystone-clone

        # Let's be 100% sure that the keystone resource is stopped and gone before
        # we remanage the httpd resource later below. We cannot reuse check_resource
        # as the resource might not exist already in which case the function would fail
        tstart=$(date +%s)
        while pcs status | grep -q keystone-clone; do
            sleep 5
            tnow=$(date +%s)
            if (( tnow-tstart > 600)) ; then
                echo_error "ERROR: keystone failed to stop during migration"
                exit 1
            fi
        done
        # make sure httpd (which provides keystone now) are started after dummy
        pcs constraint order start openstack-core-clone then httpd-clone

        # We re-manage the httpd resource now and make sure it is fully started
        # so that a subsequent reload will not fail
        pcs resource manage httpd-clone
        check_resource httpd started 1800
    fi
}

# If the major version of mysql is going to change after the major
# upgrade, the database must be upgraded on disk to avoid failures
# due to internal incompatibilities between major mysql versions
# https://bugs.launchpad.net/tripleo/+bug/1587449
# This function detects whether a database upgrade is required
# after a mysql package upgrade. It returns 0 when no major upgrade
# has to take place, 1 otherwise.
function is_mysql_upgrade_needed {
    # The name of the package which provides mysql might differ
    # after the upgrade. Consider the generic package name, which
    # should capture the major version change (e.g. 5.5 -> 10.1)
    local name="mariadb"
    local output
    local ret
    set +e
    output=$(yum -q check-update $name)
    ret=$?
    set -e
    if [ $ret -ne 100 ]; then
        # no updates so we exit
        echo "0"
        return
    fi

    local currentepoch=$(rpm -q --qf "%{epoch}" $name)
    local currentversion=$(rpm -q --qf "%{version}" $name | cut -d. -f-2)
    local currentrelease=$(rpm -q --qf "%{release}" $name)
    local newoutput=$(repoquery -a --pkgnarrow=updates --qf "%{epoch} %{version} %{release}\n" $name)
    local newepoch=$(echo "$newoutput" | awk '{ print $1 }')
    local newversion=$(echo "$newoutput" | awk '{ print $2 }' | cut -d. -f-2)
    local newrelease=$(echo "$newoutput" | awk '{ print $3 }')

    # With this we trigger the dump restore/path if we change either epoch or
    # version in the package If only the release tag changes we do not do it
    # FIXME: we could refine this by trying to parse the mariadb version
    # into X.Y.Z and trigger the update only if X and/or Y change.
    output=$(python -c "import rpm; rc = rpm.labelCompare((\"$currentepoch\", \"$currentversion\", None), (\"$newepoch\", \"$newversion\", None)); print rc")
    if [ "$output" != "-1" ]; then
        echo "0"
        return
    fi
    echo "1"
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
    # Workaround for bug 1613211 to fix up Liberty deployments that
    # already got broken with regards to /etc/puppet/modules symlinks
    ln -f -s /usr/share/openstack-puppet/modules/* /etc/puppet/modules/

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
