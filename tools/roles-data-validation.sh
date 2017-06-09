#!/bin/bash
#
# Copyright 2017 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
set -e

SCRIPT_DIR=$(cd `dirname $0` && pwd -P)
THT_DIR=${OUTPUT_DIR:-$(cd "${SCRIPT_DIR}/../" && pwd -P)}
TMPDIR=$(mktemp -d)

function do_cleanup {
  rm -rf $TMPDIR
}
trap do_cleanup EXIT

function check_diff {
  local thtfile=$1
  local genfile=$2
  echo -n "Performing diff on $thtfile $genfile... "
  diff $thtfile $genfile > $TMPDIR/diff_results
  if [ $? = 1 ]; then
      echo "ERROR: Generated roles file not match the current ${thtfile}"
      echo "Please make sure to update the appropriate roles/* files."
      echo "Here is the diff ${thtfile} ${genfile}"
      cat $TMPDIR/diff_results
      exit 1
  fi
  echo "OK!"
}

OUTPUT_DIR=$TMPDIR
source $SCRIPT_DIR/roles-data-generate-samples.sh

set +e
check_diff $THT_DIR/roles_data.yaml $TMPDIR/roles_data.yaml
check_diff $THT_DIR/roles_data_undercloud.yaml $TMPDIR/roles_data_undercloud.yaml
