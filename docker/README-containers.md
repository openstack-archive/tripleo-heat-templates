# Using Docker Containers With TripleO

## Configuring TripleO with to use a container based compute node.

Steps include:
- Adding a base OS image to glance
- Deploy an overcloud configured to use the docker compute heat templates

## Getting base OS image working.

Download the fedora atomic image into glance:

```
wget https://download.fedoraproject.org/pub/fedora/linux/releases/22/Cloud/x86_64/Images/Fedora-Cloud-Atomic-22-20150521.x86_64.qcow2
glance image-create --name atomic-image --file Fedora-Cloud-Atomic-22-20150521.x86_64.qcow2 --disk-format qcow2 --container-format bare
```

## Configuring TripleO

You can use the tripleo.sh script up until the point of running the Overcloud.
https://github.com/openstack/tripleo-common/blob/master/scripts/tripleo.sh

Create the Overcloud:
```
$ openstack overcloud deploy --templates=tripleo-heat-templates -e tripleo-heat-templates/environments/docker.yaml -e tripleo-heat-templates/environments/docker-network.yaml --libvirt-type=qemu
```

Using Network Isolation in the Overcloud:
```
$ openstack overcloud deploy --templates=tripleo-heat-templates -e tripleo-heat-templates/environments/docker.yaml -e tripleo-heat-templates/environments/docker-network-isolation.yaml --libvirt-type=qemu
```

Source the overcloudrc and then you can use the overcloud.

## Debugging

You can ssh into the controller/compute nodes by using the heat key, eg:
```
nova list
ssh heat-admin@<compute_node_ip>
```

You can check to see what docker containers are running:
```
sudo docker ps -a
```

To enter a container that doesn't seem to be working right:
```
sudo docker exec -ti <container name> /bin/bash
```

Then you can check logs etc.

You can also just do a 'docker logs' on a given container.
