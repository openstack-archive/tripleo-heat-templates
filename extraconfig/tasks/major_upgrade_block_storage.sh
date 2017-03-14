#!/bin/bash
#
# This runs an upgrade of Cinder Block Storage nodes.
#
set -eu

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y -q update
