"""Check rendered Marp deliverables without accessing a product installation."""

import json
import re
import subprocess
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports/generated/presentation"

TEXT_GEOMETRY = """section => {
  const box = section.getBoundingClientRect();
  const scale = box.width / section.clientWidth;
  const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
  const failures = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.textContent.trim() || node.parentElement.closest('header,footer')) continue;
    const range = document.createRange();
    range.selectNode(node);
    for (const rect of range.getClientRects()) {
      const x = (rect.left - box.left) / scale;
      const y = (rect.top - box.top) / scale;
      const right = (rect.right - box.left) / scale;
      const bottom = (rect.bottom - box.top) / scale;
      if (x < 50 || right > 1230 || y < 44 || bottom > 664) {
        failures.push({text: node.textContent.trim(), x, y, right, bottom});
      }
    }
  }
  return {failures, scrollHeight: section.scrollHeight, height: section.clientHeight};
}"""


def check() -> None:
    results = []
    geometry_failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        try:
            for language in ("pl", "en"):
                pdf = OUTPUT / f"laya-{language}.pdf"
                info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
                assert re.search(r"^Pages:\s+10$", info, re.MULTILINE), info
                pdf_text = subprocess.check_output(["pdftotext", str(pdf), "-"], text=True)
                assert "\ufffd" not in pdf_text, "Invalid PDF text glyph"
                html = OUTPUT / f"laya-{language}.html"
                for viewport in ({"width": 1280, "height": 720}, {"width": 390, "height": 844}):
                    context = browser.new_context(viewport=viewport, offline=True)
                    requests = []
                    errors = []
                    page = context.new_page()
                    page.on(
                        "request", lambda request, collected=requests: collected.append(request.url)
                    )
                    page.on(
                        "pageerror", lambda error, collected=errors: collected.append(str(error))
                    )
                    try:
                        page.goto(html.as_uri(), wait_until="load")
                        expect(page.locator("section")).to_have_count(10)
                        expect(page.locator('input[type="password"]')).to_have_count(0)
                        assert not page.evaluate(
                            "Array.from(document.querySelectorAll('[src],link[href]')).some("
                            "e=>/^(https?:)?\\/\\//.test(e.getAttribute('src')||e.getAttribute('href')))"
                        ), "External asset reference"
                        assert page.locator("section").first.get_attribute("lang") == language
                        for slide in range(1, 11):
                            if slide > 1:
                                page.keyboard.press("ArrowRight")
                            active = page.locator("svg.bespoke-marp-active section")
                            expect(active).to_have_attribute("id", str(slide))
                            page.evaluate(
                                """async () => {
                              await document.fonts.ready;
                              await customElements.whenDefined('marp-pre');
                              for (let frame = 0; frame < 4; frame++)
                                await new Promise(requestAnimationFrame);
                            }"""
                            )
                            geometry = active.evaluate(TEXT_GEOMETRY)
                            if (
                                geometry["failures"]
                                or geometry["scrollHeight"] != geometry["height"]
                            ):
                                geometry_failures.append((language, viewport, slide, geometry))
                            if viewport["width"] == 390 and slide in (2, 3, 9):
                                page.screenshot(path=OUTPUT / f"{language}-narrow-{slide}.png")
                        page.keyboard.press("ArrowLeft")
                        expect(page.locator("svg.bespoke-marp-active section")).to_have_attribute(
                            "id", "9"
                        )
                        assert not errors, errors
                        assert requests == [html.as_uri()], requests
                        results.append(
                            {
                                "language": language,
                                "viewport": viewport,
                                "slides": 10,
                                "keyboard": "pass",
                                "network": "offline; document only",
                                "geometry": "pass",
                                "login": "none",
                            }
                        )
                    finally:
                        context.close()
        finally:
            browser.close()
    assert not geometry_failures, geometry_failures
    (OUTPUT / "offline-check.json").write_text(json.dumps(results, indent=2) + "\n")
    print(
        "PASS: two ten-page PDFs; 40 offline desktop/narrow slide observations; keyboard, glyph text and geometry checks"
    )


if __name__ == "__main__":
    check()
