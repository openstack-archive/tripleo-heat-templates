#!/bin/bash
set -eux
# This file contains setup steps that can't be or have not yet been moved to
# puppet

# Disable libvirtd since it conflicts with nova_libvirt container
/usr/bin/systemctl disable libvirtd.service
/usr/bin/systemctl stop libvirtd.service
