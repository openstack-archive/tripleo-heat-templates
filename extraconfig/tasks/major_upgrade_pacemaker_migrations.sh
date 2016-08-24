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

# This function returns the list of services to be migrated away from pacemaker
# and to systemd. The reason to have these services in a separate function is because
# this list is needed in three different places: major_upgrade_controller_pacemaker_{1,2}
# and in the function to migrate the cluster from full HA to HA NG
function services_to_migrate {
    # The following PCMK resources the ones the we are going to delete
    PCMK_RESOURCE_TODELETE="
    httpd-clone
    memcached-clone
    mongod-clone
    neutron-dhcp-agent-clone
    neutron-l3-agent-clone
    neutron-metadata-agent-clone
    neutron-netns-cleanup-clone
    neutron-openvswitch-agent-clone
    neutron-ovs-cleanup-clone
    neutron-server-clone
    openstack-aodh-evaluator-clone
    openstack-aodh-listener-clone
    openstack-aodh-notifier-clone
    openstack-ceilometer-central-clone
    openstack-ceilometer-collector-clone
    openstack-ceilometer-notification-clone
    openstack-cinder-api-clone
    openstack-cinder-scheduler-clone
    openstack-glance-api-clone
    openstack-glance-registry-clone
    openstack-gnocchi-metricd-clone
    openstack-gnocchi-statsd-clone
    openstack-heat-api-cfn-clone
    openstack-heat-api-clone
    openstack-heat-api-cloudwatch-clone
    openstack-heat-engine-clone
    openstack-nova-api-clone
    openstack-nova-conductor-clone
    openstack-nova-consoleauth-clone
    openstack-nova-novncproxy-clone
    openstack-nova-scheduler-clone
    openstack-sahara-api-clone
    openstack-sahara-engine-clone
    "
    echo $PCMK_RESOURCE_TODELETE
}

# This function will migrate a mitaka system where all the resources are managed
# via pacemaker to a newton setup where only a few services will be managed by pacemaker
# On a high-level it will operate as follows:
# 1. Set the cluster in maintenance-mode so no start/stop action will actually take place
#    during the conversion
# 2. Remove all the colocation constraints and then the ordering constraints, except the
#    ones related to haproxy/VIPs which exist in Newton as well
# 3. Take the cluster out of maintenance-mode
# 4. Remove all the resources that won't be managed by pacemaker in newton. The
#    outcome will be
#    that they are stopped and removed from pacemakers control
# 5. Do a resource cleanup to make sure the cluster is in a clean state
function migrate_full_to_ng_ha {
    if [[ -n $(pcmk_running) ]]; then
        pcs property set maintenance-mode=true

        # First we go through all the colocation constraints (except the ones
        # we want to keep, i.e. the haproxy/ip ones) and we remove those
        COL_CONSTRAINTS=$(pcs config show | sed -n '/^Colocation Constraints:$/,/^$/p' | grep -v "Colocation Constraints:" | egrep -v "ip-.*haproxy" | awk '{print $NF}' | cut -f2 -d: |cut -f1 -d\))
        for constraint in $COL_CONSTRAINTS; do
            log_debug "Deleting colocation constraint $constraint from CIB"
            pcs constraint remove "$constraint"
        done

        # Now we kill all the ordering constraints (except the haproxy/ip ones)
        ORD_CONSTRAINTS=$(pcs config show | sed -n '/^Ordering Constraints:/,/^Colocation Constraints:$/p' | grep -v "Ordering Constraints:"  | awk '{print $NF}' | cut -f2 -d: |cut -f1 -d\))
        for constraint in $ORD_CONSTRAINTS; do
            log_debug "Deleting ordering constraint $constraint from CIB"
            pcs constraint remove "$constraint"
        done
        # At this stage all the pacemaker resources are removed from the CIB.
        # Once we remove the maintenance-mode those systemd resources will keep
        # on running. They shall be systemd enabled via the puppet converge
        # step later on
        pcs property set maintenance-mode=false

        # At this stage there are no constraints whatsoever except the haproxy/ip ones
        # which we want to keep. We now disable and then delete each resource
        # that will move to systemd.
        # We want the systemd resources be stopped before doing "yum update",
        # that way "systemctl try-restart <service>" is no-op because the
        # service was down already 
        PCS_STATUS_OUTPUT="$(pcs status)"
        for resource in $(services_to_migrate) "delay-clone" "openstack-core-clone"; do
             if echo "$PCS_STATUS_OUTPUT" | grep "$resource"; then
                 log_debug "Deleting $resource from the CIB"
                 if ! pcs resource disable "$resource" --wait=600; then
                     echo_error "ERROR: resource $resource failed to be disabled"
                     exit 1
                 fi
                 pcs resource delete --force "$resource"
             else
                 log_debug "Service $resource not found as a pacemaker resource, not trying to delete."
             fi
        done

        # We need to do a pcs resource cleanup here + crm_resource --wait to
        # make sure the cluster is in a clean state before we stop everything,
        # upgrade and restart everything
        pcs resource cleanup
        # We are making sure here that the cluster is stable before proceeding
        if ! timeout -k 10 600 crm_resource --wait; then
            echo_error "ERROR: cluster remained unstable after resource cleanup for more than 600 seconds, exiting."
            exit 1
        fi
    fi
}

function disable_standalone_ceilometer_api {
    if [[ -n $(is_bootstrap_node) ]]; then
        if [[ -n $(is_pacemaker_managed openstack-ceilometer-api) ]]; then
            # Disable pacemaker resources for ceilometer-api
            manage_pacemaker_service disable openstack-ceilometer-api
            check_resource_pacemaker openstack-ceilometer-api stopped 600
            pcs resource delete openstack-ceilometer-api --wait=600
        fi
    fi
}
