#!/bin/bash

set -eux

yum install -y \
    jq \
    python-ipaddr \
    openstack-puppet-modules \
    os-net-config \
    openvswitch \
    python-heat-agent*

ln -s -f /usr/share/openstack-puppet/modules/* /etc/puppet/modules
