#!/bin/bash
set -e

# Report an error if the generated sample environments are not in sync with
# the current configuration and templates.

echo 'Verifying that generated environments are in sync'

tmpdir=$(mktemp -d)
trap "rm -rf $tmpdir" EXIT

./tripleo_heat_templates/environment_generator.py sample-env-generator/ $tmpdir/environments

base=$PWD
retval=0

cd $tmpdir

file_list=$(find environments -type f)
for f in $file_list; do
    if ! $base/tools/yaml-diff.py $f $base/$f; then
        echo "ERROR: $base/$f is not up to date"
        diff $f $base/$f
        retval=1
    fi
done

exit $retval
