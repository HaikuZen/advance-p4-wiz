#!/bin/bash
# idf61.sh - run a command in a clean ESP-IDF v6.1 environment, from the current directory.
# THIS MACHINE ONLY: the paths are where EIM installed IDF 6.1 here (/root/.espressif).
exec env -i HOME="$HOME" TERM="${TERM:-dumb}" PATH=/usr/local/bin:/usr/bin:/bin \
  IDF_TOOLS_PATH=/root/.espressif/tools IDF_PATH=/root/.espressif/v6.1/esp-idf \
  IDF_PYTHON_ENV_PATH=/root/.espressif/tools/python/v6.1/venv PWD="$PWD" \
  bash -c 'cd "$PWD" && . "$IDF_PATH/export.sh" > /dev/null 2>&1 && "$@"' _ "$@"
