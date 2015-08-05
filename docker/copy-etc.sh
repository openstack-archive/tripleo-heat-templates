#!/bin/bash
echo "Copying agent container /etc to /var/lib/etc-data"
cp -a /etc/* /var/lib/etc-data/
