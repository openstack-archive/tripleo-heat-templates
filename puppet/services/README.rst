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

Apart from sevice specific inputs, there are few default parameters for all
the services. Following are the list of default parameters:

 * ServiceNetMap: Mapping of service_name -> network name. Typically set via
   parameter_defaults in the resource registry.  This mapping overrides those
   in ServiceNetMapDefaults.

 * EndpointMap: Mapping of service endpoint -> protocol. Typically set via
   parameter_defaults in the resource registry.

 * DefaultPasswords: Mapping of service -> default password. Used to help pass
   top level passwords managed by Heat into services.

 * RoleName: Name of the role on which this service is deployed. A service can
   be deployed in multiple roles.

 * RoleParameters: Parameter specific to a role on which the service is
   applied.

Config Settings
---------------

Each service may define three ways in which to output variables to configure Hiera
settings on the nodes.

 * config_settings: the hiera keys will be pushed on all roles of which the service
   is a part of.

 * global_config_settings: the hiera keys will be distributed to all roles

 * service_config_settings: Takes an extra key to wire in values that are
   defined for a service that need to be consumed by some other service.
   For example:
   service_config_settings:
     haproxy:
       foo: bar
   This will set the hiera key 'foo' on all roles where haproxy is included.

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

Batch Upgrade Steps
-------------------

Each service template may optionally define a `upgrade_batch_tasks` key, which
is a list of ansible tasks to be performed during the upgrade process.

Similar to the step_config, we allow a series of steps for the per-service
upgrade sequence, defined as ansible tasks with a tag e.g "step1" for the first
step, "step2" for the second, etc (currently only two steps are supported, but
more may be added when required as additional services get converted to batched
upgrades).

Note that each step is performed in batches, then we move on to the next step
which is also performed in batches (we don't perform all steps on one node,
then move on to the next one which means you can sequence rolling upgrades of
dependent services via the step value).

The tasks performed at each step is service specific, but note that all batch
upgrade steps are performed before the `upgrade_tasks` described below.  This
means that all services that support rolling upgrades can be upgraded without
downtime during `upgrade_batch_tasks`, then any remaining services are stopped
and upgraded during `upgrade_tasks`

The default batch size is 1, but this can be overridden for each role via the
`upgrade_batch_size` option in roles_data.yaml

Upgrade Steps
-------------

Each service template may optionally define a `upgrade_tasks` key, which is a
list of ansible tasks to be performed during the upgrade process.

Similar to the step_config, we allow a series of steps for the per-service
upgrade sequence, defined as ansible tasks with a tag e.g "step1" for the first
step, "step2" for the second, etc.

   Steps/tages correlate to the following:

   1) Stop all control-plane services.

   2) Quiesce the control-plane, e.g disable LoadBalancer, stop
      pacemaker cluster: this will stop the following resource:
      - ocata:
        - galera
        - rabbit
        - redis
        - haproxy
        - vips
        - cinder-volumes
        - cinder-backup
        - manilla-share
        - rbd-mirror

      The exact order is controlled by the cluster constraints.

   3) Perform a package update and install new packages: A general
      upgrade is done, and only new package should go into service
      ansible tasks.

   4) Start services needed for migration tasks (e.g DB)

   5) Perform any migration tasks, e.g DB sync commands

Note that the services are not started in the upgrade tasks - we instead re-run
puppet which does any reconfiguration required for the new version, then starts
the services.

Nova Server Metadata Settings
-----------------------------

One can use the hook of type `OS::TripleO::ServiceServerMetadataHook` to pass
entries to the nova instances' metadata. It is, however, disabled by default.
In order to overwrite it one needs to define it in the resource registry. An
implementation of this hook needs to conform to the following:

* It needs to define an input called `RoleData` of json type. This gets as
  input the contents of the `role_data` for each role's ServiceChain.

* This needs to define an output called `metadata` which will be given to the
  Nova Server resource as the instance's metadata.
