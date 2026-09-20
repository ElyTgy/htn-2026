#!/bin/sh
set -eu
FIRMWARE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python3}
CXX=${CXX:-c++}
mkdir -p "$FIRMWARE_ROOT/build"
"$CXX" -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -I "$FIRMWARE_ROOT/tests/stubs" "$FIRMWARE_ROOT/tests/firmware_test.cpp" -o "$FIRMWARE_ROOT/build/firmware_test"
"$FIRMWARE_ROOT/build/firmware_test" "$FIRMWARE_ROOT/build/native-frames.bin"
"$PYTHON" -m unittest discover -s "$FIRMWARE_ROOT/tests" -p 'test_*.py'
node --check "$FIRMWARE_ROOT/dashboard/app.mjs"
node "$FIRMWARE_ROOT/tests/simulation_test.mjs"
echo "Host tests passed. Compile for Uno separately; host timing does not measure AVR timing or motor behavior."
