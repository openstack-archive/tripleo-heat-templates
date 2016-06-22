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

include ::pacemaker::resource_defaults

if $::hostname == downcase(hiera('bootstrap_nodeid')) {
  $pacemaker_master = true
} else {
  $pacemaker_master = false
}

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

# It seems that restarting httpd via pcs at this stage can break
# because at least in liberty it seems httpd is often started
# via puppet and not via pacemaker and this confuses restarts
exec {'restart-httpd-for-aodh-l-m-upgrade':
  command => '/usr/bin/systemctl reload httpd',
  require => [Class['::apache'],
              Class['::aodh::api']],
}

if $pacemaker_master {

  pacemaker::resource::service { $::aodh::params::evaluator_service_name :
    clone_params => 'interleave=true',
    require      => Class['::aodh::evaluator'],
  }
  pacemaker::resource::service { $::aodh::params::notifier_service_name :
    clone_params => 'interleave=true',
    require      => Class['::aodh::notifier'],
  }
  pacemaker::resource::service { $::aodh::params::listener_service_name :
    clone_params => 'interleave=true',
    require      => Class['::aodh::listener'],
  }

  # Do no explicitely require on Pacemaker::Resource::Ocf['redis'] because
  # the resource already exists at this stage and we do not want to include
  # all the redis puppet manifests to reinstate it as it is already there
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
    require           => [Pacemaker::Resource::Service[$::aodh::params::evaluator_service_name]],
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
}
