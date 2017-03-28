#!/bin/bash
#
# This runs an upgrade of Cinder Block Storage nodes.
#
set -eu

# Special-case OVS for https://bugs.launchpad.net/tripleo/+bug/1669714
special_case_ovs_upgrade_if_needed

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y -q update
