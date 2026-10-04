#!/bin/sh
# Run from any directory. Generated deliverables remain ignored and local.
set -eu
cd "$(dirname "$0")/../.."
presentation_output=reports/generated/presentation
mkdir -p "$presentation_output"
for presentation_lang in pl en; do
  presentation_source="docs/presentation/laya-${presentation_lang}.md"
  npx --yes --package @marp-team/marp-cli@4.5.1 marp "$presentation_source" \
    --theme docs/presentation/laya.css --html --pdf --allow-local-files \
    --output "$presentation_output/laya-${presentation_lang}.pdf"
  npx --yes --package @marp-team/marp-cli@4.5.1 marp "$presentation_source" \
    --theme docs/presentation/laya.css --html \
    --output "$presentation_output/laya-${presentation_lang}.html"
  pdfinfo "$presentation_output/laya-${presentation_lang}.pdf"
  pdftoppm -scale-to 1280 -png "$presentation_output/laya-${presentation_lang}.pdf" \
    "$presentation_output/laya-${presentation_lang}"
done
