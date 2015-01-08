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

class { 'nova':
  glance_api_servers => join([hiera('glance_protocol'), '://', hiera('glance_host'), ':', hiera('glance_port')]),
}

file { ['/etc/libvirt/qemu/networks/autostart/default.xml',
        '/etc/libvirt/qemu/networks/default.xml']:
  ensure => absent,
  before => Service['libvirt']
}

include ::nova::compute

nova_config {
  'DEFAULT/my_ip':                     value => $ipaddress;
  'DEFAULT/linuxnet_interface_driver': value => 'nova.network.linux_net.LinuxOVSInterfaceDriver';
}

include ::nova::compute::libvirt

class { 'nova::network::neutron':
  neutron_admin_auth_url => join(['http://', hiera('neutron_host'), ':35357/v2.0']),
  neutron_url            => join(['http://', hiera('neutron_host'), ':9696']),
}

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
