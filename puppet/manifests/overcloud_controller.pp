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
  # FIXME: this should only occur on the bootstrap host (ditto for db syncs)
  # Create all the database schemas
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
