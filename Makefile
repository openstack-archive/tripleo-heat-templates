generated_templates =                \
        overcloud.yaml               \
        undercloud-vm.yaml           \
        undercloud-bm.yaml           \
        undercloud-vm-tuskar.yaml    \
        undercloud-vm-ironic.yaml

# Files included in overcloud-source.yaml via FileInclude
overcloud_source_deps = nova-compute-instance.yaml

all: $(generated_templates)

overcloud.yaml: overcloud-source.yaml swift-source.yaml $(overcloud_source_deps)
	python ./tripleo_heat_merge/merge.py overcloud-source.yaml swift-source.yaml > $@.tmp
	mv $@.tmp $@

undercloud-vm.yaml: undercloud-source.yaml undercloud-vm-source.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

undercloud-bm.yaml: undercloud-source.yaml undercloud-bm-source.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

undercloud-vm-tuskar.yaml: undercloud-source.yaml undercloud-vm-source.yaml tuskar-source.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

undercloud-vm-ironic.yaml: undercloud-source.yaml undercloud-vm-source.yaml ironic-source.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

test:
	@bash test_merge.bash

clean:
	rm -f $(generated_templates)
