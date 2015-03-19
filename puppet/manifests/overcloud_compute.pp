# Copyright 2014 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

if !str2bool(hiera('enable_package_install', 'false')) {
  case $::osfamily {
    'RedHat': {
      Package { provider => 'norpm' } # provided by tripleo-puppet
    }
    default: {
      warning('enable_package_install option not supported.')
    }
  }
}

if count(hiera('ntp::servers')) > 0 {
  include ::ntp
}

file { ['/etc/libvirt/qemu/networks/autostart/default.xml',
        '/etc/libvirt/qemu/networks/default.xml']:
  ensure => absent,
  before => Service['libvirt']
}

include ::nova
include ::nova::compute

nova_config {
  'DEFAULT/my_ip':                     value => $ipaddress;
  'DEFAULT/linuxnet_interface_driver': value => 'nova.network.linux_net.LinuxOVSInterfaceDriver';
}

$nova_enable_rbd_backend = hiera('nova_enable_rbd_backend', false)
if $nova_enable_rbd_backend {
  include ::ceph::profile::client
  include ::nova::compute::rbd
  ceph::key { 'client.openstack' :
    secret  => hiera('ceph::profile::params::mon_key'),
    cap_mon => hiera('ceph_openstack_default_cap_mon'),
    cap_osd => hiera('ceph_openstack_default_cap_osd'),
    user    => 'nova',
  }
}

include ::nova::compute::libvirt
include ::nova::network::neutron
include ::neutron

class { 'neutron::plugins::ml2':
  flat_networks        => split(hiera('neutron_flat_networks'), ','),
  tenant_network_types => [hiera('neutron_tenant_network_type')],
  type_drivers         => [hiera('neutron_tenant_network_type')],
}

class { 'neutron::agents::ml2::ovs':
  bridge_mappings => split(hiera('neutron_bridge_mappings'), ','),
  tunnel_types    => split(hiera('neutron_tunnel_types'), ','),
}

include ::ceilometer
include ::ceilometer::agent::compute

class { 'ceilometer::agent::auth':
  auth_url => join(['http://', hiera('keystone_host'), ':5000/v2.0']),
}

$snmpd_user = hiera('snmpd_readonly_user_name')
snmp::snmpv3_user { $snmpd_user:
  authtype => 'MD5',
  authpass => hiera('snmpd_readonly_user_password'),
}
class { 'snmp':
  agentaddress => ['udp:161','udp6:[::1]:161'],
  snmpd_config => [ join(['rouser ', hiera('snmpd_readonly_user_name')]), 'proc  cron', 'includeAllDisks  10%', 'master agentx', 'trapsink localhost public', 'iquerySecName internalUser', 'rouser internalUser', 'defaultMonitors yes', 'linkUpDownNotifications yes' ],
}
