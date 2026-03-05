#!/bin/bash
set -e

chown -R agent0:agent0 /data
gosu agent0 git config --global --add safe.directory /app
gosu agent0 git config --global --add safe.directory '/data/workspaces/*'
exec gosu agent0 "$@"
