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
