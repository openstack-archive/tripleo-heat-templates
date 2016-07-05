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

Pcmk_resource <| |> {
  tries     => 10,
  try_sleep => 3,
}

# TODO(jistr): use pcs resource provider instead of just no-ops
Service <|
  tag == 'aodh-service' or
  tag == 'ceilometer-service' or
  tag == 'gnocchi-service'
|> {
  hasrestart => true,
  restart    => '/bin/true',
  start      => '/bin/true',
  stop       => '/bin/true',
}

include ::tripleo::packages
include ::tripleo::firewall

if $::hostname == downcase(hiera('bootstrap_nodeid')) {
  $pacemaker_master = true
  $sync_db = true
} else {
  $pacemaker_master = false
  $sync_db = false
}

$enable_fencing = str2bool(hiera('enable_fencing', false)) and hiera('step') >= 5
$enable_load_balancer = hiera('enable_load_balancer', true)

# When to start and enable services which haven't been Pacemakerized
# FIXME: remove when we start all OpenStack services using Pacemaker
# (occurrences of this variable will be gradually replaced with false)
$non_pcmk_start = hiera('step') >= 5

if hiera('step') >= 1 {

  create_resources(kmod::load, hiera('kernel_modules'), {})
  create_resources(sysctl::value, hiera('sysctl_settings'), {})
  Exec <| tag == 'kmod::load' |>  -> Sysctl <| |>

  $pacemaker_cluster_members = downcase(regsubst(hiera('controller_node_names'), ',', ' ', 'G'))
  $corosync_ipv6 = str2bool(hiera('corosync_ipv6', false))
  if $corosync_ipv6 {
    $cluster_setup_extras = { '--token' => hiera('corosync_token_timeout', 1000), '--ipv6' => '' }
  } else {
    $cluster_setup_extras = { '--token' => hiera('corosync_token_timeout', 1000) }
  }
  class { '::pacemaker':
    hacluster_pwd => hiera('hacluster_pwd'),
  } ->
  class { '::pacemaker::corosync':
    cluster_members      => $pacemaker_cluster_members,
    setup_cluster        => $pacemaker_master,
    cluster_setup_extras => $cluster_setup_extras,
  }
  class { '::pacemaker::stonith':
    disable => !$enable_fencing,
  }
  if $enable_fencing {
    include ::tripleo::fencing

    # enable stonith after all Pacemaker resources have been created
    Pcmk_resource<||> -> Class['tripleo::fencing']
    Pcmk_constraint<||> -> Class['tripleo::fencing']
    Exec <| tag == 'pacemaker_constraint' |> -> Class['tripleo::fencing']
    # enable stonith after all fencing devices have been created
    Class['tripleo::fencing'] -> Class['pacemaker::stonith']
  }

  # FIXME(gfidente): sets 200secs as default start timeout op
  # param; until we can use pcmk global defaults we'll still
  # need to add it to every resource which redefines op params
  Pacemaker::Resource::Service {
    op_params => 'start timeout=200s stop timeout=200s',
  }

  if downcase(hiera('ceilometer_backend')) == 'mongodb' {
    include ::mongodb::params
  }

  # Galera
  if str2bool(hiera('enable_galera', true)) {
    $mysql_config_file = '/etc/my.cnf.d/galera.cnf'
  } else {
    $mysql_config_file = '/etc/my.cnf.d/server.cnf'
  }
  $galera_nodes = downcase(hiera('galera_node_names', $::hostname))
  $galera_nodes_count = count(split($galera_nodes, ','))

  # FIXME: due to https://bugzilla.redhat.com/show_bug.cgi?id=1298671 we
  # set bind-address to a hostname instead of an ip address; to move Mysql
  # from internal_api on another network we'll have to customize both
  # MysqlNetwork and ControllerHostnameResolveNetwork in ServiceNetMap
  $mysql_bind_host = hiera('mysql_bind_host')
  $mysqld_options = {
    'mysqld' => {
      'skip-name-resolve'             => '1',
      'binlog_format'                 => 'ROW',
      'default-storage-engine'        => 'innodb',
      'innodb_autoinc_lock_mode'      => '2',
      'innodb_locks_unsafe_for_binlog'=> '1',
      'query_cache_size'              => '0',
      'query_cache_type'              => '0',
      'bind-address'                  => $::hostname,
      'max_connections'               => hiera('mysql_max_connections'),
      'open_files_limit'              => '-1',
      'wsrep_on'                      => 'ON',
      'wsrep_provider'                => '/usr/lib64/galera/libgalera_smm.so',
      'wsrep_cluster_name'            => 'galera_cluster',
      'wsrep_cluster_address'         => "gcomm://${galera_nodes}",
      'wsrep_slave_threads'           => '1',
      'wsrep_certify_nonPK'           => '1',
      'wsrep_max_ws_rows'             => '131072',
      'wsrep_max_ws_size'             => '1073741824',
      'wsrep_debug'                   => '0',
      'wsrep_convert_LOCK_to_trx'     => '0',
      'wsrep_retry_autocommit'        => '1',
      'wsrep_auto_increment_control'  => '1',
      'wsrep_drupal_282555_workaround'=> '0',
      'wsrep_causal_reads'            => '0',
      'wsrep_sst_method'              => 'rsync',
      'wsrep_provider_options'        => "gmcast.listen_addr=tcp://[${mysql_bind_host}]:4567;",
    },
  }

  class { '::mysql::server':
    create_root_user        => false,
    create_root_my_cnf      => false,
    config_file             => $mysql_config_file,
    override_options        => $mysqld_options,
    remove_default_accounts => $pacemaker_master,
    service_manage          => false,
    service_enabled         => false,
  }

}

if hiera('step') >= 2 {


  # NOTE(gfidente): the following vars are needed on all nodes so they
  # need to stay out of pacemaker_master conditional.
  # The addresses mangling will hopefully go away when we'll be able to
  # configure the connection string via hostnames, until then, we need to pass
  # the list of IPv6 addresses *with* port and without the brackets as 'members'
  # argument for the 'mongodb_replset' resource.
  if str2bool(hiera('mongodb::server::ipv6', false)) {
    $mongo_node_ips_with_port_prefixed = prefix(hiera('mongo_node_ips'), '[')
    $mongo_node_ips_with_port = suffix($mongo_node_ips_with_port_prefixed, ']:27017')
    $mongo_node_ips_with_port_nobr = suffix(hiera('mongo_node_ips'), ':27017')
  } else {
    $mongo_node_ips_with_port = suffix(hiera('mongo_node_ips'), ':27017')
    $mongo_node_ips_with_port_nobr = suffix(hiera('mongo_node_ips'), ':27017')
  }
  $mongodb_replset = hiera('mongodb::server::replset')

  if $pacemaker_master {

    include ::pacemaker::resource_defaults

    # Create an openstack-core dummy resource. See RHBZ 1290121
    pacemaker::resource::ocf { 'openstack-core':
      ocf_agent_name => 'heartbeat:Dummy',
      clone_params   => true,
    }

    pacemaker::resource::ocf { 'galera' :
      ocf_agent_name  => 'heartbeat:galera',
      op_params       => 'promote timeout=300s on-fail=block',
      master_params   => '',
      meta_params     => "master-max=${galera_nodes_count} ordered=true",
      resource_params => "additional_parameters='--open-files-limit=16384' enable_creation=true wsrep_cluster_address='gcomm://${galera_nodes}'",
      require         => Class['::mysql::server'],
      before          => Exec['galera-ready'],
    }
  }
  $mysql_root_password = hiera('mysql::server::root_password')
  $mysql_clustercheck_password = hiera('mysql_clustercheck_password')
  # This step is to create a sysconfig clustercheck file with the root user and empty password
  # on the first install only (because later on the clustercheck db user will be used)
  # We are using exec and not file in order to not have duplicate definition errors in puppet
  # when we later set the the file to contain the clustercheck data
  exec { 'create-root-sysconfig-clustercheck':
    command => "/bin/echo 'MYSQL_USERNAME=root\nMYSQL_PASSWORD=\'\'\nMYSQL_HOST=localhost\n' > /etc/sysconfig/clustercheck",
    unless  => '/bin/test -e /etc/sysconfig/clustercheck && grep -q clustercheck /etc/sysconfig/clustercheck',
  }

  exec { 'galera-ready' :
    command     => '/usr/bin/clustercheck >/dev/null',
    timeout     => 30,
    tries       => 180,
    try_sleep   => 10,
    environment => ['AVAILABLE_WHEN_READONLY=0'],
    require     => Exec['create-root-sysconfig-clustercheck'],
  }

  xinetd::service { 'galera-monitor' :
    port           => '9200',
    server         => '/usr/bin/clustercheck',
    per_source     => 'UNLIMITED',
    log_on_success => '',
    log_on_failure => 'HOST',
    flags          => 'REUSE',
    service_type   => 'UNLISTED',
    user           => 'root',
    group          => 'root',
    require        => Exec['create-root-sysconfig-clustercheck'],
  }
  # We add a clustercheck db user and we will switch /etc/sysconfig/clustercheck
  # to it in a later step. We do this only on one node as it will replicate on
  # the other members. We also make sure that the permissions are the minimum necessary
  if $pacemaker_master {
    mysql_user { 'clustercheck@localhost':
      ensure        => 'present',
      password_hash => mysql_password($mysql_clustercheck_password),
      require       => Exec['galera-ready'],
    }
    mysql_grant { 'clustercheck@localhost/*.*':
      ensure     => 'present',
      options    => ['GRANT'],
      privileges => ['PROCESS'],
      table      => '*.*',
      user       => 'clustercheck@localhost',
    }
  }

  # Create all the database schemas
  if $sync_db {
    if downcase(hiera('ceilometer_backend')) == 'mysql' {
      class { '::ceilometer::db::mysql':
        require => Exec['galera-ready'],
      }
    }

    if downcase(hiera('gnocchi_indexer_backend')) == 'mysql' {
      class { '::gnocchi::db::mysql':
        require => Exec['galera-ready'],
      }
    }

    class { '::aodh::db::mysql':
        require => Exec['galera-ready'],
      }
  }

} #END STEP 2

if hiera('step') >= 4 or ( hiera('step') >= 3 and $sync_db ) {
  # At this stage we are guaranteed that the clustercheck db user exists
  # so we switch the resource agent to use it.
  file { '/etc/sysconfig/clustercheck' :
    ensure  => file,
    mode    => '0600',
    owner   => 'root',
    group   => 'root',
    content => "MYSQL_USERNAME=clustercheck\n
MYSQL_PASSWORD='${mysql_clustercheck_password}'\n
MYSQL_HOST=localhost\n",
  }

  $nova_ipv6 = hiera('nova::use_ipv6', false)
  if $nova_ipv6 {
    $memcached_servers = suffix(hiera('memcache_node_ips_v6'), ':11211')
  } else {
    $memcached_servers = suffix(hiera('memcache_node_ips'), ':11211')
  }

  class { '::nova' :
    memcached_servers => $memcached_servers
  }

  include ::nova::config

  if hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {

    # TODO(devvesa) provide non-controller ips for these services
    $zookeeper_node_ips = hiera('neutron_api_node_ips')
    $cassandra_node_ips = hiera('neutron_api_node_ips')

    # Run zookeeper in the controller if configured
    if hiera('enable_zookeeper_on_controller') {
      class {'::tripleo::cluster::zookeeper':
        zookeeper_server_ips => $zookeeper_node_ips,
        # TODO: create a 'bind' hiera key for zookeeper
        zookeeper_client_ip  => hiera('neutron::bind_host'),
        zookeeper_hostnames  => split(hiera('controller_node_names'), ',')
      }
    }

    # Run cassandra in the controller if configured
    if hiera('enable_cassandra_on_controller') {
      class {'::tripleo::cluster::cassandra':
        cassandra_servers => $cassandra_node_ips,
        # TODO: create a 'bind' hiera key for cassandra
        cassandra_ip      => hiera('neutron::bind_host'),
      }
    }

    class {'::tripleo::network::midonet::agent':
      zookeeper_servers => $zookeeper_node_ips,
      cassandra_seeds   => $cassandra_node_ips
    }

    class {'::tripleo::network::midonet::api':
      zookeeper_servers    => $zookeeper_node_ips,
      vip                  => hiera('public_virtual_ip'),
      keystone_ip          => hiera('public_virtual_ip'),
      keystone_admin_token => hiera('keystone::admin_token'),
      # TODO: create a 'bind' hiera key for api
      bind_address         => hiera('neutron::bind_host'),
      admin_password       => hiera('admin_password')
    }

    # Configure Neutron
    # TODO: when doing the composable midonet plugin, don't forget to
    # set service_plugins to an empty array in Hiera.
    class {'::neutron':
      service_plugins => []
    }

  }

  if hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {
    class {'::neutron::plugins::midonet':
      midonet_api_ip    => hiera('public_virtual_ip'),
      keystone_tenant   => hiera('neutron::server::auth_tenant'),
      keystone_password => hiera('neutron::server::password')
    }
  }

  # Ceilometer
  case downcase(hiera('ceilometer_backend')) {
    /mysql/: {
      $ceilometer_database_connection = hiera('ceilometer_mysql_conn_string')
    }
    default: {
      $mongo_node_string = join($mongo_node_ips_with_port, ',')
      $ceilometer_database_connection = "mongodb://${mongo_node_string}/ceilometer?replicaSet=${mongodb_replset}"
    }
  }
  include ::ceilometer
  include ::ceilometer::config
  class { '::ceilometer::api' :
    manage_service => false,
    enabled        => false,
  }
  class { '::ceilometer::agent::notification' :
    manage_service => false,
    enabled        => false,
  }
  class { '::ceilometer::agent::central' :
    manage_service => false,
    enabled        => false,
  }
  class { '::ceilometer::collector' :
    manage_service => false,
    enabled        => false,
  }
  include ::ceilometer::expirer
  class { '::ceilometer::db' :
    database_connection => $ceilometer_database_connection,
    sync_db             => $sync_db,
  }
  include ::ceilometer::agent::auth
  include ::ceilometer::dispatcher::gnocchi

  Cron <| title == 'ceilometer-expirer' |> { command => "sleep $((\$(od -A n -t d -N 3 /dev/urandom) % 86400)) && ${::ceilometer::params::expirer_command}" }

  # httpd/apache and horizon
  # NOTE(gfidente): server-status can be consumed by the pacemaker resource agent
  class { '::apache' :
    service_enable => false,
    # service_manage => false, # <-- not supported with horizon&apache mod_wsgi?
  }
  include ::apache::mod::remoteip
  include ::apache::mod::status
  if 'cisco_n1kv' in hiera('neutron::plugins::ml2::mechanism_drivers') {
    $_profile_support = 'cisco'
  } else {
    $_profile_support = 'None'
  }
  $neutron_options   = {'profile_support' => $_profile_support }

  $memcached_ipv6 = hiera('memcached_ipv6', false)
  if $memcached_ipv6 {
    $horizon_memcached_servers = hiera('memcache_node_ips_v6', '[::1]')
  } else {
    $horizon_memcached_servers = hiera('memcache_node_ips', '127.0.0.1')
  }

  class { '::horizon':
    cache_server_ip => $horizon_memcached_servers,
    neutron_options => $neutron_options,
  }

  # Aodh
  class { '::aodh' :
    database_connection => hiera('aodh_mysql_conn_string'),
  }
  include ::aodh::config
  include ::aodh::auth
  include ::aodh::client
  include ::aodh::wsgi::apache
  class { '::aodh::api':
    manage_service => false,
    enabled        => false,
    service_name   => 'httpd',
  }
  class { '::aodh::evaluator':
    manage_service => false,
    enabled        => false,
  }
  class { '::aodh::notifier':
    manage_service => false,
    enabled        => false,
  }
  class { '::aodh::listener':
    manage_service => false,
    enabled        => false,
  }

  # Gnocchi
  $gnocchi_database_connection = hiera('gnocchi_mysql_conn_string')
  include ::gnocchi::client
  if $sync_db {
    include ::gnocchi::db::sync
  }
  include ::gnocchi::storage
  $gnocchi_backend = downcase(hiera('gnocchi_backend', 'swift'))
  case $gnocchi_backend {
      'swift': { include ::gnocchi::storage::swift }
      'file': { include ::gnocchi::storage::file }
      'rbd': { include ::gnocchi::storage::ceph }
      default: { fail('Unrecognized gnocchi_backend parameter.') }
  }
  class { '::gnocchi':
    database_connection => $gnocchi_database_connection,
  }
  class { '::gnocchi::api' :
    manage_service => false,
    enabled        => false,
    service_name   => 'httpd',
  }
  class { '::gnocchi::wsgi::apache' :
    ssl => false,
  }
  class { '::gnocchi::metricd' :
    manage_service => false,
    enabled        => false,
  }
  class { '::gnocchi::statsd' :
    manage_service => false,
    enabled        => false,
  }

  hiera_include('controller_classes')

} #END STEP 4

if hiera('step') >= 5 {
  # We now make sure that the root db password is set to a random one
  # At first installation /root/.my.cnf will be empty and we connect without a root
  # password. On second runs or updates /root/.my.cnf will already be populated
  # with proper credentials. This step happens on every node because this sql
  # statement does not automatically replicate across nodes.
  exec { 'galera-set-root-password':
    command => "/bin/touch /root/.my.cnf && /bin/echo \"UPDATE mysql.user SET Password = PASSWORD('${mysql_root_password}') WHERE user = 'root'; flush privileges;\" | /bin/mysql --defaults-extra-file=/root/.my.cnf -u root",
  }
  file { '/root/.my.cnf' :
    ensure  => file,
    mode    => '0600',
    owner   => 'root',
    group   => 'root',
    content => "[client]
user=root
password=\"${mysql_root_password}\"

[mysql]
user=root
password=\"${mysql_root_password}\"",
    require => Exec['galera-set-root-password'],
  }

  $nova_enable_db_purge = hiera('nova_enable_db_purge', true)

  if $nova_enable_db_purge {
    include ::nova::cron::archive_deleted_rows
  }

  if $pacemaker_master {

    pacemaker::constraint::base { 'openstack-core-then-httpd-constraint':
      constraint_type => 'order',
      first_resource  => 'openstack-core-clone',
      second_resource => "${::apache::params::service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::apache::params::service_name],
                          Pacemaker::Resource::Ocf['openstack-core']],
    }
    pacemaker::constraint::base { 'galera-then-openstack-core-constraint':
      constraint_type => 'order',
      first_resource  => 'galera-master',
      second_resource => 'openstack-core-clone',
      first_action    => 'promote',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Ocf['galera'],
                          Pacemaker::Resource::Ocf['openstack-core']],
    }

    if hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {
      pacemaker::resource::service {'tomcat':
        clone_params => 'interleave=true',
      }
    }
    if hiera('neutron::core_plugin') == 'midonet.neutron.plugin_v1.MidonetPluginV2' {
      #midonet-chain chain keystone-->neutron-server-->dhcp-->metadata->tomcat
      pacemaker::constraint::base { 'neutron-server-to-dhcp-agent-constraint':
        constraint_type => 'order',
        first_resource  => "${::neutron::params::server_service}-clone",
        second_resource => "${::neutron::params::dhcp_agent_service}-clone",
        first_action    => 'start',
        second_action   => 'start',
        require         => [Pacemaker::Resource::Service[$::neutron::params::server_service],
                            Pacemaker::Resource::Service[$::neutron::params::dhcp_agent_service]],
      }
      pacemaker::constraint::base { 'neutron-dhcp-agent-to-metadata-agent-constraint':
        constraint_type => 'order',
        first_resource  => "${::neutron::params::dhcp_agent_service}-clone",
        second_resource => "${::neutron::params::metadata_agent_service}-clone",
        first_action    => 'start',
        second_action   => 'start',
        require         => [Pacemaker::Resource::Service[$::neutron::params::dhcp_agent_service],
                            Pacemaker::Resource::Service[$::neutron::params::metadata_agent_service]],
      }
      pacemaker::constraint::base { 'neutron-metadata-agent-to-tomcat-constraint':
        constraint_type => 'order',
        first_resource  => "${::neutron::params::metadata_agent_service}-clone",
        second_resource => 'tomcat-clone',
        first_action    => 'start',
        second_action   => 'start',
        require         => [Pacemaker::Resource::Service[$::neutron::params::metadata_agent_service],
                            Pacemaker::Resource::Service['tomcat']],
      }
      pacemaker::constraint::colocation { 'neutron-dhcp-agent-to-metadata-agent-colocation':
        source  => "${::neutron::params::metadata_agent_service}-clone",
        target  => "${::neutron::params::dhcp_agent_service}-clone",
        score   => 'INFINITY',
        require => [Pacemaker::Resource::Service[$::neutron::params::dhcp_agent_service],
                    Pacemaker::Resource::Service[$::neutron::params::metadata_agent_service]],
      }
    }

    # Nova
    pacemaker::constraint::base { 'keystone-then-nova-consoleauth-constraint':
      constraint_type => 'order',
      first_resource  => 'openstack-core-clone',
      second_resource => "${::nova::params::consoleauth_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::nova::params::consoleauth_service_name],
                          Pacemaker::Resource::Ocf['openstack-core']],
    }
    pacemaker::constraint::colocation { 'nova-consoleauth-with-openstack-core':
      source  => "${::nova::params::consoleauth_service_name}-clone",
      target  => 'openstack-core-clone',
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::nova::params::consoleauth_service_name],
                  Pacemaker::Resource::Ocf['openstack-core']],
    }
    pacemaker::constraint::base { 'nova-consoleauth-then-nova-vncproxy-constraint':
      constraint_type => 'order',
      first_resource  => "${::nova::params::consoleauth_service_name}-clone",
      second_resource => "${::nova::params::vncproxy_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::nova::params::consoleauth_service_name],
                          Pacemaker::Resource::Service[$::nova::params::vncproxy_service_name]],
    }
    pacemaker::constraint::colocation { 'nova-vncproxy-with-nova-consoleauth-colocation':
      source  => "${::nova::params::vncproxy_service_name}-clone",
      target  => "${::nova::params::consoleauth_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::nova::params::consoleauth_service_name],
                  Pacemaker::Resource::Service[$::nova::params::vncproxy_service_name]],
    }
    pacemaker::constraint::base { 'nova-vncproxy-then-nova-api-constraint':
      constraint_type => 'order',
      first_resource  => "${::nova::params::vncproxy_service_name}-clone",
      second_resource => "${::nova::params::api_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::nova::params::vncproxy_service_name],
                          Pacemaker::Resource::Service[$::nova::params::api_service_name]],
    }
    pacemaker::constraint::colocation { 'nova-api-with-nova-vncproxy-colocation':
      source  => "${::nova::params::api_service_name}-clone",
      target  => "${::nova::params::vncproxy_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::nova::params::vncproxy_service_name],
                  Pacemaker::Resource::Service[$::nova::params::api_service_name]],
    }
    pacemaker::constraint::base { 'nova-api-then-nova-scheduler-constraint':
      constraint_type => 'order',
      first_resource  => "${::nova::params::api_service_name}-clone",
      second_resource => "${::nova::params::scheduler_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::nova::params::api_service_name],
                          Pacemaker::Resource::Service[$::nova::params::scheduler_service_name]],
    }
    pacemaker::constraint::colocation { 'nova-scheduler-with-nova-api-colocation':
      source  => "${::nova::params::scheduler_service_name}-clone",
      target  => "${::nova::params::api_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::nova::params::api_service_name],
                  Pacemaker::Resource::Service[$::nova::params::scheduler_service_name]],
    }
    pacemaker::constraint::base { 'nova-scheduler-then-nova-conductor-constraint':
      constraint_type => 'order',
      first_resource  => "${::nova::params::scheduler_service_name}-clone",
      second_resource => "${::nova::params::conductor_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::nova::params::scheduler_service_name],
                          Pacemaker::Resource::Service[$::nova::params::conductor_service_name]],
    }
    pacemaker::constraint::colocation { 'nova-conductor-with-nova-scheduler-colocation':
      source  => "${::nova::params::conductor_service_name}-clone",
      target  => "${::nova::params::scheduler_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::nova::params::scheduler_service_name],
                  Pacemaker::Resource::Service[$::nova::params::conductor_service_name]],
    }

    # Ceilometer and Aodh
    case downcase(hiera('ceilometer_backend')) {
      /mysql/: {
        pacemaker::resource::service { $::ceilometer::params::agent_central_service_name:
          clone_params => 'interleave=true',
          require      => Pacemaker::Resource::Ocf['openstack-core'],
        }
      }
      default: {
        pacemaker::resource::service { $::ceilometer::params::agent_central_service_name:
          clone_params => 'interleave=true',
          require      => [Pacemaker::Resource::Ocf['openstack-core'],
                          Pacemaker::Resource::Service[$::mongodb::params::service_name]],
        }
      }
    }
    pacemaker::resource::service { $::ceilometer::params::collector_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::resource::service { $::ceilometer::params::api_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::resource::service { $::ceilometer::params::agent_notification_service_name :
      clone_params => 'interleave=true',
    }
    # Fedora doesn't know `require-all` parameter for constraints yet
    if $::operatingsystem == 'Fedora' {
      $redis_ceilometer_constraint_params = undef
      $redis_aodh_constraint_params = undef
    } else {
      $redis_ceilometer_constraint_params = 'require-all=false'
      $redis_aodh_constraint_params = 'require-all=false'
    }
    pacemaker::constraint::base { 'redis-then-ceilometer-central-constraint':
      constraint_type   => 'order',
      first_resource    => 'redis-master',
      second_resource   => "${::ceilometer::params::agent_central_service_name}-clone",
      first_action      => 'promote',
      second_action     => 'start',
      constraint_params => $redis_ceilometer_constraint_params,
      require           => [Pacemaker::Resource::Ocf['redis'],
                            Pacemaker::Resource::Service[$::ceilometer::params::agent_central_service_name]],
    }
    pacemaker::constraint::base { 'redis-then-aodh-evaluator-constraint':
      constraint_type   => 'order',
      first_resource    => 'redis-master',
      second_resource   => "${::aodh::params::evaluator_service_name}-clone",
      first_action      => 'promote',
      second_action     => 'start',
      constraint_params => $redis_aodh_constraint_params,
      require           => [Pacemaker::Resource::Ocf['redis'],
                            Pacemaker::Resource::Service[$::aodh::params::evaluator_service_name]],
    }
    pacemaker::constraint::base { 'keystone-then-ceilometer-central-constraint':
      constraint_type => 'order',
      first_resource  => 'openstack-core-clone',
      second_resource => "${::ceilometer::params::agent_central_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::ceilometer::params::agent_central_service_name],
                          Pacemaker::Resource::Ocf['openstack-core']],
    }
    pacemaker::constraint::base { 'keystone-then-ceilometer-notification-constraint':
      constraint_type => 'order',
      first_resource  => 'openstack-core-clone',
      second_resource => "${::ceilometer::params::agent_notification_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::ceilometer::params::agent_central_service_name],
                          Pacemaker::Resource::Ocf['openstack-core']],
    }
    pacemaker::constraint::base { 'ceilometer-central-then-ceilometer-collector-constraint':
      constraint_type => 'order',
      first_resource  => "${::ceilometer::params::agent_central_service_name}-clone",
      second_resource => "${::ceilometer::params::collector_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::ceilometer::params::agent_central_service_name],
                          Pacemaker::Resource::Service[$::ceilometer::params::collector_service_name]],
    }
    pacemaker::constraint::base { 'ceilometer-collector-then-ceilometer-api-constraint':
      constraint_type => 'order',
      first_resource  => "${::ceilometer::params::collector_service_name}-clone",
      second_resource => "${::ceilometer::params::api_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::ceilometer::params::collector_service_name],
                          Pacemaker::Resource::Service[$::ceilometer::params::api_service_name]],
    }
    pacemaker::constraint::colocation { 'ceilometer-api-with-ceilometer-collector-colocation':
      source  => "${::ceilometer::params::api_service_name}-clone",
      target  => "${::ceilometer::params::collector_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::ceilometer::params::api_service_name],
                  Pacemaker::Resource::Service[$::ceilometer::params::collector_service_name]],
    }
    # Aodh
    pacemaker::resource::service { $::aodh::params::evaluator_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::resource::service { $::aodh::params::notifier_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::resource::service { $::aodh::params::listener_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::constraint::base { 'aodh-evaluator-then-aodh-notifier-constraint':
      constraint_type => 'order',
      first_resource  => "${::aodh::params::evaluator_service_name}-clone",
      second_resource => "${::aodh::params::notifier_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::aodh::params::evaluator_service_name],
                          Pacemaker::Resource::Service[$::aodh::params::notifier_service_name]],
    }
    pacemaker::constraint::colocation { 'aodh-notifier-with-aodh-evaluator-colocation':
      source  => "${::aodh::params::notifier_service_name}-clone",
      target  => "${::aodh::params::evaluator_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::aodh::params::evaluator_service_name],
                  Pacemaker::Resource::Service[$::aodh::params::notifier_service_name]],
    }
    pacemaker::constraint::base { 'aodh-evaluator-then-aodh-listener-constraint':
      constraint_type => 'order',
      first_resource  => "${::aodh::params::evaluator_service_name}-clone",
      second_resource => "${::aodh::params::listener_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::aodh::params::evaluator_service_name],
                          Pacemaker::Resource::Service[$::aodh::params::listener_service_name]],
    }
    pacemaker::constraint::colocation { 'aodh-listener-with-aodh-evaluator-colocation':
      source  => "${::aodh::params::listener_service_name}-clone",
      target  => "${::aodh::params::evaluator_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::aodh::params::evaluator_service_name],
                  Pacemaker::Resource::Service[$::aodh::params::listener_service_name]],
    }
    if downcase(hiera('ceilometer_backend')) == 'mongodb' {
      pacemaker::constraint::base { 'mongodb-then-ceilometer-central-constraint':
        constraint_type => 'order',
        first_resource  => "${::mongodb::params::service_name}-clone",
        second_resource => "${::ceilometer::params::agent_central_service_name}-clone",
        first_action    => 'start',
        second_action   => 'start',
        require         => [Pacemaker::Resource::Service[$::ceilometer::params::agent_central_service_name],
                            Pacemaker::Resource::Service[$::mongodb::params::service_name]],
      }
    }

    # gnocchi
    pacemaker::resource::service { $::gnocchi::params::metricd_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::resource::service { $::gnocchi::params::statsd_service_name :
      clone_params => 'interleave=true',
    }
    pacemaker::constraint::base { 'gnocchi-metricd-then-gnocchi-statsd-constraint':
      constraint_type => 'order',
      first_resource  => "${::gnocchi::params::metricd_service_name}-clone",
      second_resource => "${::gnocchi::params::statsd_service_name}-clone",
      first_action    => 'start',
      second_action   => 'start',
      require         => [Pacemaker::Resource::Service[$::gnocchi::params::metricd_service_name],
                          Pacemaker::Resource::Service[$::gnocchi::params::statsd_service_name]],
    }
    pacemaker::constraint::colocation { 'gnocchi-statsd-with-metricd-colocation':
      source  => "${::gnocchi::params::statsd_service_name}-clone",
      target  => "${::gnocchi::params::metricd_service_name}-clone",
      score   => 'INFINITY',
      require => [Pacemaker::Resource::Service[$::gnocchi::params::metricd_service_name],
                  Pacemaker::Resource::Service[$::gnocchi::params::statsd_service_name]],
    }

    # Horizon and Keystone
    pacemaker::resource::service { $::apache::params::service_name:
      clone_params     => 'interleave=true',
      verify_on_create => true,
      require          => [File['/etc/keystone/ssl/certs/ca.pem'],
      File['/etc/keystone/ssl/private/signing_key.pem'],
      File['/etc/keystone/ssl/certs/signing_cert.pem']],
    }

    #VSM
    if 'cisco_n1kv' in hiera('neutron::plugins::ml2::mechanism_drivers') {
      pacemaker::resource::ocf { 'vsm-p' :
        ocf_agent_name  => 'heartbeat:VirtualDomain',
        resource_params => 'force_stop=true config=/var/spool/cisco/vsm/vsm_primary_deploy.xml',
        require         => Class['n1k_vsm'],
        meta_params     => 'resource-stickiness=INFINITY',
      }
      if str2bool(hiera('n1k_vsm::pacemaker_control', true)) {
        pacemaker::resource::ocf { 'vsm-s' :
          ocf_agent_name  => 'heartbeat:VirtualDomain',
          resource_params => 'force_stop=true config=/var/spool/cisco/vsm/vsm_secondary_deploy.xml',
          require         => Class['n1k_vsm'],
          meta_params     => 'resource-stickiness=INFINITY',
        }
        pacemaker::constraint::colocation { 'vsm-colocation-contraint':
          source  => 'vsm-p',
          target  => 'vsm-s',
          score   => '-INFINITY',
          require => [Pacemaker::Resource::Ocf['vsm-p'],
                      Pacemaker::Resource::Ocf['vsm-s']],
        }
      }
    }

  }

} #END STEP 5

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_controller_pacemaker', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}
