#!/bin/bash

if [[ -z "${CONTAINERNET_TOPOFILE}" ]]; then
  topo_file="/app/custom_topo.py"
else
  topo_file="${CONTAINERNET_TOPOFILE}"
fi

# exec to properly propagate SIGINT|SIGTERM with supervisord
exec python $topo_file
