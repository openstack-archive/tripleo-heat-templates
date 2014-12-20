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

if hiera('step') >= 1 {

  # TODO Galara
  class { 'mysql::server':
    override_options => {
      'mysqld' => {
        'bind-address' => hiera('controller_host')
      }
    }
  }

  # FIXME: this should only occur on the bootstrap host (ditto for db syncs)
  # Create all the database schemas
  # Example DSN format: mysql://user:password@host/dbname
  $allowed_hosts = ['%',hiera('controller_host')]
  $keystone_dsn = split(hiera('keystone::database_connection'), '[@:/?]')
  class { 'keystone::db::mysql':
    user          => $keystone_dsn[3],
    password      => $keystone_dsn[4],
    host          => $keystone_dsn[5],
    dbname        => $keystone_dsn[6],
    allowed_hosts => $allowed_hosts,
  }
  $glance_dsn = split(hiera('glance::api::database_connection'), '[@:/?]')
  class { 'glance::db::mysql':
    user          => $glance_dsn[3],
    password      => $glance_dsn[4],
    host          => $glance_dsn[5],
    dbname        => $glance_dsn[6],
    allowed_hosts => $allowed_hosts,
  }
  $nova_dsn = split(hiera('nova::database_connection'), '[@:/?]')
  class { 'nova::db::mysql':
    user          => $nova_dsn[3],
    password      => $nova_dsn[4],
    host          => $nova_dsn[5],
    dbname        => $nova_dsn[6],
    allowed_hosts => $allowed_hosts,
  }
  $neutron_dsn = split(hiera('neutron::server::database_connection'), '[@:/?]')
  class { 'neutron::db::mysql':
    user          => $neutron_dsn[3],
    password      => $neutron_dsn[4],
    host          => $neutron_dsn[5],
    dbname        => $neutron_dsn[6],
    allowed_hosts => $allowed_hosts,
  }
  $cinder_dsn = split(hiera('cinder::database_connection'), '[@:/?]')
  class { 'cinder::db::mysql':
    user          => $cinder_dsn[3],
    password      => $cinder_dsn[4],
    host          => $cinder_dsn[5],
    dbname        => $cinder_dsn[6],
    allowed_hosts => $allowed_hosts,
  }
  $heat_dsn = split(hiera('heat_dsn'), '[@:/?]')
  class { 'heat::db::mysql':
    user          => $heat_dsn[3],
    password      => $heat_dsn[4],
    host          => $heat_dsn[5],
    dbname        => $heat_dsn[6],
    allowed_hosts => $allowed_hosts,
  }

  if $::osfamily == 'RedHat' {
    $rabbit_provider = 'yum'
  } else {
    $rabbit_provider = undef
  }

  Class['rabbitmq'] -> Rabbitmq_vhost <| |>
  Class['rabbitmq'] -> Rabbitmq_user <| |>
  Class['rabbitmq'] -> Rabbitmq_user_permissions <| |>

  # TODO Rabbit HA
  class { 'rabbitmq':
    package_provider  => $rabbit_provider,
    config_cluster    => false,
    node_ip_address   => hiera('controller_host'),
  }

  rabbitmq_vhost { '/':
    provider => 'rabbitmqctl',
  }
  rabbitmq_user { ['nova','glance','neutron','cinder','ceilometer','heat']:
    admin    => true,
    password => hiera('rabbit_password'),
    provider => 'rabbitmqctl',
  }

  rabbitmq_user_permissions {[
    'nova@/',
    'glance@/',
    'neutron@/',
    'cinder@/',
    'ceilometer@/',
    'heat@/',
  ]:
    configure_permission => '.*',
    write_permission     => '.*',
    read_permission      => '.*',
    provider             => 'rabbitmqctl',
  }

} #END STEP 1

if hiera('step') >= 2 {

  include ::keystone

  #TODO: need a cleanup-keystone-tokens.sh solution here
  keystone_config {
    'ec2/driver': value => 'keystone.contrib.ec2.backends.sql.Ec2';
  }
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

  # TODO: swift backend, also notifications, scrubber, etc.
  include ::glance::api
  include ::glance::registry

  class { 'nova':
    rabbit_hosts           => [hiera('controller_virtual_ip')],
    glance_api_servers     => join([hiera('glance_protocol'), '://', hiera('controller_virtual_ip'), ':', hiera('glance_port')]),
  }

  include ::nova::api
  include ::nova::cert
  include ::nova::conductor
  include ::nova::consoleauth
  include ::nova::vncproxy
  include ::nova::scheduler

  class {'neutron':
    rabbit_hosts => [hiera('controller_virtual_ip')],
  }

  include ::neutron::server
  include ::neutron::agents::dhcp
  include ::neutron::agents::l3

  class { 'neutron::plugins::ml2':
    flat_networks        => split(hiera('neutron_flat_networks'), ','),
    tenant_network_types => [hiera('neutron_tenant_network_type')],
    type_drivers         => [hiera('neutron_tenant_network_type')],
  }

  class { 'neutron::agents::ml2::ovs':
    bridge_mappings  => split(hiera('neutron_bridge_mappings'), ','),
    tunnel_types     => split(hiera('neutron_tunnel_types'), ','),
  }

  class { 'neutron::agents::metadata':
    auth_url => join(['http://', hiera('controller_virtual_ip'), ':35357/v2.0']),
  }

  class {'cinder':
    rabbit_hosts => [hiera('controller_virtual_ip')],
  }

  include ::cinder::api
  include ::cinder::scheduler
  include ::cinder::volume
  include ::cinder::volume::iscsi
  class {'cinder::setup_test_volume':
    size => join([hiera('cinder_lvm_loop_device_size'), 'M']),
  }

} #END STEP 2
