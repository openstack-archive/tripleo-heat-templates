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

create_resources(kmod::load, hiera('kernel_modules'), { })
create_resources(sysctl::value, hiera('sysctl_settings'), { })
Exec <| tag == 'kmod::load' |>  -> Sysctl <| |>

if hiera('step') >= 4 {

  # When utilising images for deployment, we need to reset the iSCSI initiator name to make it unique
  exec { 'reset-iscsi-initiator-name':
    command => '/bin/echo InitiatorName=$(/usr/sbin/iscsi-iname) > /etc/iscsi/initiatorname.iscsi',
    onlyif  => '/usr/bin/test ! -f /etc/iscsi/.initiator_reset',
  }->

  file { '/etc/iscsi/.initiator_reset':
    ensure => present,
  }

  nova_config {
    'DEFAULT/my_ip': value => $ipaddress;
    'DEFAULT/linuxnet_interface_driver': value => 'nova.network.linux_net.LinuxOVSInterfaceDriver';
  }

  if hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {
    file { '/etc/libvirt/qemu.conf':
      ensure  => present,
      content => hiera('midonet_libvirt_qemu_data')
    }
  }

  include ::neutron
  include ::neutron::config

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
  }
  elsif hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {

    # TODO(devvesa) provide non-controller ips for these services
    $zookeeper_node_ips = hiera('neutron_api_node_ips')
    $cassandra_node_ips = hiera('neutron_api_node_ips')

    class { '::tripleo::network::midonet::agent':
      zookeeper_servers => $zookeeper_node_ips,
      cassandra_seeds   => $cassandra_node_ips
    }
  }
  elsif hiera('neutron::core_plugin') == 'neutron_plugin_contrail.plugins.opencontrail.contrail_plugin.NeutronPluginContrailCoreV2' {

    include ::contrail::vrouter
    # NOTE: it's not possible to use this class without a functional
    # contrail controller up and running
    #class {'::contrail::vrouter::provision_vrouter':
    #  require => Class['contrail::vrouter'],
    #}
  }
  elsif hiera('neutron::core_plugin') == 'networking_plumgrid.neutron.plugins.plugin.NeutronPluginPLUMgridV2' {
    # forward all ipv4 traffic
    # this is required for the vms to pass through the gateways public interface
    sysctl::value { 'net.ipv4.ip_forward': value => '1' }

    # ifc_ctl_pp needs to be invoked by root as part of the vif.py when a VM is powered on
    file { '/etc/sudoers.d/ifc_ctl_sudoers':
      ensure  => file,
      owner   => root,
      group   => root,
      mode    => '0440',
      content => "nova ALL=(root) NOPASSWD: /opt/pg/bin/ifc_ctl_pp *\n",
    }
  }
  else {

    # NOTE: this code won't live in puppet-neutron until Neutron OVS agent
    # can be gracefully restarted. See https://review.openstack.org/#/c/297211
    # In the meantime, it's safe to restart the agent on each change in neutron.conf,
    # because Puppet changes are supposed to be done during bootstrap and upgrades.
    # Some resource managed by Neutron_config (like messaging and logging options) require
    # a restart of OVS agent. This code does it.
    # In Newton, OVS agent will be able to be restarted gracefully so we'll drop the code
    # from here and fix it in puppet-neutron.
    Neutron_config<||> ~> Service['neutron-ovs-agent-service']

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

  hiera_include('compute_classes')
}

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_compute', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}
