#!/bin/bash
set -x

# On initial deployment, the pacemaker service is disabled and is-active exits
# 3 in that case, so allow this to fail gracefully.
pacemaker_status=$(systemctl is-active pacemaker || :)

if [ "$pacemaker_status" = "active" ]; then
    pcs property set maintenance-mode=true
fi

# We need to reload haproxy in case the certificate changed because
# puppet doesn't know the contents of the cert file.  We shouldn't
# reload it if it wasn't already active (such as if using external
# loadbalancer or on initial deployment).
haproxy_status=$(systemctl is-active haproxy || :)
if [ "$haproxy_status" = "active" ]; then
    systemctl reload haproxy
fi
