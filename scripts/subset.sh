#!/bin/bash
mkdir -p outputs/web
for f in outputs/ttf/*.ttf; do
  name=$(basename "$f" .ttf)
  pyftsubset "$f" \
    --unicodes=U+10C00-10C4F,U+0020,U+205A \
    --layout-features='*' \
    --flavor=woff2 \
    --output-file="outputs/web/${name}.woff2"
done
