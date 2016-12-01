========
services
========

A TripleO nested stack Heat template that encapsulates generic configuration
data to configure a specific service. This generally includes everything
needed to configure the service excluding the local bind ports which
are still managed in the per-node role templates directly (controller.yaml,
compute.yaml, etc.). All other (global) service settings go into
the puppet/service templates.

Input Parameters
----------------

Each service may define its own input parameters and defaults.
Operators will use the parameter_defaults section of any Heat
environment to set per service parameters.

Config Settings
---------------

Each service may define a config_settings output variable which returns
Hiera settings to be configured.

Deployment Steps
----------------

Each service may define an output variable which returns a puppet manifest
snippet that will run at each of the following steps. Earlier manifests
are re-asserted when applying latter ones.

 * config_settings: Custom hiera settings for this service.

 * global_config_settings: Additional hiera settings distributed to all roles.

 * step_config: A puppet manifest that is used to step through the deployment
   sequence. Each sequence is given a "step" (via hiera('step') that provides
   information for when puppet classes should activate themselves.

   Steps correlate to the following:

   1) Load Balancer configuration

   2) Core Services (Database/Rabbit/NTP/etc.)

   3) Early Openstack Service setup (Ringbuilder, etc.)

   4) General OpenStack Services

   5) Service activation (Pacemaker)

Upgrade Steps
-------------

Each service template may optionally define a `upgrade_tasks` key, which is a
list of ansible tasks to be performed during the upgrade process.

Similar to the step_config, we allow a series of steps for the per-service
upgrade sequence, defined as ansible tasks with a tag e.g "step1" for the first
step, "step2" for the second, etc.

   Steps/tages correlate to the following:

   1) Quiesce the control-plane, e.g disable LoadBalancer, stop pacemaker cluster

   2) Stop all control-plane services, ready for upgrade

   3) Perform a package update, (either specific packages or the whole system)

   4) Start services needed for migration tasks (e.g DB)

   5) Perform any migration tasks, e.g DB sync commands

   6) Start control-plane services

   7) Any additional online migration tasks (e.g data migrations)
