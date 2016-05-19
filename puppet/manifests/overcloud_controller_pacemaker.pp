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

    exec { 'galera-ready' :
      command     => '/usr/bin/clustercheck >/dev/null',
      timeout     => 30,
      tries       => 180,
      try_sleep   => 10,
      environment => ['AVAILABLE_WHEN_READONLY=0'],
      require     => Exec['create-root-sysconfig-clustercheck'],
    }

    # We add a clustercheck db user and we will switch /etc/sysconfig/clustercheck
    # to it in a later step. We do this only on one node as it will replicate on
    # the other members. We also make sure that the permissions are the minimum necessary
    mysql_user { 'clustercheck@localhost':
      ensure        => 'present',
      password_hash => mysql_password(hiera('mysql_clustercheck_password')),
      require       => Exec['galera-ready'],
    }

    mysql_grant { 'clustercheck@localhost/*.*':
      ensure     => 'present',
      options    => ['GRANT'],
      privileges => ['PROCESS'],
      table      => '*.*',
      user       => 'clustercheck@localhost',
    }

    class { '::aodh::db::mysql':
        require => Exec['galera-ready'],
    }
  }
  # This step is to create a sysconfig clustercheck file with the root user and empty password
  # on the first install only (because later on the clustercheck db user will be used)
  # We are using exec and not file in order to not have duplicate definition errors in puppet
  # when we later set the the file to contain the clustercheck data
  exec { 'create-root-sysconfig-clustercheck':
    command => "/bin/echo 'MYSQL_USERNAME=root\nMYSQL_PASSWORD=\'\'\nMYSQL_HOST=localhost\n' > /etc/sysconfig/clustercheck",
    unless  => '/bin/test -e /etc/sysconfig/clustercheck && grep -q clustercheck /etc/sysconfig/clustercheck',
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

} #END STEP 2

if hiera('step') >= 4 or ( hiera('step') >= 3 and $sync_db ) {
  # At this stage we are guaranteed that the clustercheck db user exists
  # so we switch the resource agent to use it.
  $mysql_clustercheck_password = hiera('mysql_clustercheck_password')
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

  hiera_include('controller_classes')

} #END STEP 4

if hiera('step') >= 5 {
  # We now make sure that the root db password is set to a random one
  # At first installation /root/.my.cnf will be empty and we connect without a root
  # password. On second runs or updates /root/.my.cnf will already be populated
  # with proper credentials. This step happens on every node because this sql
  # statement does not automatically replicate across nodes.
  $mysql_root_password = hiera('mysql::server::root_password')
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

    # Fedora doesn't know `require-all` parameter for constraints yet
    if $::operatingsystem == 'Fedora' {
      $redis_aodh_constraint_params = undef
    } else {
      $redis_aodh_constraint_params = 'require-all=false'
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
