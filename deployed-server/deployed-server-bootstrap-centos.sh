#!/bin/bash

set -eux

yum install -y \
    jq \
    python-ipaddress \
    puppet-tripleo \
    os-net-config \
    openvswitch \
    python-heat-agent* \
    openstack-selinux \
    tmpwatch

ln -s -f /usr/share/openstack-puppet/modules/* /etc/puppet/modules

setenforce 0
sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config

echo '# empty ruleset created by deployed-server bootstrap' > /etc/sysconfig/iptables
echo '# empty ruleset created by deployed-server bootstrap' > /etc/sysconfig/ip6tables
