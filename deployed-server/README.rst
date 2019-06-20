TripleO with Deployed Servers
=============================

The deployed-server set of templates can be used to deploy TripleO via
tripleo-heat-templates to servers that are already installed with a base
operating system.

When OS::TripleO::Server is mapped to the deployed-server.yaml template via the
provided deployed-server-environment.yaml resource registry, Nova and Ironic
are not used to create any server instances. Heat continues to create the
SoftwareDeployment resources, and they are made available to the already
deployed and running servers.

Template Usage
--------------
To use these templates pass the included environment file to the deployment
command::

    -e environments/deployed-server-environment.yaml

Deployed Server configuration
-----------------------------
It is currently assumed that the deployed servers being used have the required
set of software and packages already installed on them. These exact
requirements must match how such a server would look if it were deployed the
standard way via Ironic using the TripleO overcloud-full image.

An easy way to help get this setup for development is to use an overcloud-full
image from an already existing TripleO setup. Create the vm's for the already
deployed server, and use the overcloud-full image as their disk.

Each server must have a fqdn set that resolves to an IP address on a routable
network (e.g., the hostname should not resolve to 127.0.0.1).  The hostname
will be detected on each server via the hostnamectl --static command.

Each server also must have a route to the configured IP address on the
undercloud where the OpenStack services are listening. This is the value for
local_ip in the undercloud.conf.

It's recommended that each server have at least 2 nic's. One used for external
management such as ssh, and one used for the OpenStack deployment itself. Since
the overcloud deployment will reconfigure networking on the configured nic to
be used by OpenStack, the external management nic is needed as a fallback so
that all connectivity is not lost in case of a configuration error. Be sure to
use correct nic config templates as needed, since the nodes will not receive
dhcp from the undercloud neutron-dhcp-agent service.

For example, the net-config-static-bridge.yaml template could be used for
controllers, and the net-config-static.yaml template could be used for computes
by specifying:

resource_registry:
  OS::TripleO::Controller::Net::SoftwareConfig: /home/stack/deployed-server/tripleo-heat-templates/net-config-static-bridge.yaml
  OS::TripleO::Compute::Net::SoftwareConfig: /home/stack/deployed-server/tripleo-heat-templates/net-config-static.yaml

In a setup where the first nic on the servers is used for external management,
set the nic's to be used for OpenStack to nic2:

parameter_defaults:
  NeutronPublicInterface: nic2
  HypervisorNeutronPublicInterface: nic2

The above nic config templates also require a route to the ctlplane network to
be defined. Define the needed parameters as necessary for your environment, for
example:

parameter_defaults:
  ControlPlaneDefaultRoute: 192.168.122.130
  ControlPlaneSubnetCidr: "24"
  EC2MetadataIp: "192.168.24.1"

In this example, 192.168.122.130 is the external management IP of an
undercloud, thus it is the default route for the configured local_ip value of
192.168.24.1.
