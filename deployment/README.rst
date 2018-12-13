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
