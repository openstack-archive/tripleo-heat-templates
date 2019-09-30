---
fixes:
  - |
    Sets the bridge-nf-call-* values to 1, overriding any distro defaults that
    may not be applied due to br_netfilter not being loaded. These values must
    be 1 for security groups to work.
