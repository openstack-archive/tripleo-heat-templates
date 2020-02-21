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
    tmpwatch \
    rsync

ln -s -f /usr/share/openstack-puppet/modules/* /etc/puppet/modules

setenforce 0
sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config

echo '# empty ruleset created by deployed-server bootstrap' > /etc/sysconfig/iptables
echo '# empty ruleset created by deployed-server bootstrap' > /etc/sysconfig/ip6tables

if [ ! -f /usr/bin/ansible-playbook ]; then
    if [ -f /usr/bin/ansible-playbook-3 ]; then
        ln -s -f /usr/bin/ansible-playbook-3 /usr/local/bin/ansible-playbook
    fi
else
    if [ ! -f /usr/bin/ansible-playbook-3 ]; then
        ln -s -f /usr/bin/ansible-playbook /usr/local/bin/ansible-playbook-3
    fi
fi

# https://launchpad.net/bugs/1823353
systemctl enable network
systemctl start network
