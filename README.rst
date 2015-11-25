======================
tripleo-heat-templates
======================

Heat templates to deploy OpenStack using OpenStack.

* Free software: Apache license
* Documentation: http://docs.openstack.org/developer/tripleo-docs
* Source: http://git.openstack.org/cgit/openstack/tripleo-heat-templates
* Bugs: http://bugs.launchpad.net/tripleo

Features
--------

The ability to deploy a multi-node, role based OpenStack deployment using
OpenStack Heat. Notable features include:

 * Choice of deployment/configuration tooling: puppet, (soon) docker

 * Role based deployment: roles for the controller, compute, ceph, swift,
   and cinder storage

 * physical network configuration: support for isolated networks, bonding,
   and standard ctlplane networking

Directories
-----------

A description of the directory layout in TripleO Heat Templates.

 * environments: contains heat environment files that can be used with -e
                 on the command like to enable features, etc.

 * extraconfig: templates used to enable 'extra' functionality. Includes
                functionality for distro specific registration and upgrades.

 * firstboot: example first_boot scripts that can be used when initially
              creating instances.

 * network: heat templates to help create isolated networks and ports

 * puppet: templates mostly driven by configuration with puppet. To use these
           templates you can use the overcloud-resource-registry-puppet.yaml.

 * validation-scripts: validation scripts useful to all deployment
                       configurations
