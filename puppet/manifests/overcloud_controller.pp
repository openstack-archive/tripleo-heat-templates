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

include tripleo::packages

if hiera('step') >= 1 {

  create_resources(sysctl::value, hiera('sysctl_settings'), {})

  $controller_node_ips = split(hiera('controller_node_ips'), ',')

  class { '::tripleo::loadbalancer' :
    controller_hosts => $controller_node_ips,
    manage_vip       => true,
  }

}

if hiera('step') >= 2 {

  if count(hiera('ntp::servers')) > 0 {
    include ::ntp
  }

  # MongoDB
  if downcase(hiera('ceilometer_backend')) == 'mongodb' {
    include ::mongodb::globals

    include ::mongodb::server
    $mongo_node_ips_with_port = suffix(hiera('mongo_node_ips'), ':27017')
    $mongo_node_string = join($mongo_node_ips_with_port, ',')

    $mongodb_replset = hiera('mongodb::server::replset')
    $ceilometer_mongodb_conn_string = "mongodb://${mongo_node_string}/ceilometer?replicaSet=${mongodb_replset}"
    if downcase(hiera('bootstrap_nodeid')) == $::hostname {
      mongodb_replset { $mongodb_replset :
        members => $mongo_node_ips_with_port,
      }
    }
  }

  # Redis
  $redis_node_ips = hiera('redis_node_ips')
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
    include ::tripleo::redis_notification
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
        'bind-address' => hiera('mysql_bind_host'),
        'max_connections' => hiera('mysql_max_connections'),
        'open_files_limit' => '-1',
      },
    },
    remove_default_accounts => true,
  }

  # FIXME: this should only occur on the bootstrap host (ditto for db syncs)
  # Create all the database schemas
  include ::keystone::db::mysql
  include ::glance::db::mysql
  include ::nova::db::mysql
  include ::neutron::db::mysql
  include ::cinder::db::mysql
  include ::heat::db::mysql
  if downcase(hiera('ceilometer_backend')) == 'mysql' {
    include ::ceilometer::db::mysql
  }

  $rabbit_nodes = hiera('rabbit_node_ips')
  if count($rabbit_nodes) > 1 {
    class { '::rabbitmq':
      config_cluster          => true,
      cluster_nodes           => $rabbit_nodes,
      tcp_keepalive           => false,
      config_kernel_variables => hiera('rabbitmq_kernel_variables'),
      config_variables        => hiera('rabbitmq_config_variables'),
      environment_variables   => hiera('rabbitmq_environment'),
    }
    rabbitmq_policy { 'ha-all@/':
      pattern    => '^(?!amq\.).*',
      definition => {
        'ha-mode' => 'all',
      },
    }
  } else {
    include ::rabbitmq
  }

  # pre-install swift here so we can build rings
  include ::swift

  $enable_ceph = hiera('ceph_storage_count', 0) > 0

  if $enable_ceph {
    class { 'ceph::profile::params':
      mon_initial_members => downcase(hiera('ceph_mon_initial_members'))
    }
    include ::ceph::profile::mon
  }

  if str2bool(hiera('enable_ceph_storage', 'false')) {
    if str2bool(hiera('ceph_osd_selinux_permissive', true)) {
      exec { 'set selinux to permissive on boot':
        command => "sed -ie 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config",
        onlyif  => "test -f /etc/selinux/config && ! grep '^SELINUX=permissive' /etc/selinux/config",
        path    => ["/usr/bin", "/usr/sbin"],
      }

      exec { 'set selinux to permissive':
        command => "setenforce 0",
        onlyif  => "which setenforce && getenforce | grep -i 'enforcing'",
        path    => ["/usr/bin", "/usr/sbin"],
      } -> Class['ceph::profile::osd']
    }

    include ::ceph::profile::osd
  }

  if str2bool(hiera('enable_external_ceph', 'false')) {
    include ::ceph::profile::client
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

  $glance_backend = downcase(hiera('glance_backend', 'swift'))
  case $glance_backend {
      swift: { $backend_store = 'glance.store.swift.Store' }
      file: { $backend_store = 'glance.store.filesystem.Store' }
      rbd: { $backend_store = 'glance.store.rbd.Store' }
      default: { fail('Unrecognized glance_backend parameter.') }
  }
  $http_store = ['glance.store.http.Store']
  $glance_store = concat($http_store, $backend_store)

  # TODO: notifications, scrubber, etc.
  include ::glance
  class { 'glance::api':
    known_stores => $glance_store
  }
  include ::glance::registry
  include join(['::glance::backend::', $glance_backend])

  class { '::nova' :
    memcached_servers => suffix(hiera('memcache_node_ips'), ':11211'),
  }
  include ::nova::config
  include ::nova::api
  include ::nova::cert
  include ::nova::conductor
  include ::nova::consoleauth
  include ::nova::network::neutron
  include ::nova::vncproxy
  include ::nova::scheduler
  include ::nova::scheduler::filter

  include ::neutron
  include ::neutron::server
  include ::neutron::agents::l3
  include ::neutron::agents::dhcp
  include ::neutron::agents::metadata

  file { '/etc/neutron/dnsmasq-neutron.conf':
    content => hiera('neutron_dnsmasq_options'),
    owner   => 'neutron',
    group   => 'neutron',
    notify  => Service['neutron-dhcp-service'],
    require => Package['neutron'],
  }

  class { 'neutron::plugins::ml2':
    flat_networks => split(hiera('neutron_flat_networks'), ','),
    tenant_network_types => [hiera('neutron_tenant_network_type')],
    mechanism_drivers   => [hiera('neutron_mechanism_drivers')],
  }
  class { 'neutron::agents::ml2::ovs':
    bridge_mappings => split(hiera('neutron_bridge_mappings'), ','),
    tunnel_types => split(hiera('neutron_tunnel_types'), ','),
  }
  if 'cisco_n1kv' in hiera('neutron_mechanism_drivers') {
    include neutron::plugins::ml2::cisco::nexus1000v

    class { 'neutron::agents::n1kv_vem':
      n1kv_source          => hiera('n1kv_vem_source', undef),
      n1kv_version         => hiera('n1kv_vem_version', undef),
    }

    class { 'n1k_vsm':
      n1kv_source       => hiera('n1kv_vsm_source', undef),
      n1kv_version      => hiera('n1kv_vsm_version', undef),
      pacemaker_control => false,
    }
  }

  if 'cisco_ucsm' in hiera('neutron_mechanism_drivers') {
    include ::neutron::plugins::ml2::cisco::ucsm
  }
  if 'cisco_nexus' in hiera('neutron_mechanism_drivers') {
    include ::neutron::plugins::ml2::cisco::nexus
    include ::neutron::plugins::ml2::cisco::type_nexus_vxlan
  }

  if hiera('neutron_enable_bigswitch_ml2', false) {
    include neutron::plugins::ml2::bigswitch::restproxy
  }
  neutron_l3_agent_config {
    'DEFAULT/ovs_use_veth': value => hiera('neutron_ovs_use_veth', false);
  }
  neutron_dhcp_agent_config {
    'DEFAULT/ovs_use_veth': value => hiera('neutron_ovs_use_veth', false);
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

    $cinder_pool_requires = [Ceph::Pool['volumes']]

  } else {
    $cinder_pool_requires = []
  }

  if hiera('cinder_enable_rbd_backend', false) {
    $cinder_rbd_backend = 'tripleo_ceph'

    cinder::backend::rbd { $cinder_rbd_backend :
      rbd_pool        => 'volumes',
      rbd_user        => 'openstack',
      rbd_secret_uuid => hiera('ceph::profile::params::fsid'),
      require         => $cinder_pool_requires,
    }
  }

  if hiera('cinder_enable_netapp_backend', false) {
    $cinder_netapp_backend = hiera('cinder::backend::netapp::title')

    cinder_config {
      "${cinder_netapp_backend}/host": value => 'hostgroup';
    }

    if hiera('cinder::backend::netapp::nfs_shares', undef) {
      $cinder_netapp_nfs_shares = split(hiera('cinder::backend::netapp::nfs_shares', undef), ',')
    }

    cinder::backend::netapp { $cinder_netapp_backend :
      netapp_login                 => hiera('cinder::backend::netapp::netapp_login', undef),
      netapp_password              => hiera('cinder::backend::netapp::netapp_password', undef),
      netapp_server_hostname       => hiera('cinder::backend::netapp::netapp_server_hostname', undef),
      netapp_server_port           => hiera('cinder::backend::netapp::netapp_server_port', undef),
      netapp_size_multiplier       => hiera('cinder::backend::netapp::netapp_size_multiplier', undef),
      netapp_storage_family        => hiera('cinder::backend::netapp::netapp_storage_family', undef),
      netapp_storage_protocol      => hiera('cinder::backend::netapp::netapp_storage_protocol', undef),
      netapp_transport_type        => hiera('cinder::backend::netapp::netapp_transport_type', undef),
      netapp_vfiler                => hiera('cinder::backend::netapp::netapp_vfiler', undef),
      netapp_volume_list           => hiera('cinder::backend::netapp::netapp_volume_list', undef),
      netapp_vserver               => hiera('cinder::backend::netapp::netapp_vserver', undef),
      netapp_partner_backend_name  => hiera('cinder::backend::netapp::netapp_partner_backend_name', undef),
      nfs_shares                   => $cinder_netapp_nfs_shares,
      nfs_shares_config            => hiera('cinder::backend::netapp::nfs_shares_config', undef),
      netapp_copyoffload_tool_path => hiera('cinder::backend::netapp::netapp_copyoffload_tool_path', undef),
      netapp_controller_ips        => hiera('cinder::backend::netapp::netapp_controller_ips', undef),
      netapp_sa_password           => hiera('cinder::backend::netapp::netapp_sa_password', undef),
      netapp_storage_pools         => hiera('cinder::backend::netapp::netapp_storage_pools', undef),
      netapp_eseries_host_type     => hiera('cinder::backend::netapp::netapp_eseries_host_type', undef),
      netapp_webservice_path       => hiera('cinder::backend::netapp::netapp_webservice_path', undef),
    }
  }

  if hiera('cinder_enable_nfs_backend', false) {
    $cinder_nfs_backend = 'tripleo_nfs'

    if ($::selinux != "false") {
      selboolean { 'virt_use_nfs':
          value => on,
          persistent => true,
      } -> Package['nfs-utils']
    }

    package {'nfs-utils': } ->
    cinder::backend::nfs { $cinder_nfs_backend :
      nfs_servers         => hiera('cinder_nfs_servers'),
      nfs_mount_options   => hiera('cinder_nfs_mount_options'),
      nfs_shares_config   => '/etc/cinder/shares-nfs.conf',
    }
  }

  $cinder_enabled_backends = delete_undef_values([$cinder_iscsi_backend, $cinder_rbd_backend, $cinder_netapp_backend, $cinder_nfs_backend])
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
  include ::swift::proxy::ratelimit
  include ::swift::proxy::catch_errors
  include ::swift::proxy::tempurl
  include ::swift::proxy::formpost

  # swift storage
  if str2bool(hiera('enable_swift_storage', 'true')) {
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
  }

  # Ceilometer
  $ceilometer_backend = downcase(hiera('ceilometer_backend'))
  case $ceilometer_backend {
    /mysql/ : {
      $ceilometer_database_connection = hiera('ceilometer_mysql_conn_string')
    }
    default : {
      $ceilometer_database_connection = $ceilometer_mongodb_conn_string
    }
  }
  include ::ceilometer
  include ::ceilometer::config
  include ::ceilometer::api
  include ::ceilometer::agent::notification
  include ::ceilometer::agent::central
  include ::ceilometer::alarm::notifier
  include ::ceilometer::alarm::evaluator
  include ::ceilometer::expirer
  include ::ceilometer::collector
  include ceilometer::agent::auth
  class { '::ceilometer::db' :
    database_connection => $ceilometer_database_connection,
  }

  Cron <| title == 'ceilometer-expirer' |> { command => "sleep $((\$(od -A n -t d -N 3 /dev/urandom) % 86400)) && ${::ceilometer::params::expirer_command}" }

  # Heat
  include ::heat
  include ::heat::api
  include ::heat::api_cfn
  include ::heat::api_cloudwatch
  include ::heat::engine

  # Horizon
  if 'cisco_n1kv' in hiera('neutron_mechanism_drivers') {
    $_profile_support = 'cisco'
  } else {
    $_profile_support = 'None'
  }
  $neutron_options   = {'profile_support' => $_profile_support }
  $vhost_params = { add_listen => false }
  class { 'horizon':
    cache_server_ip    => hiera('memcache_node_ips', '127.0.0.1'),
    vhost_extra_params => $vhost_params,
    neutron_options    => $neutron_options,
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

  hiera_include('controller_classes')

} #END STEP 3

if hiera('step') >= 4 {
  include ::keystone::cron::token_flush
} #END STEP 4

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_controller', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}
