This directory contains Heat templates to help configure
multiple NICs for each Overcloud role, where it is
assumed that each NIC is running a specific network
traffic type and that VLANs are not being used.

Configuration
-------------

To make use of these templates create a Heat environment that looks
something like this:

  resource\_registry:
    OS::TripleO::BlockStorage::Net::SoftwareConfig: network/config/multiple-nics/cinder-storage.yaml
    OS::TripleO::Compute::Net::SoftwareConfig: network/config/multiple-nics/compute.yaml
    OS::TripleO::Controller::Net::SoftwareConfig: network/config/multiple-nics/controller.yaml
    OS::TripleO::ObjectStorage::Net::SoftwareConfig: network/config/multiple-nics/swift-storage.yaml
    OS::TripleO::CephStorage::Net::SoftwareConfig: network/config/multiple-nics/ceph-storage.yaml

Or use this Heat environment file:

  environments/net-multiple-nics.yaml

Configuration with System Management Network
--------------------------------------------

To enable the optional System Management network, create a Heat environment
that looks something like this:

  resource\_registry:
    OS::TripleO::Network::Management: ../network/management.yaml
    OS::TripleO::Controller::Ports::ManagementPort: ../network/ports/management.yaml
    OS::TripleO::Compute::Ports::ManagementPort: ../network/ports/management.yaml
    OS::TripleO::CephStorage::Ports::ManagementPort: ../network/ports/management.yaml
    OS::TripleO::SwiftStorage::Ports::ManagementPort: ../network/ports/management.yaml
    OS::TripleO::BlockStorage::Ports::ManagementPort: ../network/ports/management.yaml

Or use this Heat environment file:

  environments/network-management.yaml
