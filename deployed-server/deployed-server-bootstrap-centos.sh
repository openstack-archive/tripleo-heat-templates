#!/bin/bash

set -eux

yum install -y \
    jq \
    python-ipaddr \
    openstack-puppet-modules \
    os-net-config \
    openvswitch \
    python-heat-agent* \
    openstack-selinux

ln -s -f /usr/share/openstack-puppet/modules/* /etc/puppet/modules

setenforce 0
sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
