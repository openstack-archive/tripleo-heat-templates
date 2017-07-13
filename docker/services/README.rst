===============
Docker Services
===============

TripleO docker services are currently built on top of the puppet services.
To do this each of the docker services includes the output of the
t-h-t puppet/service templates where appropriate.

In general global docker specific service settings should reside in these
templates (templates in the docker/services directory.) The required and
optional items are specified in the docker settings section below.

If you are adding a config setting that applies to both docker and
baremetal that setting should (so long as we use puppet) go into the
puppet/services templates themselves.

Building Kolla Images
---------------------

TripleO currently relies on Kolla docker containers. Kolla supports container
customization and we are making use of this feature within TripleO to inject
puppet (our configuration tool of choice) into the Kolla base images. The
undercloud nova-scheduler also requires openstack-tripleo-common to
provide custom filters.

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
   `override file <https://github.com/openstack/tripleo-common/blob/master/contrib/tripleo_kolla_template_overrides.j2>`_
   which can be used to build Kolla packages that work with TripleO, and an
   `example build script <https://github.com/dprince/undercloud_containers/blob/master/build_kolla.sh>_.

Docker settings
---------------
Each service may define an output variable which returns a puppet manifest
snippet that will run at each of the following steps. Earlier manifests
are re-asserted when applying latter ones.

 * config_settings: This setting is generally inherited from the
   puppet/services templates and only need to be appended
   to on accasion if docker specific config settings are required.

 * step_config: This setting controls the manifest that is used to
   create docker config files via puppet. The puppet tags below are
   used along with this manifest to generate a config directory for
   this container.

 * kolla_config: Contains YAML that represents how to map config files
   into the kolla container. This config file is typically mapped into
   the container itself at the /var/lib/kolla/config_files/config.json
   location and drives how kolla's external config mechanisms work.

 * docker_config: Data that is passed to the docker-cmd hook to configure
   a container, or step of containers at each step. See the available steps
   below and the related docker-cmd hook documentation in the heat-agents
   project.

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

     * config_image: The name of the docker image that will be used for
       generating configuration files. This is often the same container
       that the runtime service uses. Some services share a common set of
       config files which are generated in a common base container.

     * step_config: This setting controls the manifest that is used to
       create docker config files via puppet. The puppet tags below are
       used along with this manifest to generate a config directory for
       this container.

 * docker_puppet_tasks: This section provides data to drive the
   docker-puppet.py tool directly. The task is executed only once
   within the cluster (not on each node) and is useful for several
   puppet snippets we require for initialization of things like
   keystone endpoints, database users, etc. See docker-puppet.py
   for formatting.

Docker steps
------------
Similar to baremetal docker containers are brought up in a stepwise manner.
The current architecture supports bringing up baremetal services alongside
of containers. For each step the baremetal puppet manifests are executed
first and then any docker containers are brought up afterwards.

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
   5) Service activation (Pacemaker)
     a) step 5 baremetal
     b) step 5 containers
