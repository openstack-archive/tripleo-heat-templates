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
    $cmd --output $result
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
merge_py="./tripleo_heat_merge/merge.py"
run_test "python $merge_py examples/source.yaml" examples/source_lib_result.yaml
run_test "python $merge_py examples/source2.yaml" examples/source2_lib_result.yaml
run_test "python $merge_py examples/source_include_subkey.yaml" examples/source_include_subkey_result.yaml
run_test "python $merge_py examples/launchconfig1.yaml examples/launchconfig2.yaml" examples/launchconfig_result.yaml
run_test "python $merge_py --scale NovaCompute=3 examples/scale1.yaml" examples/scale_result.yaml
run_test "python $merge_py --scale NovaCompute=3 examples/scale_map.yaml" examples/scale_map_result.yaml
run_test "python $merge_py --hot examples/source_hot.yaml" examples/source_lib_result_hot.yaml
run_test "python $merge_py --hot examples/source2_hot.yaml" examples/source2_lib_result_hot.yaml
run_test "python $merge_py --hot examples/source_include_subkey_hot.yaml" examples/source_include_subkey_result_hot.yaml
run_test "python $merge_py --hot examples/launchconfig1_hot.yaml examples/launchconfig2_hot.yaml" examples/launchconfig_result_hot.yaml
run_test "python $merge_py --hot --scale NovaCompute=3 examples/scale1_hot.yaml" examples/scale_result_hot.yaml
run_test "python $merge_py --hot --scale NovaCompute=3 examples/scale_map_hot.yaml" examples/scale_map_result_hot.yaml
run_test "python $merge_py --hot --scale NovaCompute=5,1,2 examples/scale_map_hot.yaml" examples/scale_map_result_hot_blacklist.yaml
run_test "python $merge_py --hot --scale NovaCompute=3, examples/scale_map_hot.yaml" examples/scale_map_result_hot.yaml
echo
trap - EXIT
exit $fail
