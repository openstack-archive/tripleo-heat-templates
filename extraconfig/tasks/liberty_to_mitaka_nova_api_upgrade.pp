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

# This puppet manifest is to be used only during a Liberty->Mitaka upgrade
# It creates the nova api database during the controller upgrade instead of
# during the converge step.  Executed on the controllers only.
include ::tripleo::packages
$pacemaker_master   = hiera('bootstrap_nodeid')

# Will prevent any reboot of any service.
Service <| |> {
  hasrestart => true,
  restart    => '/bin/true',
  start      => '/bin/true',
  stop       => '/bin/true',
  enable     => '/bin/true',
  provider   => 'base',
}

# Restart of the nova-* services will be done in another step.
nova_config {
  'api_database/connection': value => hiera('nova::api_database_connection')
}

if downcase($pacemaker_master) == $::hostname {
  # You have to open up the class here to avoid any change to the
  # /etc/my.cnf.d/server.cnf.  Ultimately, "include ::mysql::server"
  # is the one that modify it.
  $dbname = 'nova_api'
  mysql_database { $dbname:
    ensure  => present,
    charset => 'utf8',
    collate => 'utf8_general_ci',
    notify  => Exec['nova-db-sync-api'],
  }

  $allowed_hosts_list = unique(concat(any2array(hiera('nova::db::mysql::allowed_hosts')), [hiera('nova_api_vip')]))
  $real_allowed_hosts = prefix($allowed_hosts_list, "${dbname}_")

  openstacklib::db::mysql::host_access { $real_allowed_hosts:
    user          => hiera('nova::db::mysql_api::dbname'),
    password_hash => mysql_password(hiera('nova::db::mysql_api::password')),
    database      => $dbname,
    privileges    => 'ALL',
    notify        => Exec['nova-db-sync-api'],
  }

  exec { 'nova-db-sync-api':
    command     => '/usr/bin/nova-manage api_db sync',
    refreshonly => true,
    logoutput   => on_failure,
    notify      => Exec['nova-db-online-data-migrations']
  }

  exec { 'nova-db-online-data-migrations':
    command     => '/usr/bin/nova-manage db online_data_migrations',
    refreshonly => true,
    logoutput   => on_failure,
  }
}
