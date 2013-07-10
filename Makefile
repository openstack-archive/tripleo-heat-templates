NOTCOMPUTE=nova-api.yaml keystone.yaml heat-allinone.yaml glance.yaml neutron.yaml mysql.yaml rabbitmq.yaml

notcompute.yaml: $(NOTCOMPUTE)
	python merge.py --master-role notcompute --slave-roles stateless stateful -- $^ > notcompute.yaml

overcloud.yaml: bootstack-vm.yaml nova-compute-group.yaml
	python merge.py $^ > $@.tmp
	mv $@.tmp $@
