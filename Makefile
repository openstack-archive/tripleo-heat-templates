generated_templates =                         \
        overcloud.yaml                        \
        overcloud-with-block-storage-nfs.yaml \
        undercloud-vm.yaml                    \
        undercloud-bm.yaml                    \
        undercloud-vm-ironic.yaml             \
        undercloud-vm-ironic-vlan.yaml

# Files included in overcloud-source.yaml via FileInclude
overcloud_source_deps = nova-compute-instance.yaml

all: $(generated_templates)
VALIDATE := $(patsubst %,validate-%,$(generated_templates))
validate-all: $(VALIDATE)
$(VALIDATE):
	heat template-validate -f $(subst validate-,,$@)

# You can define in CONTROLEXTRA one or more additional YAML files to further extend the template, some additions could be:
# - overcloud-vlan-port.yaml to activate the VLAN auto-assignment from Neutron
# - nfs-source.yaml to configure Cinder with NFS
overcloud.yaml: overcloud-source.yaml block-storage.yaml swift-deploy.yaml swift-source.yaml swift-storage-source.yaml ssl-source.yaml nova-compute-config.yaml $(overcloud_source_deps)
	python ./tripleo_heat_merge/merge.py --hot --scale NovaCompute=$${COMPUTESCALE:-'1'} --scale controller=$${CONTROLSCALE:-'1'} --scale SwiftStorage=$${SWIFTSTORAGESCALE:-'0'} --scale BlockStorage=$${BLOCKSTORAGESCALE:-'0'} overcloud-source.yaml block-storage.yaml swift-source.yaml swift-storage-source.yaml ssl-source.yaml swift-deploy.yaml nova-compute-config.yaml ${CONTROLEXTRA} > $@.tmp
	mv $@.tmp $@

undercloud-vm.yaml: undercloud-source.yaml undercloud-vm-nova-config.yaml undercloud-vm-nova-deploy.yaml
	python ./tripleo_heat_merge/merge.py --hot $^ > $@.tmp
	mv $@.tmp $@

undercloud-bm.yaml: undercloud-source.yaml undercloud-bm-nova-config.yaml undercloud-bm-nova-deploy.yaml
	python ./tripleo_heat_merge/merge.py --hot $^ > $@.tmp
	mv $@.tmp $@

undercloud-vm-ironic.yaml: undercloud-source.yaml undercloud-vm-ironic-config.yaml undercloud-vm-ironic-deploy.yaml
	python ./tripleo_heat_merge/merge.py --hot $^ > $@.tmp
	mv $@.tmp $@

undercloud-vm-ironic-vlan.yaml: undercloud-source.yaml undercloud-vm-ironic-config.yaml undercloud-vm-ironic-deploy.yaml undercloud-vlan-port.yaml
	python ./tripleo_heat_merge/merge.py --hot $^ > $@.tmp
	mv $@.tmp $@

check: test

test:
	@bash test_merge.bash

clean:
	rm -f $(generated_templates)

.PHONY: clean overcloud.yaml check
