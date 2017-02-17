# Copyright 2017 Red Hat, Inc.
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

# This puppet manifest is to be used only during a Liberty->Mitaka
# upgrade It ensures proper configuration of nova.conf on controller
# and compute nodes.
nova_config {
  'neutron/auth_plugin':         value => 'v3password';
  'neutron/username':            value => hiera('nova::network::neutron::neutron_username');
  'neutron/password':            value => hiera('nova::network::neutron::neutron_password');
  'neutron/auth_url':            value => hiera('nova::network::neutron::neutron_auth_url');
  'neutron/project_name':        value => hiera('nova::network::neutron::neutron_project_name');
  'neutron/user_domain_name':    value => 'Default';
  'neutron/project_domain_name': value => 'Default';
  'DEFAULT/use_neutron':         value => 'True';
  'neutron/auth_strategy':       ensure => absent;
  'neutron/admin_tenant_name':   ensure => absent;
  'neutron/admin_username':      ensure => absent;
  'neutron/admin_auth_url':      ensure => absent;
}
