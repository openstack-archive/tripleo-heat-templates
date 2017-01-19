#!/bin/bash
#
# This delivers the compute upgrade script to be invoked as part of the tripleo
# major upgrade workflow.
#
set -eu

UPGRADE_SCRIPT=/root/liberty_to_mitaka_neutron_auth_param.pp

cat > $UPGRADE_SCRIPT << ENDOFCAT
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
# during the converge step.

if str2bool(hiera('nova::compute::enabled', false)) {
    class{ 'nova::network::neutron':
      neutron_auth_plugin             => 'v3password',
      neutron_username                => hiera('nova::network::neutron::neutron_username'),
      neutron_password                => hiera('nova::network::neutron::neutron_password'),
      neutron_auth_url                => hiera('nova::network::neutron::neutron_auth_url'),
      # DEPRECATED PARAMETERS
      neutron_auth_strategy           => undef,
      neutron_admin_tenant_name       => undef,
      neutron_admin_username          => undef,
      neutron_admin_auth_url          => undef,
      }
}
ENDOFCAT
