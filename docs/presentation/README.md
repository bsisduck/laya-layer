# English / Polish presentation source

[Laya English](laya-en.md) and [Laya Polish](laya-pl.md) each contain **ten slides**.
[laya.css](laya.css) is the local Marp theme; no external assets, source challenge
PDFs, product keys or invented team facts are embedded. Team/member/URL fields
are deliberate templates. Fill them from user-owned facts before submission.

Render with Node 18+ and pinned Marp CLI (tooling only, outside gateway lock):

```sh
mkdir -p reports/generated/presentation
npx --yes --package @marp-team/marp-cli@4.5.1 marp docs/presentation/laya-en.md \
  --theme docs/presentation/laya.css --html --pdf --allow-local-files \
  --output reports/generated/presentation/laya-en.pdf
npx --yes --package @marp-team/marp-cli@4.5.1 marp docs/presentation/laya-pl.md \
  --theme docs/presentation/laya.css --html --pdf --allow-local-files \
  --output reports/generated/presentation/laya-pl.pdf
pdfinfo reports/generated/presentation/laya-en.pdf
pdfinfo reports/generated/presentation/laya-pl.pdf
```

Rendering requires a prepared local Chromium/Chrome. Initial npx preparation can
use the network; an offline judge environment must cache the renderer/browser
beforehand. The product itself has no Marp/Node presentation dependency.
Generated PDFs/previews/reports stay under ignored `reports/generated/`; commit
only Markdown/CSS source. Recheck ten pages, readable EN/PL glyphs, diagram/text
fit and every evidence claim after edits. Refresh release/PR status from
[the evidence ledger](../release-evidence.md) before root's final freeze.

Root-reported QA and actual model latency are attributed and scoped. Semantic
v1's poor results/failed CoreML warm run remain; v2 mistakes remain visible.
This deck does not promise a semantic detector, SMTP, bank deployment, SOC/vendor
certification or submission eligibility. The supplied terms allow English or
Polish and at most ten PDF slides; use one language version for submission.
