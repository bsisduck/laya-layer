# Laya Layer — decyzja przed działaniem

Ten Polish slides with editable native text and vector diagrams, plus speaker notes.
This is a new narrative about requests, decisions and evidence. It does not reuse
the supplied deck's statistics, images or story. The original file stays unchanged.

The three product surfaces are Chat, Logs and Workflow. Four scenario histories
are explicitly illustrative; live HR execution and actual audit are separate.
The deck distinguishes read, permitted write with exact approval, and unregistered
or destructive operations denied before dispatch. GDPR Article 20 (portability)
and Article 30 (records of processing) have different purposes; technical audit is
not a full implementation of either. Sources are in speaker notes and
[narracja.md](narracja.md). Model-quality limitations remain in slide 9 narration.

## Build

Node.js 20+; dependencies are pinned in the local lockfile, separate from the app. The image-size transitive parser is overridden to patched
2.0.4; npm audit reports zero known vulnerabilities for the locked build tools.
This deck uses only native text and shapes and does not parse external images.
Run from the project root:

```sh
npm ci --ignore-scripts --prefix docs/presentation/decision-workspace
node docs/presentation/decision-workspace/build.cjs \
  'reports/generated/presentation/Laya Layer — decyzja przed działaniem.pptx'
```

This writes the PPTX and a companion narration Markdown into the chosen directory.
Keep generated files in the ignored reports directory or outside Git. The deck uses
Avenir Next (available on the development Mac); install that font on the rendering
machine or use the PDF for fixed appearance. Shape geometry is 16:9, 13⅓ × 7½ inches.
PptxGenJS 4.0.1's dangling declarations for absent slide masters are removed without
changing actual package parts or relationships. The exported structure is validated.

PDF conversion example on the development Mac with LibreOffice and Homebrew
fontconfig (adapt these environment paths on another host):

```sh
FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf soffice \
  -env:UserInstallation=file:///tmp/laya-deck-lo \
  --headless --convert-to pdf --outdir reports/generated/presentation \
  'reports/generated/presentation/Laya Layer — decyzja przed działaniem.pptx'
```

## Review evidence

All ten slides were rendered in LibreOffice 26.8 and visually reviewed. An
independent reviewer requested a clearer slide 2 title and a more precise
"Wywołanie" label for the action gateway; both are applied. The author also fixed
a font-discovery fallback and wrapped slide 9 captions to prevent neighboring
columns touching. Final checks cover ten slides, ten notes, native text,
package relationships, layout/font policy and rendered text bounds. The PDF embeds
Avenir Next. No native Microsoft PowerPoint verification is claimed.

The local artifact-tool runtime was unavailable, so authoring used the available
`pptx` skill's PptxGenJS workflow and independent OOXML/layout validators.
