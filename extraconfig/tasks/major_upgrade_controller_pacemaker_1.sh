#!/bin/bash

set -eu

# Migrate to HA NG
if [[ -n $(is_bootstrap_node) ]]; then
    migrate_full_to_ng_ha
fi
