#!/bin/bash
set -eux
set -o pipefail

write_entries() {
    local file="$1"
    local entries="$2"

    # Don't do anything if the file isn't there
    if [ ! -f "$file" ]; then
        return
    fi

    if grep -q "^# HEAT_HOSTS_START" "$file"; then
        temp=$(mktemp)
        (
        sed '/^# HEAT_HOSTS_START/,$d' "$file"
        echo -ne "\n# HEAT_HOSTS_START - Do not edit manually within this section!\n"
        echo "$entries"
        echo -ne "# HEAT_HOSTS_END\n\n"
        sed '1,/^# HEAT_HOSTS_END/d' "$file"
        ) > "$temp"
        echo "INFO: Updating hosts file $file, check below for changes"
        diff "$file" "$temp" || true
        cat "$temp" > "$file"
    else
        # NOTE(aschultz): we purge any entries in the hosts file that match
        # the existing short hostname on initial installation only. This
        # prevents existing data from coming through and causing deployment
        # issues when services (I'm looking at you rabbitmq) start up.
        sed -i "/$(hostname -s)/d" "$file"
        echo -ne "\n# HEAT_HOSTS_START - Do not edit manually within this section!\n" >> "$file"
        echo "$entries" >> "$file"
        echo -ne "# HEAT_HOSTS_END\n\n" >> "$file"
    fi

}

hosts="WRITE_HOSTS"
if [ ! -z "$hosts" ]; then
    for tmpl in /etc/cloud/templates/hosts.*.tmpl ; do
        write_entries "$tmpl" "$hosts"
    done
    write_entries "/etc/hosts" "$hosts"
else
    echo "No hosts in Heat, nothing written."
fi
