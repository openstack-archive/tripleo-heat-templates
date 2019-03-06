#!/bin/bash
# Copyright 2018 Red Hat Inc.
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
# Usage: pyshim.sh <script and/or arguments>
#
# Unfortunately THT doesn't know which version of python might be in a
# container so we need this script to be able to try python3 or python2
# depending on availability.  Since this is a temporary shim until we've
# fully cut over to python3, we check for the existance of python3 first
# before falling back to python2. This will help in the transition from
# python2 based containers to python3.

show_usage() {
    echo "Usage: pyshim.sh <script and/or arguments>"
}

if [ $# -lt 1 ]
then
    show_usage
    exit 1
fi

set -x
if command -v python3 >/dev/null; then
    python3 "$@"
elif command -v python2 >/dev/null; then
    python2 "$@"
elif command -v python >/dev/null; then
    python "$@"
else
    echo "ERROR: python is not available!"
    exit 1
fi
