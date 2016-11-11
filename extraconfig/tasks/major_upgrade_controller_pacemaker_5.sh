#!/bin/bash

set -eu

if [[ -n $(is_bootstrap_node) ]]; then
  # run gnocchi upgrade
  gnocchi-upgrade
fi
