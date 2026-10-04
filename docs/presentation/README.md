# Polish and English product presentation

[Polish](laya-pl.md) is the primary deliverable. [English](laya-en.md) maintains
the same ten-slide story, including cover and closing. Both use the existing
cream/forest/orange [Marp theme](laya.css), editable diagrams and evidence tables.
The [exact supplied spec](../../.ai/specs/2026-10-04-final-hr-presentation.md)
governs the scope. Public delivery is tracked in
[issue 48](https://github.com/bsisduck/laya-sec-agent/issues/48).

**Draft:** HR acceptance and final integrated measurements are pending root.
The first push and draft PR remain held. Accepted department evidence is
`e6ac3564` (reviewed `40eb409`), and accepted issuer evidence is `e015e66c`
(reviewed `cd4c162`). Those results do not establish the final HR release result.
Replace the draft footer and final tested-revision line only from root's final
accepted evidence. No runtime code is changed by this presentation task.

## Render and inspect

Prepare Node 20+, local Chrome/Chromium and Poppler (`pdfinfo`, `pdftoppm`,
`pdftotext`). The existing renderer remains pinned to Marp CLI **4.5.1**.
First renderer preparation can use the network. Cache it before offline rendering.
Marp/Node is presentation tooling, separate from the product runtime.

```sh
sh docs/presentation/render.sh
python3 docs/presentation/check.py
```

The checker needs the existing Playwright Python package and local Google Chrome.
If using the repository QA environment, run it with the same test-only dependency:

```sh
uv run --locked --extra mcp --with playwright python docs/presentation/check.py
```

Generated deliverables, all twenty full-size PNG pages, narrow-view screenshots
and `offline-check.json` remain ignored under `reports/generated/presentation`:

- `laya-pl.pdf` and `laya-pl.html`
- `laya-en.pdf` and `laya-en.html`

Both PDFs must contain ten pages. Each HTML must contain ten slides and open
directly from disk with no login, asset server, API key or network dependency.
Marp embeds the theme and navigation script. Local system fonts supply Polish
glyphs without a web-font download. Use left/right arrow keys to navigate.
Repository/regulatory links are optional references, never rendering dependencies.
HTML speaker notes contain official sources and scoped code/evidence references.
Slide 8 also links official sources in the visible slide. Team facts remain explicitly unfilled in the
[submission template](../submission-template.md), with no invented public demo URL.

The checker opens fresh offline browser contexts at 1280×720 and 390×844,
navigates every slide in both languages, checks document-only requests, language,
absence of a login input, source text bounds and PDF page/text extraction.
It does not replace visual inspection: inspect **every rendered page**, Polish
glyphs, table/diagram labels, arrows, overlap and narrow screenshots.

## Claim review

| Slide | Claim source | Evidence boundary |
|---|---|---|
| 1–2 | HR author `docs/hr-workflow.md`, synthetic `hr-candidate-001` | Draft until root accepts HR; no hiring ranking/decision or SMTP |
| 3 | [Architecture](../architecture.md), model/tool/telemetry contracts | Local services solid; enterprise targets dashed |
| 4 | [Delegated authority](../delegated-authority.md), accepted issuer `docs/issuer-exchange.md`, HR contract | Human/accounting/approver separate; generated-key issuer evidence, no corporate SSO certification |
| 5 | [Catalog](../tool-catalog.md), exact approval contracts | Local 25/75 heuristic, no legal/semantic probability; outbox only |
| 6 | [Threat evidence](../threat-model.md) | Authored L0–L5 and exact seven layers; live levels unknown |
| 7 | [Department usage](../department-usage.md), [telemetry](../telemetry-delivery.md) | Known/unknown attempts, simulated tariffs, local collector, unavailable department export |
| 8 | [Standards evidence](../standards-evidence.md), official notes | Purpose-specific AI Act, technical support without compliance verdict |
| 9 | [Release evidence](../release-evidence.md), frozen semantic v1/v2 | Four test types; no summed overlapping totals or invented final measurements |
| 10 | [Local app](../local-app.md), [local console](../local-console.md), public repo | Prepared assets for offline product restart; no-login console still protects agent APIs |

After root supplies the final merged base: rebase unpublished commits, reconcile
all provisional references and actual measurements, update product delivery docs,
then run the required `make validate` with the prepared pinned Hermes source.
Render again, pass the checker and inspect all twenty final pages. Record the
tested base, source review commit, artifact hashes and independent root review in
the release evidence. Publish one scoped **draft** PR and require root review and
green CI. The author does not merge.

Frozen v1 poor results/failed CoreML warm run and v2 false positives/missed attacks
remain intact. [Actual installed HR standard-v2 observation](../hr-release-observation.md)
is an ordinary-record false positive: executed reads, withheld outputs and no
provider attempts. It must remain alongside fixture control success. Static
artifact checks prove presentation behavior, never gateway
enforcement or real-model accuracy. Both supplied challenge documents permit
English or Polish and a maximum ten-slide PDF. Submit one language version with
user-owned team/organizer facts after the user's separate submission action.
