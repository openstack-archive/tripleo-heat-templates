Roles
=====

The yaml files in this directory can be combined into a single roles_data.yaml
and be used with TripleO to create custom deployments.

Use tripleoclient to build your own custom roles_data.yaml for your
environment.

roles_data.yaml
---------------

The roles_data.yaml specifies which roles (groups of nodes) will be deployed.
Note this file is used as an input to the various \*.j2.yaml jinja2 templates,
so that they are converted into \*.yaml during the plan creation. This occurs
via a mistral action/workflow. The file format of this file is a yaml list.

Role YAML files
===============

Each role yaml file should contain only a single role. The filename should
match the role name. The name of the role is  mandatory and must be unique.

The role files in this folder should contain at least a role name and the
default list of services for the role.

Role Options
------------

* CountDefault: (number) optional, default number of nodes, defaults to 0
  sets the default for the {{role.name}}Count parameter in overcloud.yaml

* HostnameFormatDefault: (string) optional default format string for hostname
  defaults to '%stackname%-{{role.name.lower()}}-%index%'
  sets the default for {{role.name}}HostnameFormat parameter in overcloud.yaml

* ImageDefault: (string) optional default image name or ID, defaults to
  overcloud-full

* FlavorDefault: (string) optional default flavor name or ID, defaults to
  baremetal

* RoleParametersDefault: (map) optional default to the per-role RoleParameters
  value, this enables roles to specify specific values appropriate to their
  configuration, defaults to an empty map.

* upgrade_batch_size: (number): batch size for upgrades where tasks are
  specified by services to run in batches vs all nodes at once.
  This defaults to 1, but larger batches may be specified here.

* ServicesDefault: (list) optional default list of services to be deployed
  on the role, defaults to an empty list. Sets the default for the
  {{role.name}}Services parameter in overcloud.yaml

* tags: (list) list of tags used by other parts of the deployment process to
  find the role for a specific type of functionality. Currently a role
  with both 'primary' and 'controller' is used as the primary role for the
  deployment process. If no roles have 'primary' and 'controller', the
  first role in this file is used as the primary role.
  The third tag that can be defined here is external_bridge, which is used
  to define which node must have a bridge created in a multiple-nic network
  config.

* description: (string) as few sentences describing the role and information
  pertaining to the usage of the role.

 * networks: (list), optional list of networks which the role will have
   access to when network isolation is enabled. The names should match
   those defined in network_data.yaml.

 * networks_skip_config: (list), optional list of networks for which the
   configuration would be skipped for the role. The names should match
   those defined in network_data.yaml

Working with Roles
==================
The tripleoclient provides a series of commands that can be used to view
roles and generate a roles_data.yaml file for deployment.

Listing Available Roles
-----------------------
The ``openstack overcloud role list`` command can be used to view the list
of roles provided by tripleo-heat-templates.

Usage
^^^^^
.. code-block::

  usage: openstack overcloud role list [-h] [--roles-path <roles directory>]

  List availables roles

  optional arguments:
    -h, --help            show this help message and exit
    --roles-path <roles directory>
                          Filesystem path containing the role yaml files. By
                          default this is /usr/share/openstack-tripleo-heat-
                          templates/roles

Example
^^^^^^^
.. code-block::

  [user@host ~]$ openstack overcloud role list
  BlockStorage
  CephStorage
  Compute
  ComputeOvsDpdk
  ComputeSriov
  Controller
  ControllerOpenstack
  Database
  Messaging
  Minimal
  Networker
  ObjectStorage
  Telemetry
  Undercloud

Viewing Role Details
--------------------
The ``openstack overcloud role show`` command can be used as a quick way to
view some of the information about a role.

Usage
^^^^^
.. code-block::

  usage: openstack overcloud role show [-h] [--roles-path <roles directory>]
                                       <role>

  Show information about a given role

  positional arguments:
    <role>                Role to display more information about.

  optional arguments:
    -h, --help            show this help message and exit
    --roles-path <roles directory>
                          Filesystem path containing the role yaml files. By
                          default this is /usr/share/openstack-tripleo-heat-
                          templates/roles

Example
^^^^^^^
.. code-block::

  [user@host ~]$ openstack overcloud role show Compute
  ###############################################################################
  # Role Data for 'Compute'
  ###############################################################################
  HostnameFormatDefault: '%stackname%-novacompute-%index%'
  ServicesDefault:
   * OS::TripleO::Services::AuditD
   * OS::TripleO::Services::CACerts
   * OS::TripleO::Services::CephClient
   * OS::TripleO::Services::CephExternal
   * OS::TripleO::Services::CertmongerUser
   * OS::TripleO::Services::Collectd
   * OS::TripleO::Services::ComputeCeilometerAgent
   * OS::TripleO::Services::ComputeNeutronCorePlugin
   * OS::TripleO::Services::ComputeNeutronL3Agent
   * OS::TripleO::Services::ComputeNeutronMetadataAgent
   * OS::TripleO::Services::ComputeNeutronOvsAgent
   * OS::TripleO::Services::Iscsid
   * OS::TripleO::Services::Kernel
   * OS::TripleO::Services::MySQLClient
   * OS::TripleO::Services::NeutronSriovAgent
   * OS::TripleO::Services::NeutronVppAgent
   * OS::TripleO::Services::NovaCompute
   * OS::TripleO::Services::NovaLibvirt
   * OS::TripleO::Services::NovaMigrationTarget
   * OS::TripleO::Services::Podman
   * OS::TripleO::Services::Securetty
   * OS::TripleO::Services::Snmp
   * OS::TripleO::Services::Sshd
   * OS::TripleO::Services::Timesync
   * OS::TripleO::Services::Timezone
   * OS::TripleO::Services::TripleoFirewall
   * OS::TripleO::Services::TripleoPackages
   * OS::TripleO::Services::Vpp
  name: 'Compute'

Generate roles_data.yaml
------------------------
The ``openstack overcloud roles generate`` command can be used to generate
a roles_data.yaml file for deployments.

Usage
^^^^^
.. code-block::

  usage: openstack overcloud roles generate [-h]
                                            [--roles-path <roles directory>]
                                            [-o <output file>]
                                            <role> [<role> ...]

  Generate roles_data.yaml file

  positional arguments:
    <role>                List of roles to use to generate the roles_data.yaml
                          file for the deployment. NOTE: Ordering is important
                          if no role has the "primary" and "controller" tags. If
                          no role is tagged then the first role listed will be
                          considered the primary role. This usually is the
                          controller role.

  optional arguments:
    -h, --help            show this help message and exit
    --roles-path <roles directory>
                          Filesystem path containing the role yaml files. By
                          default this is /usr/share/openstack-tripleo-heat-
                          templates/roles
    -o <output file>, --output-file <output file>
                          File to capture all output to. For example,
                          roles_data.yaml

Example
^^^^^^^
.. code-block::

  [user@host ~]$ openstack overcloud roles generate -o roles_data.yaml Controller Compute BlockStorage ObjectStorage CephStorage
