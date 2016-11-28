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

Steps
-----

Each service may define an output variable which returns a puppet manifest
snippet that will run at each of the following steps. Earlier manifests
are re-asserted when applying latter ones.

 * config_settings: Custom hiera settings for this service. These are
   used to generate configs.

 * step_config: A puppet manifest that is used to step through the deployment
   sequence. Each sequence is given a "step" (via hiera('step') that provides
   information for when puppet classes should activate themselves.

 * docker_compose:

 * container_name:

 * volumes:

Steps correlate to the following:

   1) Service configuration generation with puppet.

   2) Early Openstack Service setup (database init?)

   3) Early containerized networking services startup (OVS)

   4) Network configuration

   5) General OpenStack Services

   6) Service activation (Pacemaker)

   7) Fencing (Pacemaker)

