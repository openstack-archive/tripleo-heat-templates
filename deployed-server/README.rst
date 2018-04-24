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


os-collect-config
-----------------
os-collect-config on each deployed server must be manually configured to poll
the Heat API for the available SoftwareDeployments. An example configuration
for /etc/os-collect-config.conf looks like:

    [DEFAULT]
    collectors=heat
    command=os-refresh-config

    [heat]
    # you can get these values from stackrc on the undercloud
    user_id=<a user that can connect to heat> # note this must be the ID, not the username
    password=<a password>
    auth_url=<keystone url>
    project_id=<project_id> # note, this must be the ID, not project name
    stack_id=<stack_id>
    resource_name=<resource_name>

Note that the stack_id value is the id of the nested stack containing the
resource (identified by resource_name) implemented by the deployed-server.yaml
templates.

Once the configuration for os-collect-config has been defined, the service
needs to be restarted. Once restarted, it will start polling Heat and applying
the SoftwareDeployments.

A sample script at deployed-server/scripts/get-occ-config.sh is included that
will automatically generate the os-collect-config configuration needed on each
server, ssh to each server, copy the configuration, and restart the
os-collect-config service.

.. warning::
   The get-occ-config.sh script is not intended for production use, as it
   copies admin credentials to each of the deployed nodes.

The script can only be used once the stack id's of the nested deployed-server
stacks have been created via Heat. This usually only takes a couple of minutes
once the deployment command has been started. Once the following output is seen
from the deployment command, the script should be ready to run:

    [Controller]: CREATE_IN_PROGRESS state changed
    [NovaCompute]: CREATE_IN_PROGRESS state changed

The user running the script must be able to ssh as root to each server.  Define
the names of your custom roles (if applicable) and hostnames of the deployed
servers you intend to use for each role type. For each role name, a
corresponding <role-name>_hosts variable should also be defined, e.g.::

    export ROLES="Controller NewtorkNode StorageNode Compute"
    export Controller_hosts="10.0.0.1 10.0.0.2 10.0.0.3"
    export NetworkNode_hosts="10.0.0.4 10.0.0.5 10.0.0.6"
    export StorageNode_hosts="10.0.0.7 10.0.08"
    export Compute_hosts="10.0.0.9 10.0.0.10 10.0.0.11"

Then run the script on the undercloud with a stackrc file sourced, and
the script will copy the needed os-collect-config.conf configuration to each
server and restart the os-collect-config service.
