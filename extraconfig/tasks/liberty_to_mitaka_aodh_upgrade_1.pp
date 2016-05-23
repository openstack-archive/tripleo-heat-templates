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

if str2bool(hiera('mongodb::server::ipv6', false)) {
  $mongo_node_ips_with_port_prefixed = prefix(hiera('mongo_node_ips'), '[')
  $mongo_node_ips_with_port = suffix($mongo_node_ips_with_port_prefixed, ']:27017')
  $mongo_node_ips_with_port_nobr = suffix(hiera('mongo_node_ips'), ':27017')
} else {
  $mongo_node_ips_with_port = suffix(hiera('mongo_node_ips'), ':27017')
  $mongo_node_ips_with_port_nobr = suffix(hiera('mongo_node_ips'), ':27017')
}
$mongodb_replset = hiera('mongodb::server::replset')
$mongo_node_string = join($mongo_node_ips_with_port, ',')
$database_connection = "mongodb://${mongo_node_string}/ceilometer?replicaSet=${mongodb_replset}"

class { '::aodh' :
  database_connection => $database_connection,
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
