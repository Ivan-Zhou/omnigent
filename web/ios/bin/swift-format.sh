#!/usr/bin/env bash
# Guarded wrapper around `swift format`, invoked by the web-ios-swift-*
# pre-commit hooks. Skips cleanly on machines without a Swift toolchain so
# `pre-commit run --all-files` stays green there. Xcode and the ubuntu-latest
# CI image both ship one, so the hooks enforce in both places.
set -euo pipefail

if ! command -v swift >/dev/null 2>&1; then
  exit 0
fi

# swift-format 6+ exposes formatting as the `swift format` subcommand. Older
# toolchains may not; treat its absence the same as a missing toolchain.
if ! swift format --version >/dev/null 2>&1; then
  exit 0
fi

exec swift "$@"
