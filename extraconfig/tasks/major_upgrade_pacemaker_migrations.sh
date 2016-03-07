#!/bin/bash

# Special pieces of upgrade migration logic go into this
# file. E.g. Pacemaker cluster transitions for existing deployments,
# matching changes to overcloud_controller_pacemaker.pp (Puppet
# handles deployment, this file handles migrations).
#
# This file shouldn't execute any action on its own, all logic should
# be wrapped into bash functions. Upgrade scripts will source this
# file and call the functions defined in this file where appropriate.
#
# The migration functions should be idempotent. If the migration has
# been already applied, it should be possible to call the function
# again without damaging the deployment or failing the upgrade.
