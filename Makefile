NOTCOMPUTE=nova-api.yaml keystone.yaml heat-allinone.yaml glance.yaml quantum.yaml mysql.yaml rabbitmq.yaml

notcompute.yaml: $(NOTCOMPUTE)
	python merge.py --master-role notcompute --slave-roles stateless stateful -- $(NOTCOMPUTE) > notcompute.yaml
