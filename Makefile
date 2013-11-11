overcloud.yaml: overcloud-source.yaml nova-compute-instance.yaml swift-source.yaml
	# $^ won't work here because we want to list nova-compute-instance.yaml as
	# a prerequisite but don't want to pass it into merge.py
	python merge.py overcloud-source.yaml swift-source.yaml > $@.tmp
	mv $@.tmp $@

undercloud-vm-tuskar.yaml: undercloud-vm.yaml tuskar-source.yaml
	python merge.py $^ > $@.tmp
	mv $@.tmp $@

undercloud-vm-ironic.yaml: undercloud-vm.yaml ironic-source.yaml
	python merge.py $^ > $@.tmp
	mv $@.tmp $@

test:
	@bash test_merge.bash
