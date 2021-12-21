#!/usr/bin/env python
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import argparse
import os
import yaml


def parse_opts():
    """Parse all of the conversion options."""

    parser = argparse.ArgumentParser(
        description="Convert a network V1 template to a V2 template."
    )
    parser.add_argument(
        "v1", metavar="<network_data.yaml>", help="Existing V1 Template."
    )

    return parser.parse_args()


def main():
    """Convert a network v1 template to the network v2 format.

    The V1 template will be converted to V2 format. The V1 template will be
    saved as a backup file before writing the V2 net-data format.
    """

    args = parse_opts()
    net_data_file = os.path.abspath(os.path.expanduser(args.v1))
    with open(net_data_file) as f:
        template_data = yaml.safe_load(f)

    new_template_data = list()
    for item in template_data:
        new_item = dict()
        item.pop("enabled", False)  # Drop unused var
        name = new_item["name"] = item.pop("name")
        name_lower = new_item["name_lower"] = item.pop(
            "name_lower", name.lower()
        )
        new_item["vip"] = item.pop("vip", False)
        new_item["mtu"] = item.pop("mtu", 1500)
        new_item["ipv6"] = item.pop("ipv6", False)
        new_item["subnets"] = item.pop("subnets", dict())
        new_item["subnets"]["{}_subnet".format(name_lower)] = item
        new_template_data.append(new_item)

    os.rename(net_data_file, "{}.bak".format(net_data_file))
    try:
        # content is converted to yaml before opening the file.
        # This is done to ensure that we're not breaking any existing files
        # during the conversion process.
        dump_yaml = yaml.safe_dump(
            new_template_data, default_style=False, sort_keys=False
        )
    except Exception as e:
        print("Conversion could not be completed. Error:{}".format(str(e)))
    else:
        with open(net_data_file, "w") as f:
            f.write(dump_yaml)


if __name__ == "__main__":
    main()
