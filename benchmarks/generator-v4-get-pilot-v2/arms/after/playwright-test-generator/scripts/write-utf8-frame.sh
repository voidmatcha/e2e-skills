#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0

# Emit exactly one length-prefixed UTF-8 frame. The payload is accepted only
# on stdin so target-controlled URL text never enters an argument vector.
set -f
IFS=' '
export LC_ALL=C

if (( $# != 0 )); then
  printf '%s\n' 'write-utf8-frame: payload belongs on stdin' >&2
  exit 2
fi

payload=
if IFS= read -r -d '' payload; then
  printf '%s\n' 'write-utf8-frame: NUL bytes are not allowed' >&2
  exit 2
fi

printf '%08x\n%s' "${#payload}" "$payload"
