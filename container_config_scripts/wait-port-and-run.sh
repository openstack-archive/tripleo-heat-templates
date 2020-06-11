#!/bin/bash
set -eu

HOST=$1
PORT=$2

echo "$(date -u): Checking whether we can bind to ${HOST}:${PORT}"
while (ss -Htnl src "${HOST}" "sport = :${PORT}" | grep -wq "${PORT}"); do
    echo "$(date -u): ${HOST}:${PORT} still in use, waiting...";
    sleep 10;
done

shift 2
COMMAND="$*"
if [ -z "${COMMAND}" ]; then
    COMMAND="true"
fi
exec $COMMAND
