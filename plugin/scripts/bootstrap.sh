#!/usr/bin/env sh
# Network/runtime package bootstrap is intentionally disabled for unreleased
# 0.3. A lifecycle hook must never resolve or install mutable packages. A future
# installer may replace this file only after it has an offline wheelhouse,
# require-hashes lock, ownership/mode checks, atomic rollback, and release tests.

PLUGIN_VERSION="0.3.0"
exit 0
