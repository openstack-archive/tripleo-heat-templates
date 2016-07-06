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

  if hiera('neutron::core_plugin') == 'neutron_plugin_contrail.plugins.opencontrail.contrail_plugin.NeutronPluginContrailCoreV2' {

    include ::contrail::vrouter
    # NOTE: it's not possible to use this class without a functional
    # contrail controller up and running
    #class {'::contrail::vrouter::provision_vrouter':
    #  require => Class['contrail::vrouter'],
    #}
  }

  include ::ceilometer
  include ::ceilometer::config
  include ::ceilometer::agent::compute
  include ::ceilometer::agent::auth

  hiera_include('compute_classes')
}

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_compute', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}
