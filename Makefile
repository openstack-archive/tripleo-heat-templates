generated_templates =                         \
        overcloud.yaml                        \
        overcloud-with-block-storage-nfs.yaml \
        undercloud-vm.yaml                    \
        undercloud-bm.yaml                    \
        undercloud-vm-ironic.yaml

# Files included in overcloud-source.yaml via FileInclude
overcloud_source_deps = nova-compute-instance.yaml

all: $(generated_templates)

overcloud.yaml: overcloud-source.yaml block-storage.yaml swift-deploy.yaml swift-source.yaml swift-storage-source.yaml ssl-source.yaml nova-compute-config.yaml $(overcloud_source_deps)
	python ./tripleo_heat_merge/merge.py --scale NovaCompute=$${COMPUTESCALE:-'1'} --scale controller=$${CONTROLSCALE:-'1'} --scale SwiftStorage=$${SWIFTSTORAGESCALE='0'} --scale BlockStorage=$${BLOCKSTORAGESCALE='0'} overcloud-source.yaml block-storage.yaml swift-source.yaml swift-storage-source.yaml ssl-source.yaml swift-deploy.yaml nova-compute-config.yaml > $@.tmp
	mv $@.tmp $@

overcloud-with-block-storage-nfs.yaml: overcloud-source.yaml block-storage-nfs.yaml nfs-server-source.yaml swift-source.yaml swift-storage-source.yaml ssl-source.yaml $(overcloud_source_deps)
	# $^ won't work here because we want to list nova-compute-instance.yaml as
	# a prerequisite but don't want to pass it into merge.py
	python ./tripleo_heat_merge/merge.py --scale NovaCompute=$${COMPUTESCALE:-'1'} --scale controller=$${CONTROLSCALE:-'1'} --scale SwiftStorage=$${SWIFTSTORAGESCALE='0'} --scale BlockStorage=$${BLOCKSTORAGESCALE:-'1'} overcloud-source.yaml block-storage-nfs.yaml nfs-server-source.yaml swift-source.yaml swift-storage-source.yaml ssl-source.yaml > $@.tmp
	mv $@.tmp $@

undercloud-vm.yaml: undercloud-source.yaml undercloud-vm-nova-config.yaml undercloud-vm-nova-deploy.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

undercloud-bm.yaml: undercloud-source.yaml undercloud-bm-nova-config.yaml undercloud-bm-nova-deploy.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

undercloud-vm-ironic.yaml: undercloud-source.yaml undercloud-vm-ironic-config.yaml undercloud-vm-ironic-deploy.yaml
	python ./tripleo_heat_merge/merge.py $^ > $@.tmp
	mv $@.tmp $@

check: test

test:
	@bash test_merge.bash

clean:
	rm -f $(generated_templates)

.PHONY: clean overcloud.yaml check
