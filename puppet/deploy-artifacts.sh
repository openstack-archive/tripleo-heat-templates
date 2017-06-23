#!/bin/bash

TMP_DATA=$(mktemp -d)
function cleanup {
  rm -Rf "$TMP_DATA"
}
trap cleanup EXIT

if [ -n "$artifact_urls" ]; then
  for URL in $(echo $artifact_urls | sed -e "s| |\n|g" | sort -u); do
    curl --globoff -o $TMP_DATA/file_data "$URL"
    if file -b $TMP_DATA/file_data | grep RPM &>/dev/null; then
      mv $TMP_DATA/file_data $TMP_DATA/file_data.rpm
      yum install -y $TMP_DATA/file_data.rpm
      rm $TMP_DATA/file_data.rpm
    elif file -b $TMP_DATA/file_data | grep 'gzip compressed data' &>/dev/null; then
      pushd /
      tar xvzf $TMP_DATA/file_data
      popd
    else
      echo "ERROR: Unsupported file format: $URL"
      exit 1
    fi
    if [ -f $TMP_DATA/file_data ]; then
      rm $TMP_DATA/file_data
    fi
  done
else
  echo "No artifact_urls was set. Skipping..."
fi
