#!/bin/bash

TMP_DATA=$(mktemp -d)
function cleanup {
  rm -Rf "$TMP_DATA"
}
trap cleanup EXIT

if [ -n "$artifact_urls" ]; then
  for URL in $(echo $artifact_urls | sed -e "s| |\n|g" | sort -u); do
    curl -o $TMP_DATA/file_data "$artifact_urls"
    if file -b $TMP_DATA/file_data | grep RPM &>/dev/null; then
      yum install -y $TMP_DATA/file_data
    elif file -b $TMP_DATA/file_data | grep 'gzip compressed data' &>/dev/null; then
      pushd /
      tar xvzf $TMP_DATA/file_data
      popd
    else
      echo "ERROR: Unsupported file format."
      exit 1
    fi
    rm $TMP_DATA/file_data
  done
else
  echo "No artifact_urls was set. Skipping..."
fi
