NOTCOMPUTE=nova-api.yaml keystone.yaml heat-allinone.yaml glance.yaml neutron.yaml mysql.yaml rabbitmq.yaml

notcompute.yaml: $(NOTCOMPUTE)
	python merge.py --master-role notcompute --slave-roles stateless stateful -- $^ > notcompute.yaml

overcloud.yaml: overcloud-source.yaml nova-compute-instance.yaml
	python merge.py $< > $@.tmp
	mv $@.tmp $@
