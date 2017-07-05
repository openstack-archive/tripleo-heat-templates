=================================
Samples for plan-environment.yaml
=================================

The ``plan-environment.yaml`` file provides the details of the plan to be
deployed by TripleO. Along with the details of the heat environments and
parameters, it is also possible to provide workflow specific parameters to the
TripleO mistral workflows. A new section ``workflow_parameters`` has been
added to provide workflow specific parameters. This provides a clear
separation of heat environment parameters and the workflow only parameters.
These customized plan environment files can be provided as with ``-p`` option
to the ``openstack overcloud deploy`` and ``openstack overcloud plan create``
commands. The sample format to provide the workflow specific parameters::

  workflow_parameters:
    tripleo.derive_params.v1.derive_parameters:
      # DPDK Parameters
      num_phy_cores_per_numa_node_for_pmd: 2


All the parameters specified under the workflow name will be passed as
``user_input`` to the workflow, while invoking from the tripleoclient.
