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

if hiera('step') >= 1 {

  $controller_node_ips = split(hiera('controller_node_ips'), ',')
  $enable_pacemaker = str2bool(hiera('enable_pacemaker'))
  $enable_keepalived = !$enable_pacemaker

  class { '::tripleo::loadbalancer' :
    controller_hosts => $controller_node_ips,
  }

  if $enable_pacemaker {
    $pacemaker_cluster_members = regsubst(hiera('controller_node_ips'), ',', ' ', 'G')
    if $::hostname == downcase(hiera('bootstrap_nodeid')) {
      $pacemaker_master = true
    } else {
      $pacemaker_master = false
    }
    user { 'hacluster':
     ensure => present,
    } ->
    class { '::pacemaker':
      hacluster_pwd => hiera('hacluster_pwd'),
    } ->
    class { '::pacemaker::corosync':
      cluster_members => $pacemaker_cluster_members,
      setup_cluster   => $pacemaker_master,
    }
    class { '::pacemaker::stonith':
      disable => true,
    }
  }

}

if hiera('step') >= 2 {

  if count(hiera('ntp::servers')) > 0 {
    include ::ntp
  }

  # MongoDB
  include ::mongodb::globals
  include ::mongodb::server
  $mongo_node_ips = split(hiera('mongo_node_ips'), ',')
  $mongo_node_ips_with_port = suffix($mongo_node_ips, ':27017')
  $mongo_node_string = join($mongo_node_ips_with_port, ',')

  $mongodb_replset = hiera('mongodb::server::replset')
  $ceilometer_mongodb_conn_string = "mongodb://${mongo_node_string}/ceilometer?replicaSet=${mongodb_replset}"
  if downcase(hiera('bootstrap_nodeid')) == $::hostname {
    mongodb_replset { $mongodb_replset :
      members => $mongo_node_ips_with_port,
    }
  }

  # Redis
  $redis_node_ips = split(hiera('redis_node_ips'), ',')
  $redis_master_hostname = downcase(hiera('bootstrap_nodeid'))

  if $redis_master_hostname == $::hostname {
    $slaveof = undef
  } else {
    $slaveof = "${redis_master_hostname} 6379"
  }
  class {'::redis' :
    slaveof => $slaveof,
  }

  if count($redis_node_ips) > 1 {
    Class['::tripleo::redis_notification'] -> Service['redis-sentinel']
    include ::redis::sentinel
    class {'::tripleo::redis_notification' :
      haproxy_monitor_ip => hiera('tripleo::loadbalancer::controller_virtual_ip'),
    }
  }

  if str2bool(hiera('enable_galera', 'true')) {
    $mysql_config_file = '/etc/my.cnf.d/galera.cnf'
  } else {
    $mysql_config_file = '/etc/my.cnf.d/server.cnf'
  }
  # TODO Galara
  class { 'mysql::server':
    config_file => $mysql_config_file,
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
  $heat_dsn = split(hiera('heat::database_connection'), '[@:/?]')
  class { 'heat::db::mysql':
    user          => $heat_dsn[3],
    password      => $heat_dsn[4],
    host          => $heat_dsn[5],
    dbname        => $heat_dsn[6],
    allowed_hosts => $allowed_hosts,
  }

  $rabbit_nodes = split(downcase(hiera('rabbit_node_names', $::hostname)), ',')
  if count($rabbit_nodes) > 1 {
    $rabbit_cluster = true
  }
  else {
    $rabbit_cluster = false
  }
  class { 'rabbitmq':
    config_cluster   => $rabbit_cluster,
    cluster_nodes    => $rabbit_nodes,
    node_ip_address  => hiera('controller_host'),
  }
  if $rabbit_cluster {
    rabbitmq_policy { 'ha-all@/':
      pattern    => '^(?!amq\.).*',
      definition => {
        'ha-mode'      => 'all',
        'ha-sync-mode' => 'automatic',
      },
    }
  }
  rabbitmq_vhost { '/':
    provider => 'rabbitmqctl',
  }

  # pre-install swift here so we can build rings
  include ::swift

  $cinder_enable_rbd_backend = hiera('cinder_enable_rbd_backend', false)
  $enable_ceph = $cinder_enable_rbd_backend

  if $enable_ceph {
    class { 'ceph::profile::params':
      mon_initial_members => downcase(hiera('ceph_mon_initial_members'))
    }
    include ::ceph::profile::mon
  }

} #END STEP 2

if hiera('step') >= 3 {

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

  # TODO: notifications, scrubber, etc.
  include ::glance
  include ::glance::api
  include ::glance::registry
  include ::glance::backend::swift

  class { 'nova':
    glance_api_servers     => join([hiera('glance_protocol'), '://', hiera('controller_virtual_ip'), ':', hiera('glance_port')]),
  }

  include ::nova::api
  include ::nova::cert
  include ::nova::conductor
  include ::nova::consoleauth
  include ::nova::network::neutron
  include ::nova::vncproxy
  include ::nova::scheduler

  include ::neutron
  include ::neutron::server
  include ::neutron::agents::dhcp
  include ::neutron::agents::l3

  file { '/etc/neutron/dnsmasq-neutron.conf':
    content => hiera('neutron_dnsmasq_options'),
    owner   => 'neutron',
    group   => 'neutron',
    notify  => Service['neutron-dhcp-service'],
    require => Package['neutron'],
  }

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

  Service['neutron-server'] -> Service['neutron-dhcp-service']
  Service['neutron-server'] -> Service['neutron-l3']
  Service['neutron-server'] -> Service['neutron-ovs-agent-service']
  Service['neutron-server'] -> Service['neutron-metadata']

  include ::cinder
  include ::cinder::api
  include ::cinder::glance
  include ::cinder::scheduler
  include ::cinder::volume
  class {'cinder::setup_test_volume':
    size => join([hiera('cinder_lvm_loop_device_size'), 'M']),
  }

  $cinder_enable_iscsi = hiera('cinder_enable_iscsi_backend', true)
  if $cinder_enable_iscsi {
    $cinder_iscsi_backend = 'tripleo_iscsi'

    cinder::backend::iscsi { $cinder_iscsi_backend :
      iscsi_ip_address => hiera('cinder_iscsi_ip_address'),
      iscsi_helper     => hiera('cinder_iscsi_helper'),
    }
  }

  if $enable_ceph {

    Ceph_pool {
      pg_num  => hiera('ceph::profile::params::osd_pool_default_pg_num'),
      pgp_num => hiera('ceph::profile::params::osd_pool_default_pgp_num'),
      size    => hiera('ceph::profile::params::osd_pool_default_size'),
    }

    $ceph_pools = hiera('ceph_pools')
    ceph::pool { $ceph_pools : }
  }

  if $cinder_enable_rbd_backend {
    $cinder_rbd_backend = 'tripleo_ceph'

    cinder_config {
      "${cinder_rbd_backend}/host": value => 'hostgroup';
    }

    cinder::backend::rbd { $cinder_rbd_backend :
      rbd_pool        => 'volumes',
      rbd_user        => 'openstack',
      rbd_secret_uuid => hiera('ceph::profile::params::fsid'),
      require         => Ceph::Pool['volumes'],
    }
  }

  $cinder_enabled_backends = delete_undef_values([$cinder_iscsi_backend, $cinder_rbd_backend])
  class { '::cinder::backends' :
    enabled_backends => $cinder_enabled_backends,
  }

  # swift proxy
  include ::memcached
  include ::swift::proxy
  include ::swift::proxy::proxy_logging
  include ::swift::proxy::healthcheck
  include ::swift::proxy::cache
  include ::swift::proxy::keystone
  include ::swift::proxy::authtoken
  include ::swift::proxy::staticweb
  include ::swift::proxy::ceilometer
  include ::swift::proxy::ratelimit
  include ::swift::proxy::catch_errors
  include ::swift::proxy::tempurl
  include ::swift::proxy::formpost

  # swift storage
  class {'swift::storage::all':
    mount_check => str2bool(hiera('swift_mount_check'))
  }
  if(!defined(File['/srv/node'])) {
    file { '/srv/node':
      ensure  => directory,
      owner   => 'swift',
      group   => 'swift',
      require => Package['openstack-swift'],
    }
  }
  $swift_components = ['account', 'container', 'object']
  swift::storage::filter::recon { $swift_components : }
  swift::storage::filter::healthcheck { $swift_components : }

  # Ceilometer
  include ::ceilometer
  include ::ceilometer::api
  include ::ceilometer::agent::notification
  include ::ceilometer::agent::central
  include ::ceilometer::alarm::notifier
  include ::ceilometer::alarm::evaluator
  include ::ceilometer::expirer
  include ::ceilometer::collector
  class { '::ceilometer::db' :
    database_connection => $ceilometer_mongodb_conn_string,
  }
  class { 'ceilometer::agent::auth':
    auth_url => join(['http://', hiera('controller_virtual_ip'), ':5000/v2.0']),
  }

  Cron <| title == 'ceilometer-expirer' |> { command => "sleep $((\$(od -A n -t d -N 3 /dev/urandom) % 86400)) && ${::ceilometer::params::expirer_command}" }

  # Heat
  include ::heat
  include ::heat::api
  include ::heat::api_cfn
  include ::heat::api_cloudwatch
  include ::heat::engine

  $snmpd_user = hiera('snmpd_readonly_user_name')
  snmp::snmpv3_user { $snmpd_user:
    authtype => 'MD5',
    authpass => hiera('snmpd_readonly_user_password'),
  }
  class { 'snmp':
    agentaddress => ['udp:161','udp6:[::1]:161'],
    snmpd_config => [ join(['rouser ', hiera('snmpd_readonly_user_name')]), 'proc  cron', 'includeAllDisks  10%', 'master agentx', 'trapsink localhost public', 'iquerySecName internalUser', 'rouser internalUser', 'defaultMonitors yes', 'linkUpDownNotifications yes' ],
  }

} #END STEP 3
