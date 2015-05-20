This directory contains Heat templates to help configure
Vlans on a bonded pair of NICs for each Overcloud role.

Configuration
-------------

To make use of these templates create a Heat environment that looks
something like this:

  resource\_registry:
    OS::TripleO::BlockStorage::Net::SoftwareConfig: network/config/bond-with-vlans/cinder-storage.yaml
    OS::TripleO::Compute::Net::SoftwareConfig: network/config/bond-with-vlans/compute.yaml
    OS::TripleO::Controller::Net::SoftwareConfig: network/config/bond-with-vlans/controller.yaml
    OS::TripleO::ObjectStorage::Net::SoftwareConfig: network/config/bond-with-vlans/swift-storage.yaml
    OS::TripleO::CephStorage::Net::SoftwareConfig: network/config/bond-with-vlans/ceph-storage.yaml
