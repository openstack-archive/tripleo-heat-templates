#!/bin/bash

# This needs to be run after os-net-config. since os-net-config potentially can
# restart network interfaces, which would affects VIPs controlled by
# keepalived.

# TODO(hjensas): Remove this when we have keepalived 2.0.6 or later.
docker container restart keepalived || true
