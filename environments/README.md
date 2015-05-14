This directory contains Heat environment file snippets which can
be used to enable features in the Overcloud.

Configuration
-------------

These can be enabled using the -e [path to environment yaml] option with
heatclient.

Below is an example of how to enable the Ceph template using
devtest\_overcloud.sh:

    export OVERCLOUD\_CUSTOM\_HEAT\_ENV=$TRIPLEO\_ROOT/tripleo-heat-templates/environments/ceph_devel.yaml
