#!/bin/bash
# Copyright 2020 Red Hat Inc.
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

OUT=$( sudo -u glance -E /usr/local/bin/kolla_start 2>&1 ) || if [[ $OUT =~ train ]]; then
    echo 'DB is already up to date'
else
    echo $OUT
    exit 1
fi
