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

include ::tripleo::packages
include ::tripleo::firewall

create_resources(kmod::load, hiera('kernel_modules'), {})
create_resources(sysctl::value, hiera('sysctl_settings'), {})
Exec <| tag == 'kmod::load' |>  -> Sysctl <| |>

if count(hiera('ntp::servers')) > 0 {
  include ::ntp
}

include ::timezone

file { ['/etc/libvirt/qemu/networks/autostart/default.xml',
        '/etc/libvirt/qemu/networks/default.xml']:
  ensure => absent,
  before => Service['libvirt'],
}
# in case libvirt has been already running before the Puppet run, make
# sure the default network is destroyed
exec { 'libvirt-default-net-destroy':
  command => '/usr/bin/virsh net-destroy default',
  onlyif  => '/usr/bin/virsh net-info default | /bin/grep -i "^active:\s*yes"',
  before  => Service['libvirt'],
}

# When utilising images for deployment, we need to reset the iSCSI initiator name to make it unique
exec { 'reset-iscsi-initiator-name':
  command => '/bin/echo InitiatorName=$(/usr/sbin/iscsi-iname) > /etc/iscsi/initiatorname.iscsi',
  onlyif  => '/usr/bin/test ! -f /etc/iscsi/.initiator_reset',
}->

file { '/etc/iscsi/.initiator_reset':
  ensure => present,
}

include ::nova
include ::nova::config
include ::nova::compute

nova_config {
  'DEFAULT/my_ip':                     value => $ipaddress;
  'DEFAULT/linuxnet_interface_driver': value => 'nova.network.linux_net.LinuxOVSInterfaceDriver';
}

$rbd_ephemeral_storage = hiera('nova::compute::rbd::ephemeral_storage', false)
$rbd_persistent_storage = hiera('rbd_persistent_storage', false)
if $rbd_ephemeral_storage or $rbd_persistent_storage {
  include ::ceph::profile::client

  $client_keys = hiera('ceph::profile::params::client_keys')
  $client_user = join(['client.', hiera('ceph_client_user_name')])
  class { '::nova::compute::rbd':
    libvirt_rbd_secret_key => $client_keys[$client_user]['secret'],
  }
}

if hiera('cinder_enable_nfs_backend', false) {
  if str2bool($::selinux) {
    selboolean { 'virt_use_nfs':
      value      => on,
      persistent => true,
    } -> Package['nfs-utils']
  }

  package {'nfs-utils': } -> Service['nova-compute']
}

include ::nova::compute::libvirt
if hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {
  file {'/etc/libvirt/qemu.conf':
    ensure  => present,
    content => hiera('midonet_libvirt_qemu_data')
  }
}
include ::nova::network::neutron
include ::neutron

# If the value of core plugin is set to 'nuage',
# include nuage agent,
# If the value of core plugin is set to 'midonet',
# include midonet agent,
# else use the default value of 'ml2'
if hiera('neutron::core_plugin') == 'neutron.plugins.nuage.plugin.NuagePlugin' {
  include ::nuage::vrs
  include ::nova::compute::neutron

  class { '::nuage::metadataagent':
    nova_os_tenant_name => hiera('nova::api::admin_tenant_name'),
    nova_os_password    => hiera('nova_password'),
    nova_metadata_ip    => hiera('nova_metadata_node_ips'),
    nova_auth_ip        => hiera('keystone_public_api_virtual_ip'),
  }
} elsif hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {

  # TODO(devvesa) provide non-controller ips for these services
  $zookeeper_node_ips = hiera('neutron_api_node_ips')
  $cassandra_node_ips = hiera('neutron_api_node_ips')

  class {'::tripleo::network::midonet::agent':
    zookeeper_servers => $zookeeper_node_ips,
    cassandra_seeds   => $cassandra_node_ips
  }
} else {
  include ::neutron::plugins::ml2
  include ::neutron::agents::ml2::ovs

  if 'cisco_n1kv' in hiera('neutron::plugins::ml2::mechanism_drivers') {
    class { '::neutron::agents::n1kv_vem':
      n1kv_source  => hiera('n1kv_vem_source', undef),
      n1kv_version => hiera('n1kv_vem_version', undef),
    }
  }

  if 'bsn_ml2' in hiera('neutron::plugins::ml2::mechanism_drivers') {
    include ::neutron::agents::bigswitch
  }
}


include ::ceilometer
include ::ceilometer::config
include ::ceilometer::agent::compute
include ::ceilometer::agent::auth

$snmpd_user = hiera('snmpd_readonly_user_name')
snmp::snmpv3_user { $snmpd_user:
  authtype => 'MD5',
  authpass => hiera('snmpd_readonly_user_password'),
}
class { '::snmp':
  agentaddress => ['udp:161','udp6:[::1]:161'],
  snmpd_config => [ join(['rouser ', hiera('snmpd_readonly_user_name')]), 'proc  cron', 'includeAllDisks  10%', 'master agentx', 'trapsink localhost public', 'iquerySecName internalUser', 'rouser internalUser', 'defaultMonitors yes', 'linkUpDownNotifications yes' ],
}

hiera_include('compute_classes')
package_manifest{'/var/lib/tripleo/installed-packages/overcloud_compute': ensure => present}
