#!/bin/bash
#
# This runs an upgrade of Cinder Block Storage nodes.
#
set -eu

# Special-case OVS for https://bugs.launchpad.net/tripleo/+bug/1669714
update_network

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y -q update
