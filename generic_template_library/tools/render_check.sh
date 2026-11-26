#!/bin/sh
# Convert every DOCX under an examples folder to PDF and page PNGs for visual inspection
# (LibreOffice preview, not Microsoft Word).
# Usage: sh tools/render_check.sh examples/stage4 qa/stage4_render   (from this folder)
# Needs LibreOffice (soffice) and poppler (pdftoppm, pdfinfo); override with SOFFICE=/path/to/soffice POPPLER_BIN=/path/to/bin.
SOFFICE=${SOFFICE:-soffice}
POPPLER_BIN=${POPPLER_BIN:-}
P=${POPPLER_BIN:+$POPPLER_BIN/}
SRC=${1:-examples/stage4}
OUTD=${2:-qa/stage4_render}
rm -rf "$OUTD"; mkdir -p "$OUTD"
for f in "$SRC"/*/*.docx; do
  study=$(basename "$(dirname "$f")")
  cp "$f" "$OUTD/${study}__$(basename "$f")"
done
for f in "$OUTD"/*.docx; do "$SOFFICE" --headless --convert-to pdf --outdir "$OUTD" "$f" >/dev/null 2>&1; rm "$f"; done
for p in "$OUTD"/*.pdf; do "${P}pdftoppm" -r 70 -png "$p" "${p%.pdf}"; echo "$(basename "$p"): $("${P}pdfinfo" "$p" | awk '/Pages/{print $2}') page(s)"; done
