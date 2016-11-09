#!/bin/bash

set -eu

start_or_enable_service rabbitmq
check_resource rabbitmq started 600
start_or_enable_service redis
check_resource redis started 600
start_or_enable_service openstack-cinder-volume
check_resource openstack-cinder-volume started 600

# start httpd so keystone is available for gnocchi
# upgrade to run.
systemctl start httpd

# Swift isn't controled by pacemaker
systemctl_swift start
