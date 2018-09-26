Sample Environment Generator
----------------------------

This is a tool to automate the generation of our sample environment
files.  It takes a yaml file as input, and based on the environments
defined in that file generates a number of sample environment files
from the parameters in the Heat templates.

Usage
=====

The simplest case is when an existing sample environment needs to be
updated to reflect changes in the templates.  Use the tox ``genconfig``
target to do this::

    tox -e genconfig

.. note:: The tool should be run from the root directory of the
          ``tripleo-heat-templates`` project.

If a new sample environment is needed, it should be added to the
appropriate file in the ``sample-env-generator/`` directory.  The existing
entries in the files can be used as examples, and a more detailed
explanation of the different available keys is below:

Top-level:

- **environments**: This is the top-level key in the file.  All other keys
  below should appear in a list of dictionaries that define environments.

Environment-specific:

- **name**: the output file will be this name + .yaml, in the
  ``environments`` directory.
- **title**: a human-readable title for the environment.
- **description**: A description of the environment.  Will be included
  as a comment at the top of the sample file.
- **files**: The Heat templates containing the parameter definitions
  for the environment.  Should be specified as a path relative to the
  root of the ``tripleo-heat-templates`` project.  For example:
  ``puppet/extraconfig/tls/ca-inject.yaml:``.  Each filename
  should be a YAML dictionary that contains a ``parameters`` entry.
- **parameters**: There should be one ``parameters`` entry per file in the
  ``files`` section (see the example configuration below).
  This can be either a list of parameters related to
  the environment, which is necessary for templates like
  overcloud.yaml, or the string 'all', which indicates that all
  parameters from the file should be included.
- **static**: Can be used to specify that certain parameters must
  not be changed.  Examples would be the EnableSomething params
  in the templates.  When writing a sample config for Something,
  ``EnableSomething: True`` would be a static param, since it
  would be nonsense to include the environment with it set to any other
  value.
- **sample_values**: Sometimes it is useful to include a sample value
  for a parameter that is not the parameter's actual default.
  An example of this is the SSLCertificate param in the enable-tls
  environment file.
- **resource_registry**: Many environments also need to pass
  resource_registry entries when they are used.  This can be used
  to specify that in the configuration file.
- **children**: For environments that share a lot of common values but may
  need minor variations for different use cases, sample environment entries
  can be nested.  ``children`` takes a list of environments with the same
  structure as the top-level ``environments`` key.  The main difference is
  that all keys are optional, and any that are omitted will be inherited from
  the parent environment definition.

Some behavioral notes:

- Parameters without default values will be marked as mandatory to indicate
  that the user must set a value for them.
- It is no longer recommended to set parameters using the ``parameters``
  section.  Instead, all parameters should be set as ``parameter_defaults``
  which will work regardless of whether the parameter is top-level or nested.
  Therefore, the tool will always set parameters in the ``parameter_defaults``
  section.
- Parameters whose name begins with the _ character are treated as private.
  This indicates that the parameter value will be passed in from another
  template and does not need to be exposed directly to the user.

If adding a new environment, don't forget to add the new file to the
git repository so it will be included with the review.

Example
=======

Given a Heat template named ``example.yaml`` that looks like::

    parameters:
      EnableExample:
        default: False
        description: Enable the example feature
        type: boolean
      ParamOne:
        default: one
        description: First example param
        type: string
      ParamTwo:
        description: Second example param
        type: number
      _PrivateParam:
        default: does not matter
        description: Will not show up
        type: string

And an environment generator entry that looks like::

    environments:
      -
        name: example
        title: Example Environment
        description: |
          An example environment demonstrating how to use the sample
          environment generator.  This text will be included at the top
          of the generated file as a comment.
        files:
          example.yaml:
            parameters: all
        sample_values:
          EnableExample: True
        static:
          - EnableExample
        resource_registry:
          OS::TripleO::ExampleData: ../extraconfig/example.yaml

The generated environment file would look like::

    # *******************************************************************
    # This file was created automatically by the sample environment
    # generator. Developers should use `tox -e genconfig` to update it.
    # Users are recommended to make changes to a copy of the file instead
    # of the original, if any customizations are needed.
    # *******************************************************************
    # title: Example Environment
    # description: |
    #   An example environment demonstrating how to use the sample
    #   environment generator.  This text will be included at the top
    #   of the generated file as a comment.
    parameter_defaults:
      # First example param
      # Type: string
      ParamOne: one

      # Second example param
      # Mandatory. This parameter must be set by the user.
      # Type: number
      ParamTwo: <None>

      # ******************************************************
      # Static parameters - these are values that must be
      # included in the environment but should not be changed.
      # ******************************************************
      # Enable the example feature
      # Type: boolean
      EnableExample: True

      # *********************
      # End static parameters
      # *********************
    resource_registry:
      OS::TripleO::ExampleData: ../extraconfig/example.yaml
