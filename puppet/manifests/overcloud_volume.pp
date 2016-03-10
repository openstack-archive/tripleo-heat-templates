# Copyright 2015 Red Hat, Inc.
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

include ::cinder
include ::cinder::config
include ::cinder::glance
include ::cinder::volume
include ::cinder::setup_test_volume

$cinder_enable_iscsi = hiera('cinder_enable_iscsi_backend', true)
if $cinder_enable_iscsi {
  $cinder_iscsi_backend = 'tripleo_iscsi'

  cinder::backend::iscsi { $cinder_iscsi_backend :
    iscsi_ip_address => hiera('cinder_iscsi_ip_address'),
    iscsi_helper     => hiera('cinder_iscsi_helper'),
  }
}

$cinder_enabled_backends = any2array($cinder_iscsi_backend)
class { '::cinder::backends' :
  enabled_backends => union($cinder_enabled_backends, hiera('cinder_user_enabled_backends')),
}

$snmpd_user = hiera('snmpd_readonly_user_name')
snmp::snmpv3_user { $snmpd_user:
  authtype => 'MD5',
  authpass => hiera('snmpd_readonly_user_password'),
}
class { '::snmp':
  agentaddress => ['udp:161','udp6:[::1]:161'],
  snmpd_config => [ join(['createUser ', hiera('snmpd_readonly_user_name'), ' MD5 "', hiera('snmpd_readonly_user_password'), '"']), join(['rouser ', hiera('snmpd_readonly_user_name')]), 'proc  cron', 'includeAllDisks  10%', 'master agentx', 'trapsink localhost public', 'iquerySecName internalUser', 'rouser internalUser', 'defaultMonitors yes', 'linkUpDownNotifications yes' ],
}

hiera_include('volume_classes')
package_manifest{'/var/lib/tripleo/installed-packages/overcloud_volume': ensure => present}
