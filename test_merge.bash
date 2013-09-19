#!/bin/bash
set -ue
result=""
cleanup() {
    if [ -n "$result" ] ; then
        rm -f $result
    fi
}
trap cleanup EXIT
result=$(mktemp /tmp/test_merge.XXXXXX)
fail=0
python merge.py examples/source.yaml > $result
if ! cmp $result examples/source_lib_result.yaml ; then
    diff -u $result examples/source_lib_result.yaml
    echo
    echo FAIL - merge of source.yaml result does not match expected output
    echo
    fail=1
else
    echo
    echo PASS - merge of source.yaml result matches expected output
    echo
fi
exit $fail
