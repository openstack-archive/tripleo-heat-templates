===================
TripleO Deployments
===================

This directory contains files that represent individual service deployments,
orchestration tools, and the configuration tools used to deploy them.

Directory Structure
-------------------

Each logical grouping of services will have a directory. Example: 'timesync'.
Within this directory related timesync services would exist to for example
configure timesync services on baremetal or via containers.

Filenaming conventions
----------------------

As a convention each deployments service filename will reflect both
the deployment engine (baremetal, or containers) along with the
config tool used to deploy that service.

The convention is <service-name>-<engine>-<config management tool>.

Examples:

  deployment/aodh/aodh-api-container-puppet.yaml (containerized Aodh service configured with Puppet)

  deployment/aodh/aodh-api-container-ansible.yaml (containerized Aodh service configured with Ansible)

  deployment/timesync/chrony-baremetal-ansible.yaml (baremetal Chrony service configured with Ansible)

  deployment/timesync/chrony-baremetal-puppet.yaml (baremetal Chrony service configured with Puppet)

Building Kolla Images
---------------------

TripleO currently relies on Kolla(Dockerfile) containers. Kolla supports
container customization and we are making use of this feature within TripleO
to inject puppet (our configuration tool of choice) into the Kolla base images.
A variety of other customizations are being made via the
tripleo-common/container-images/tripleo_kolla_template_overrides.j2 file.

To build Kolla images for TripleO adjust your kolla config [*]_ to build your
centos base image with puppet using the example below:

.. code-block::

$ cat template-overrides.j2
{% extends parent_template %}
{% set base_centos_binary_packages_append = ['puppet'] %}
{% set nova_scheduler_packages_append = ['openstack-tripleo-common'] %}

kolla-build --base centos --template-override template-overrides.j2

..

.. [*] See the
   `override file <https://github.com/openstack/tripleo-common/blob/master/container-images/tripleo_kolla_template_overrides.j2>`_
   which can be used to build Kolla packages that work with TripleO.

Containerized Deployment Template Structure
-------------------------------------------
Each deployment template may define a set of output values control
the underlying service deployment in a variety of ways. These output sections
are specific to the TripleO deployment architecture. The following sections
are available for containerized services.

 * config_settings: This section contains service specific hiera data
   can be used to generate config files for each service. This data
   is ultimately processed via the container-puppet.py tool which
   generates config files for each service according to the settings here.

 * kolla_config: Contains YAML that represents how to map config files
   into the kolla container. This config file is typically mapped into
   the container itself at the /var/lib/kolla/config_files/config.json
   location and drives how kolla's external config mechanisms work.

 * docker_config: Data that is passed to paunch tool to configure
   a container, or step of containers at each step. See the available steps
   documented below which are implemented by TripleO's cluster deployment
   architecture. If you want the tasks executed only once for the bootstrap
   node per a role in the cluster, use the `/usr/bin/bootstrap_host_exec`
   wrapper.

 * puppet_config: This section is a nested set of key value pairs
   that drive the creation of config files using puppet.
   Required parameters include:

     * puppet_tags: Puppet resource tag names that are used to generate config
       files with puppet. Only the named config resources are used to generate
       a config file. Any service that specifies tags will have the default
       tags of 'file,concat,file_line,augeas,cron' appended to the setting.
       Example: keystone_config

     * config_volume: The name of the volume (directory) where config files
       will be generated for this service. Use this as the location to
       bind mount into the running Kolla container for configuration.

     * config_image: The name of the container image that will be used for
       generating configuration files. This is often the same container
       that the runtime service uses. Some services share a common set of
       config files which are generated in a common base container.

     * step_config: This setting controls the manifest that is used to
       create container config files via puppet. The puppet tags below are
       used along with this manifest to generate a config directory for
       this container.

 * container_puppet_tasks: This section provides data to drive the
   container-puppet.py tool directly. The task is executed for the
   defined steps before the corresponding docker_config's step. Puppet
   always sees the step number overrided as the step #6. It might be useful
   for initialization of things. See container-puppet.py for formatting.
   Note that the tasks are executed only once for the bootstrap node per a
   role in the cluster. Make sure the puppet manifest ensures the wanted
   "at most once" semantics. That may be achieved via the
   `<service_name>_short_bootstrap_node_name` hiera parameters automatically
   evaluated for each service.

 * global_config_settings: the hiera keys will be distributed to all roles

 * service_config_settings: Takes an extra key to wire in values that are
   defined for a service that need to be consumed by some other service.
   For example:
   service_config_settings:
     haproxy:
       foo: bar
   This will set the hiera key 'foo' on all roles where haproxy is included.

Deployment steps
----------------
Similar to baremetal containers are brought up in a stepwise manner.
The current architecture supports bringing up baremetal services alongside
of containers. For each step the baremetal puppet manifests are executed
first and then any containers are brought up afterwards.

Steps correlate to the following:

   Pre) Containers config files generated per hiera settings.
   1) Load Balancer configuration baremetal
     a) step 1 baremetal
     b) step 1 containers
   2) Core Services (Database/Rabbit/NTP/etc.)
     a) step 2 baremetal
     b) step 2 containers
   3) Early Openstack Service setup (Ringbuilder, etc.)
     a) step 3 baremetal
     b) step 3 containers
   4) General OpenStack Services
     a) step 4 baremetal
     b) step 4 containers
     c) Keystone containers post initialization (tenant,service,endpoint creation)
   5) Service activation (Pacemaker), online data migration
     a) step 5 baremetal
     b) step 5 containers

Update steps:
-------------

All services have an associated update_tasks output that is an ansible
snippet that will be run during update in an rolling update that is
expected to run in a rolling update fashion (one node at a time)

For Controller (where pacemaker is running) we have the following states:
 1. Step=1: stop the cluster on the updated node;
 2. Step=2: Pull the latest image and retag the it pcmklatest
 3. Step=3: yum upgrade happens on the host.
 4. Step=4: Restart the cluster on the node
 5. Step=5: Verification:
    Currently we test that the pacemaker services are running.

Then the usual deploy steps are run which pull in the latest image for
all containerized services and the updated configuration if any.

Note: as pacemaker is not containerized, the points 1 and 4 happen in
deployment/pacemaker/pacemaker-baremetal-puppet.yaml.

Fast-forward Upgrade Steps
--------------------------

Each service template may optionally define a `fast_forward_upgrade_tasks` key,
which is a list of Ansible tasks to be performed during the fast-forward
upgrade process. As with Upgrade steps each task is associated to a particular
step provided as a variable and used along with a release variable by a basic
conditional that determines when the task should run.

Steps are broken down into two categories, prep tasks executed across all hosts
and bootstrap tasks executed on a single host for a given role.

The individual steps then correspond to the following tasks during the upgrade:

Prep steps:

- Step=0: Check running services
- Step=1: Stop the service
- Step=2: Stop the cluster
- Step=3: Update repos

Bootstrap steps:

- Step=4: DB backups
- Step=5: Pre package update commands
- Step=6: Package updates
- Step=7: Post package update commands
- Step=8: DB syncs
- Step=9: Verification

Input Parameters
----------------

Each service may define its own input parameters and defaults.
Operators will use the parameter_defaults section of any Heat
environment to set per service parameters.

Apart from sevice specific inputs, there are few default parameters for all
the services. Following are the list of default parameters:

 * ServiceData: Mapping of service specific data. It is used to encapsulate
   all the service specific data. As of now, it contains net_cidr_map, which
   contains the CIDR map for all the networks. Additional data will be added
   as and when required.

 * ServiceNetMap: Mapping of service_name -> network name. Default mappings
   for service to network names are defined in
   ../network/service_net_map.j2.yaml, which may be overridden via
   ServiceNetMap values added to a user environment file via
   parameter_defaults.

 * EndpointMap: Mapping of service endpoint -> protocol. Contains a mapping of
   endpoint data generated for all services, based on the data included in
   ../network/endpoints/endpoint_data.yaml.

 * DefaultPasswords: Mapping of service -> default password. Used to pass some
   passwords from the parent templates, this is a legacy interface and should
   not be used by new services.

 * RoleName: Name of the role on which this service is deployed. A service can
   be deployed in multiple roles. This is an internal parameter (should not be
   set via environment file), which is fetched from the name attribute of the
   roles_data.yaml template.

 * RoleParameters: Parameter specific to a role on which the service is
   applied. Using the format "<RoleName>Parameters" in the parameter_defaults
   of user environment file, parameters can be provided for a specific role.
   For example, in order to provide a parameter specific to "Compute" role,
   below is the format::

      parameter_defaults:
        ComputeParameters:
          Param1: value

Update Steps
------------

Each service template may optionally define a `update_tasks` key,
which is a list of ansible tasks to be performed during the minor
update process. These are executed in a rolling manner node-by-node.

We allow a series of steps for the per-service update sequence via
conditionals referencing a step variable e.g `when: step|int == 2`.

Pre-upgrade Rolling Steps
-------------------------

Each service template may optionally define a
`pre_upgrade_rolling_tasks` key, which is a list of ansible tasks to
be performed before the main upgrade phase, and these tasks are
executed in a node-by-node rolling manner on the overcloud, similarly as `update_tasks`.

Upgrade Steps
-------------

Each service template may optionally define a `upgrade_tasks` key, which is a
list of ansible tasks to be performed during the upgrade process.

Similar to the `update_tasks`, we allow a series of steps for the
per-service upgrade sequence, defined as ansible tasks with a "when:
step|int == 1" for the first step, "== 2" for the second, etc.

   Steps correlate to the following:

   1) Perform any pre-upgrade validations.

   2) Stop the control-plane services, e.g disable LoadBalancer, stop
      pacemaker cluster and stop any managed resources.
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
