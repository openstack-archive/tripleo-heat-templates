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

# This puppet manifest is to be used only during a Mitaka->Newton upgrade
# It configures ceilometer to be run under httpd but it makes sure to not
# restart any services. This snippet needs to be called before init as a
# pre upgrade migration.

Service <|
  tag == 'ceilometer-service'
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


if str2bool(hiera('mongodb::server::ipv6', false)) {
  $mongo_node_ips_with_port_prefixed = prefix(hiera('mongodb_node_ips'), '[')
  $mongo_node_ips_with_port = suffix($mongo_node_ips_with_port_prefixed, ']:27017')
} else {
  $mongo_node_ips_with_port = suffix(hiera('mongodb_node_ips'), ':27017')
}
$mongodb_replset = hiera('mongodb::server::replset')
$mongo_node_string = join($mongo_node_ips_with_port, ',')
$database_connection = "mongodb://${mongo_node_string}/ceilometer?replicaSet=${mongodb_replset}"

include ::ceilometer

class {'::ceilometer::db':
  database_connection => $database_connection,
}

if $sync_db  {
  include ::ceilometer::db::sync
}

include ::ceilometer::config

class { '::ceilometer::api':
  enabled           => true,
  service_name      => 'httpd',
  keystone_password => hiera('ceilometer::keystone::auth::password'),
  identity_uri      => hiera('ceilometer::keystone::authtoken::auth_url'),
  auth_uri          => hiera('ceilometer::keystone::authtoken::auth_uri'),
  keystone_tenant   => hiera('ceilometer::keystone::authtoken::project_name'),
}

class { '::apache' :
  service_enable  => false,
  service_manage  => true,
  service_restart => '/bin/true',
  purge_configs   => false,
  purge_vhost_dir => false,
}

# To ensure existing ports are not overridden
class { '::aodh::wsgi::apache':
  servername => $::hostname,
  ssl        => false,
}
class { '::gnocchi::wsgi::apache':
  servername => $::hostname,
  ssl        => false,
}

class { '::keystone::wsgi::apache':
  servername => $::hostname,
  ssl        => false,
}
class { '::ceilometer::wsgi::apache':
  servername => $::hostname,
  ssl        => false,
}
