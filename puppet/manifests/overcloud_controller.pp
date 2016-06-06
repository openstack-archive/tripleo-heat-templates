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

if hiera('step') >= 2 {
  # FIXME: this should only occur on the bootstrap host (ditto for db syncs)
  # Create all the database schemas
  include ::aodh::db::mysql

} #END STEP 2

if hiera('step') >= 4 {
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

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_controller', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}
