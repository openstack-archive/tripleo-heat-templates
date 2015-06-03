This directory contains Heat templates to help configure
Vlans on a single NICs for each Overcloud role.

Configuration
-------------

To make use of these templates create a Heat environment that looks
something like this:

  resource\_registry:
    OS::TripleO::BlockStorage::Net::SoftwareConfig: network/config/single-nic-vlans/cinder-storage.yaml
    OS::TripleO::Compute::Net::SoftwareConfig: network/config/single-nic-vlans/compute.yaml
    OS::TripleO::Controller::Net::SoftwareConfig: network/config/single-nic-vlans/controller.yaml
    OS::TripleO::ObjectStorage::Net::SoftwareConfig: network/config/single-nic-vlans/swift-storage.yaml
    OS::TripleO::CephStorage::Net::SoftwareConfig: network/config/single-nic-vlans/ceph-storage.yaml

Or use this Heat environment file:

  environments/net-single-nic-with-vlans.yaml
