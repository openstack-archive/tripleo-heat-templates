#!/bin/bash
set -ue
result=""
cleanup() {
    if [ -n "$result" ] ; then
        rm -f $result
    fi
}
trap cleanup EXIT
run_test() {
    local cmd=$1
    local expected=$2
    result=$(mktemp /tmp/test_merge.XXXXXX)
    fail=0
    $cmd > $result
    if ! cmp $result $expected ; then
        diff -u $expected $result || :
        echo FAIL - $cmd result does not match expected
        fail=1
    else
        echo PASS - $cmd
    fi
    cleanup
}
echo
run_test "python merge.py examples/source.yaml" examples/source_lib_result.yaml
echo
trap - EXIT
exit $fail
