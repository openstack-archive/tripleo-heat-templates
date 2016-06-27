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

# This puppet manifest is to be used only during a Liberty->Mitaka upgrade
# It configures keystone to be run under httpd but it makes sure to not
# restart any services. This snippet needs to be called after the
# major-upgrade-pacemaker-init.yaml step because that pushes new hiera data
# on the nodes and before the major-upgrade-pacemaker.yaml

Service <|
  tag == 'keystone-service'
|> {
  hasrestart => true,
  restart    => '/bin/true',
  start      => '/bin/true',
  stop       => '/bin/true',
}

if $::hostname == downcase(hiera('bootstrap_nodeid')) {
  $pacemaker_master = true
  $sync_db = true
} else {
  $pacemaker_master = false
  $sync_db = false
}

include ::tripleo::packages

class { '::keystone':
  sync_db        => $sync_db,
  manage_service => false,
  enabled        => false,
  # This parameter does not exist in liberty puppet modules
  #enable_bootstrap => $pacemaker_master,
}

include ::keystone::config

file { [ '/etc/keystone/ssl', '/etc/keystone/ssl/certs', '/etc/keystone/ssl/private' ]:
  ensure  => 'directory',
  owner   => 'keystone',
  group   => 'keystone',
  require => Package['keystone'],
}
file { '/etc/keystone/ssl/certs/signing_cert.pem':
  content => hiera('keystone_signing_certificate'),
  owner   => 'keystone',
  group   => 'keystone',
  notify  => Service['keystone'],
  require => File['/etc/keystone/ssl/certs'],
}
file { '/etc/keystone/ssl/private/signing_key.pem':
  content => hiera('keystone_signing_key'),
  owner   => 'keystone',
  group   => 'keystone',
  notify  => Service['keystone'],
  require => File['/etc/keystone/ssl/private'],
}
file { '/etc/keystone/ssl/certs/ca.pem':
  content => hiera('keystone_ca_certificate'),
  owner   => 'keystone',
  group   => 'keystone',
  notify  => Service['keystone'],
  require => File['/etc/keystone/ssl/certs'],
}

class { '::apache' :
  service_enable  => false,
  # This needs to be true otherwise keystone_config won't find service
  service_manage  => true,
  # we must not restart httpd at this stage of the upgrade
  service_restart => '/bin/true',
  purge_configs   => false,
  purge_vhost_dir => false,
}


# Needed to make sure we do not disable the aodh ports
include ::aodh::wsgi::apache
include ::keystone::wsgi::apache
