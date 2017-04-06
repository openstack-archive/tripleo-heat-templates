========================
Team and repository tags
========================

.. image:: http://governance.openstack.org/badges/tripleo-heat-templates.svg
    :target: http://governance.openstack.org/reference/tags/index.html

.. Change things from this point on

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


Service testing matrix
----------------------

The configuration for the CI scenarios will be defined in `tripleo-heat-templates/ci/`
and should be executed according to the following table:

+----------------+-------------+-------------+-------------+-------------+-----------------+
|        -       | scenario001 | scenario002 | scenario003 | scenario004 | multinode-nonha |
+================+=============+=============+=============+=============+=================+
| keystone       |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| glance         |    rbd      |    swift    |    file     | swift + rbd |      swift      |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| cinder         |     rbd     |    iscsi    |             |             |      iscsi      |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| heat           |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| mysql          |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| neutron        |     ovs     |     ovs     |     ovs     |     ovs     |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| rabbitmq       |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| mongodb        |      X      |      X      |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| redis          |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| haproxy        |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| keepalived     |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| memcached      |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| pacemaker      |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| nova           |     qemu    |     qemu    |     qemu    |     qemu    |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| ntp            |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| snmp           |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| timezone       |      X      |      X      |      X      |      X      |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| sahara         |             |             |      X      |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| mistral        |             |             |      X      |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| swift          |             |      X      |             |             |        X        |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| aodh           |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| ceilometer     |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| gnocchi        |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| panko          |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| barbican       |             |      X      |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| zaqar          |             |      X      |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| ec2api         |             |      X      |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| cephrgw        |             |      X      |             |      X      |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| tacker         |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| congress       |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| cephmds        |             |             |             |      X      |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| manila         |             |             |             |      X      |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| collectd       |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| fluentd        |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
| sensu-client   |      X      |             |             |             |                 |
+----------------+-------------+-------------+-------------+-------------+-----------------+
