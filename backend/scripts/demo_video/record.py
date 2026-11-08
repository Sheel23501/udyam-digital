"""Drive the running app like an owner would and record the screen (Playwright + the system Chrome).

Usage:  streamlit app running at --url, then
        python scripts/demo_video/record.py --out <dir>
Writes <dir>/app.webm and <dir>/marks.json (seconds from the start of the recording at which each step begins).
compose.py then adds the caption panel, the title card and the closing card."""
import argparse
import json
import os
import shutil
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

W, H = 600, 720                                         # phone-shaped viewport, recorded 1:1

CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('__demo_cursor')) return;
    const c = document.createElement('div');
    c.id = '__demo_cursor';
    Object.assign(c.style, {position: 'fixed', left: '-40px', top: '-40px', width: '22px', height: '22px', borderRadius: '50%',
      background: 'rgba(228,0,70,0.35)', border: '2px solid #E40046', zIndex: 2147483647, pointerEvents: 'none',
      transform: 'translate(-50%,-50%)', transition: 'width .12s, height .12s, background .12s'});
    document.body.appendChild(c);
    document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', () => { c.style.width = '34px'; c.style.height = '34px'; c.style.background = 'rgba(228,0,70,0.6)'; }, true);
    document.addEventListener('mouseup', () => { c.style.width = '22px'; c.style.height = '22px'; c.style.background = 'rgba(228,0,70,0.35)'; }, true);
  };
  if (document.body) add(); else document.addEventListener('DOMContentLoaded', add);
})();
"""


class Demo:
    def __init__(self, page: Page):
        self.page = page
        self.t0 = time.monotonic()
        self.marks: list[dict] = []
        self.mouse = (W / 2, H / 2)

    def mark(self, key: str) -> None:
        self.marks.append({"key": key, "t": round(time.monotonic() - self.t0, 2)})
        print(f"{self.marks[-1]['t']:7.2f}s  {key}", flush=True)

    def hold(self, s: float) -> None:
        self.page.wait_for_timeout(int(s * 1000))

    def glide(self, x: float, y: float, steps: int = 18) -> None:
        self.page.mouse.move(x, y, steps=steps)
        self.mouse = (x, y)

    def click(self, sel: str, timeout: float = 30) -> None:
        loc = self.page.locator(sel).first
        loc.wait_for(state="visible", timeout=timeout * 1000)
        loc.scroll_into_view_if_needed()
        self.hold(0.25)
        b = loc.bounding_box()
        self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        self.hold(0.2)
        loc.click()

    def type(self, sel: str, text: str, delay: int = 60) -> None:
        self.click(sel)
        self.page.locator(sel).first.press_sequentially(text, delay=delay)

    def scroll(self, total: int, step: int = 90, pause: float = 0.12) -> None:
        self.page.mouse.move(W / 2, H / 2)
        n = max(1, abs(total) // step)
        for _ in range(n):
            self.page.mouse.wheel(0, step if total > 0 else -step)
            self.hold(pause)

    def idle(self, timeout: float = 90) -> None:
        """Wait until Streamlit has finished running the script (no spinner, no running status)."""
        self.page.wait_for_timeout(400)
        self.page.wait_for_function(
            "() => !document.querySelector('[data-testid=stSpinner]') && "
            "!document.querySelector('[data-testid=stStatusWidget] [data-testid=stStatusWidgetRunningIcon]')",
            timeout=timeout * 1000)
        self.page.wait_for_timeout(500)

    def visible(self, sel: str) -> bool:
        loc = self.page.locator(sel)
        return loc.count() > 0 and loc.first.is_visible()


def run(url: str, out: Path, pin: str, headless: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=headless)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, locale="en-IN",
                                  record_video_dir=str(raw), record_video_size={"width": W, "height": H})
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        d = Demo(page)
        try:
            journey(d, url, pin)
        except Exception:
            page.screenshot(path=str(out / "failure.png"), full_page=True)
            raise
        finally:
            d.mark("end")
            video = page.video
            ctx.close()
            browser.close()
            src = Path(video.path())
            shutil.move(str(src), out / "app.webm")
            shutil.rmtree(raw, ignore_errors=True)
            (out / "marks.json").write_text(json.dumps(d.marks, indent=1), encoding="utf-8")


def journey(d: Demo, url: str, pin: str) -> None:
    pg = d.page
    pg.goto(url, wait_until="networkidle")
    pg.locator(".st-key-lang_hi button").wait_for(timeout=60000)
    d.idle()

    # 1. language
    d.mark("language")
    d.hold(2.5)
    d.click(".st-key-lang_hi button")
    d.idle()

    # 2. mobile number + one-time code (demo SMS shown on screen)
    d.mark("otp")
    d.type(".st-key-phone input", "9876543210", delay=90)
    d.hold(0.5)
    d.click(".st-key-send_otp button")
    pg.locator(".sms b").wait_for(timeout=30000)
    d.idle()
    code = pg.locator(".sms b").inner_text().strip()
    d.hold(2.5)
    d.type(".st-key-otp_code input", code, delay=160)
    d.hold(0.6)
    d.click(".st-key-verify_otp button")
    d.idle()

    # 3. advisor chat in Hindi: tap the first example, answer follow-ups until the card appears
    d.mark("chat")
    d.hold(2.0)
    d.click(".st-key-example_1 button")
    follow_ups = ["अभी हम महीने में लगभग 6,000 रुपये टेलीकॉम पर खर्च करते हैं।",
                  "बस इतना ही। अब कीमत बता दीजिए।",
                  "हाँ, ठीक है।"]
    for turn in range(len(follow_ups) + 1):
        d.idle(timeout=120)
        if d.visible(".st-key-to_quote button"):
            break
        d.hold(3.0)                                                    # let the viewer read the question
        if turn < len(follow_ups):
            d.type(".st-key-chat_box textarea", follow_ups[turn], delay=45)
            pg.keyboard.press("Enter")

    # 4. the recommendation card
    d.mark("card")
    d.hold(1.0)
    d.scroll(900, step=60, pause=0.18)
    d.hold(2.0)
    d.scroll(900, step=60, pause=0.18)
    d.hold(2.5)
    d.click(".st-key-to_quote button")
    d.idle()

    # 5. quote: switch to English, change a quantity, break a rule and fix it, show locked add-ons
    d.mark("quote")
    d.click(".st-key-lang_radio label:has-text('English')")
    d.idle()
    d.hold(2.0)
    if d.visible("[class*='st-key-qty_'] button[data-testid='stNumberInputStepUp']"):
        d.click("[class*='st-key-qty_'] button[data-testid='stNumberInputStepUp']")
        d.idle()
        d.hold(1.0)
        d.page.locator("[data-testid='stMetric']").first.scroll_into_view_if_needed()
        d.hold(2.5)
    first_toggle = "[class*='st-key-tg_'] label"
    d.click(first_toggle)
    d.idle()
    broke = d.visible("text=This combination breaks a rule")
    d.mark("quote_rule" if broke else "quote_off")
    if broke:
        pg.locator("text=This combination breaks a rule").first.scroll_into_view_if_needed()
    else:
        d.page.locator("[data-testid='stMetric']").first.scroll_into_view_if_needed()
    d.hold(4.0)
    d.click(first_toggle)
    d.idle()
    d.hold(1.0)
    d.mark("quote_locked")
    d.click("[data-testid='stExpander'] summary:has-text('Add more')")
    d.idle()
    d.hold(1.0)
    d.scroll(400, step=60, pause=0.15)
    d.hold(3.5)
    d.click(".st-key-to_consent button")
    d.idle()

    # 6. DPDP consent
    d.mark("consent")
    d.hold(2.5)
    boxes = pg.locator("[data-testid='stCheckbox'] label")
    for i in range(boxes.count()):
        lab = boxes.nth(i)
        lab.scroll_into_view_if_needed()
        b = lab.bounding_box()
        d.glide(b["x"] + 14, b["y"] + b["height"] / 2, steps=10)
        lab.click(position={"x": 10, "y": b["height"] / 2})
        d.idle()
        d.hold(0.6)
    d.hold(1.0)
    d.click(".st-key-agree button")
    d.idle()

    # 7. Smart KYC: a tampered GSTIN fails with the reason, a genuine applicant passes
    d.mark("kyc_fail")
    d.click(".st-key-kyc_mode_radio label:has-text('Use a sample applicant')")
    d.idle()
    for applicant, key in (("K06", None), ("K03", "kyc_pass")):
        if key:
            d.mark(key)
        d.click("[data-testid='stSelectbox']")
        d.hold(0.8)
        pg.keyboard.type(applicant, delay=120)
        d.hold(0.5)
        pg.keyboard.press("Enter")
        d.idle()
        d.hold(0.5)
        d.click(".st-key-verify_sample button")
        pg.locator(".pill").first.wait_for(timeout=120000)
        d.idle()
        d.hold(1.5)
        d.scroll(500, step=60, pause=0.2)
        d.hold(3.5)
        if applicant == "K06":
            d.click(".st-key-kyc_again button")
            d.idle()
    d.click(".st-key-place_order button")
    d.idle()

    # 8. tracker and done
    d.mark("tracker")
    d.hold(3.0)
    for _ in range(2):
        d.click(".st-key-advance button")
        d.idle()
        d.hold(2.2)
    d.scroll(-600)
    d.hold(2.0)
    d.click(".st-key-finish button")
    d.idle()
    d.mark("done")
    d.hold(3.5)

    # 9. back office for staff
    pg.goto(url.rstrip("/") + "/backoffice", wait_until="networkidle")
    d.mark("backoffice")
    pg.locator(".st-key-staff_pin input").wait_for(timeout=60000)
    d.idle()
    d.type(".st-key-staff_pin input", pin, delay=110)
    d.click(".st-key-staff_enter button")
    pg.locator("text=Unclosed leads").wait_for(timeout=60000)
    d.idle()
    d.hold(2.5)
    d.scroll(500, step=60, pause=0.2)
    d.hold(5.0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8599")
    ap.add_argument("--out", required=True)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    run(args.url, Path(args.out), os.environ.get("STAFF_PIN", ""), headless=not args.headed)
