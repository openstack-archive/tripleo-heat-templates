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

$enable_load_balancer = hiera('enable_load_balancer', true)

if hiera('step') >= 2 {
  if str2bool(hiera('enable_galera', true)) {
    $mysql_config_file = '/etc/my.cnf.d/galera.cnf'
  } else {
    $mysql_config_file = '/etc/my.cnf.d/server.cnf'
  }
  # TODO Galara
  # FIXME: due to https://bugzilla.redhat.com/show_bug.cgi?id=1298671 we
  # set bind-address to a hostname instead of an ip address; to move Mysql
  # from internal_api on another network we'll have to customize both
  # MysqlNetwork and ControllerHostnameResolveNetwork in ServiceNetMap
  class { '::mysql::server':
    config_file             => $mysql_config_file,
    override_options        => {
      'mysqld' => {
        'bind-address'     => $::hostname,
        'max_connections'  => hiera('mysql_max_connections'),
        'open_files_limit' => '-1',
      },
    },
    remove_default_accounts => true,
  }

  # FIXME: this should only occur on the bootstrap host (ditto for db syncs)
  # Create all the database schemas
  if downcase(hiera('gnocchi_indexer_backend')) == 'mysql' {
    include ::gnocchi::db::mysql
  }
  include ::aodh::db::mysql

} #END STEP 2

if hiera('step') >= 4 {

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
  include ::aodh::db::sync
  include ::aodh::auth
  include ::aodh::api
  include ::aodh::wsgi::apache
  include ::aodh::evaluator
  include ::aodh::notifier
  include ::aodh::listener
  include ::aodh::client

  # Gnocchi
  $gnocchi_database_connection = hiera('gnocchi_mysql_conn_string')
  class { '::gnocchi':
    database_connection => $gnocchi_database_connection,
  }
  include ::gnocchi::api
  include ::gnocchi::wsgi::apache
  include ::gnocchi::client
  include ::gnocchi::db::sync
  include ::gnocchi::storage
  include ::gnocchi::metricd
  include ::gnocchi::statsd
  $gnocchi_backend = downcase(hiera('gnocchi_backend', 'swift'))
  case $gnocchi_backend {
      'swift': { include ::gnocchi::storage::swift }
      'file': { include ::gnocchi::storage::file }
      'rbd': { include ::gnocchi::storage::ceph }
      default: { fail('Unrecognized gnocchi_backend parameter.') }
  }

  hiera_include('controller_classes')

} #END STEP 4

if hiera('step') >= 5 {
  $nova_enable_db_purge = hiera('nova_enable_db_purge', true)

  if $nova_enable_db_purge {
    include ::nova::cron::archive_deleted_rows
  }
} #END STEP 5

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_controller', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}
