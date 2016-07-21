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

# TODO(jistr): use pcs resource provider instead of just no-ops
Service <|
  tag == 'aodh-service'
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

if hiera('step') >= 2 {
  if $pacemaker_master {
    class { '::aodh::db::mysql':
        require => Exec['galera-ready'],
    }
  }
} #END STEP 2

if hiera('step') >= 4 or ( hiera('step') >= 3 and $sync_db ) {
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

    # The next step is to include this class in puppet-tripleo profiles directly.
    # We couldn't do it directly in puppet-tripleo, otherwise CI would have break because
    # of Puppet duplicated resource.
    include ::tripleo::profile::pacemaker::apache

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
