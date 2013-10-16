overcloud.yaml: overcloud-source.yaml nova-compute-instance.yaml
	python merge.py $< > $@.tmp
	mv $@.tmp $@

undercloud-vm-tuskar.yaml: undercloud-vm.yaml tuskar-source.yaml
	python merge.py $^ > $@.tmp
	mv $@.tmp $@

test:
	@bash test_merge.bash
