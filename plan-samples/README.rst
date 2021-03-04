=================================
Samples for plan-environment.yaml
=================================

The ``plan-environment.yaml`` file provides the details of playbooks
and their parameters required for use cases like derived parameter
workflow. It has a section ``playbook_parameters`` that is used to
specify playbook name and playbooks parameters.

These plan environment files can be provided as with ``-p`` option
to the ``openstack overcloud deploy``.

The sample format to provide the playbook specific parameters::

  playbook_parameters:
    cli-derive-parameters.yaml:
      # DPDK Parameters
      num_phy_cores_per_numa_node_for_pmd: 2
