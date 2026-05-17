#!/bin/bash

UI_DIR="./src/ui"
PY_DIR="./src/views"

mkdir -p "$PY_DIR"

for ui_file in "$UI_DIR"/*.ui; do
    filename=$(basename "$ui_file" .ui)
    output_file="$PY_DIR/ui_${filename}.py"
    echo "Converting: $ui_file -> $output_file"
    python3 -m PyQt6.uic.pyuic -x "$ui_file" -o "$output_file"
done
echo Done!
