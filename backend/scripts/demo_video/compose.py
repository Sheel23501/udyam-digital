"""Turn the raw screen recording into the submission video: caption panel on the left, the app on the right,
a title card first and a closing card with the links last. Also writes a matching .srt subtitle file.

Usage:  python scripts/demo_video/compose.py --src <dir with app.webm + marks.json> --out <video.mp4> [--max 178]
Needs Pillow and imageio-ffmpeg (bundled ffmpeg with libx264)."""
import argparse
import json
import subprocess
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

FF = imageio_ffmpeg.get_ffmpeg_exe()
CW, CH = 1280, 720
APP_X = 660                                              # app video (600 x 720) sits at the right
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
RED, BG, PANEL, WHITE, GREY, DIM = "#E40046", "#0F1014", "#16171C", "#FFFFFF", "#D1D5DB", "#6B7280"
LIVE_URL = "udyam-digital-isyfatadrab4adtbqddzwp.streamlit.app"
REPO_URL = "github.com/Sheel23501/udyam-digital"
STEPS = ["Language", "Mobile number", "Advisor chat", "Recommendation", "Live quote", "Consent", "Smart KYC", "Order tracker", "Back office"]

CAPTIONS = {
    "language": (1, "Pick a language", "The owner opens a link from WhatsApp, a QR code or a partner, and picks Hindi or English. No app to install, no salesperson."),
    "otp": (2, "Verify the mobile number", "A fresh random one-time code links the quote and the order to the owner. In demo mode the SMS is shown on screen."),
    "chat": (3, "Describe the business in Hindi", "A sari shop in Delhi: five people, two shops, GST, a card machine that keeps dropping, and cameras wanted. The advisor asks only for what is missing."),
    "card": (4, "One bundle, one monthly price", "A rules engine picks every item from Airtel's catalogue and prices it. The AI only explains. The card also says what was left out and why."),
    "quote": (5, "Live quote, now in English", "The owner can switch language at any time. Changing a quantity re-prices instantly, and every change is checked against the rules."),
    "quote_rule": (5, "Rules cannot be broken", "Switching off the internet line breaks a rule, because other items depend on it, so the order is blocked. Switched back on, it can continue."),
    "quote_off": (5, "Switch items on and off", "The price updates instantly, and every change is re-checked against the same rules."),
    "quote_locked": (5, "Locked add-ons say why", "Anything this business is not eligible for stays locked, with the reason next to it."),
    "consent": (6, "Consent before any document", "Each purpose is listed in plain words, as the DPDP Act asks. The API refuses documents until the owner agrees."),
    "kyc_fail": (7, "Smart KYC catches a tampered GSTIN", "Four documents, 12 checks against the GST and Udyam registries in seconds. Sample K06 has a tampered digit: rejected, with the reason shown."),
    "kyc_pass": (7, "A genuine owner passes", "Sample K03 is verified in seconds. GSTIN and names stay masked on screen, in the API and in the audit log."),
    "tracker": (8, "Order placed, no status calls", "Every stage has an expected date, and the owner is notified at each step, so nobody has to call and ask."),
    "done": (8, "Done, with a referral link", "The owner can invite another business. Both get one month of a SIM plan free when it activates."),
    "backoffice": (9, "Back office for staff", "Leads the journey could not close land in a scored queue with a suggested next action, so the field team calls the high-value ones first. PIN protected."),
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def panel(key: str, path: Path) -> None:
    step, title, body = CAPTIONS[key]
    im = Image.new("RGB", (CW, CH), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, APP_X - 1, CH], fill=PANEL)
    d.rectangle([APP_X - 4, 0, APP_X - 1, CH], fill=RED)
    x = 56
    d.rounded_rectangle([x, 44, x + 118, 76], radius=16, fill=RED)
    d.text((x + 59, 60), "LIVE DEMO", font=font(BOLD, 15), fill=WHITE, anchor="mm")
    d.text((x + 134, 60), "Udyam Digital · Airtel SYNC Track A", font=font(FONT, 17), fill=DIM, anchor="lm")
    d.text((x, 150), f"STEP {step} OF {len(STEPS)}  ·  {STEPS[step - 1].upper()}", font=font(BOLD, 20), fill=RED)
    y = 188
    tf = font(BOLD, 42)
    for line in wrap(d, title, tf, 540):
        d.text((x, y), line, font=tf, fill=WHITE)
        y += 52
    y += 18
    bf = font(FONT, 26)
    for line in wrap(d, body, bf, 540):
        d.text((x, y), line, font=bf, fill=GREY)
        y += 37
    # progress
    seg = (540 - 8 * 6) / 9
    for i in range(9):
        sx = x + i * (seg + 6)
        d.rounded_rectangle([sx, 628, sx + seg, 634], radius=3, fill=RED if i < step else "#2A2C33")
    d.text((x, 662), LIVE_URL, font=font(FONT, 16), fill=DIM)
    im.save(path)


def card(kind: str, path: Path) -> None:
    im = Image.new("RGB", (CW, CH), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, CH - 8, CW, CH], fill=RED)
    x = 110
    if kind == "intro":
        d.rounded_rectangle([x, 150, x + 300, 186], radius=18, fill=RED)
        d.text((x + 150, 168), "AIRTEL SYNC · TRACK A", font=font(BOLD, 17), fill=WHITE, anchor="mm")
        d.text((x, 220), "Udyam Digital", font=font(BOLD, 84), fill=WHITE)
        y = 330
        for line in wrap(d, "A small business goes live in one sitting: on a phone, in Hindi or English, with no salesperson in the loop.", font(FONT, 32), 1000):
            d.text((x, y), line, font=font(FONT, 32), fill=GREY)
            y += 44
        d.text((x, y + 40), "Sheel Gautam · Vikas Meena  ·  IIIT Delhi", font=font(BOLD, 26), fill=WHITE)
        d.text((x, y + 82), "A walkthrough of the live prototype, step by step", font=font(FONT, 22), fill=DIM)
    else:
        d.text((x, 110), "Built and verified", font=font(BOLD, 56), fill=WHITE)
        stats = [("2,050", "automated tests"), ("30 / 30", "advisor scenarios"), ("12 / 12", "KYC verdicts"), ("16 / 16", "live chats, zero rule breaks")]
        sx = x
        for num, lab in stats:
            d.text((sx, 210), num, font=font(BOLD, 46), fill=RED)
            d.text((sx, 268), lab, font=font(FONT, 20), fill=GREY)
            sx += 270
        for i, (lab, url) in enumerate((("Try it live", LIVE_URL), ("Code", REPO_URL))):
            y = 360 + i * 92
            d.rounded_rectangle([x, y, x + 1060, y + 70], radius=35, fill=RED if i == 0 else PANEL, outline=None if i == 0 else WHITE, width=2)
            d.text((x + 34, y + 35), lab.upper(), font=font(BOLD, 18), fill=WHITE, anchor="lm")
            d.text((x + 210, y + 35), url, font=font(BOLD, 27), fill=WHITE, anchor="lm")
        d.text((x, 580), "Sheel Gautam · Vikas Meena  ·  IIIT Delhi", font=font(BOLD, 24), fill=WHITE)
    im.save(path)


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-3000:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", type=float, default=178.0, help="longest allowed total length in seconds")
    ap.add_argument("--intro", type=float, default=5.0)
    ap.add_argument("--outro", type=float, default=7.0)
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    work = src / "compose"
    work.mkdir(exist_ok=True)
    marks = json.loads((src / "marks.json").read_text())
    end = next(m["t"] for m in marks if m["key"] == "end")
    steps = [m for m in marks if m["key"] in CAPTIONS]
    budget = a.max - a.intro - a.outro
    speed = max(1.0, end / budget)                      # speed the app part up only if it would run over
    print(f"recording {end:.1f}s -> {end / speed:.1f}s at x{speed:.2f}")

    # caption track: one still per step, held until the next step starts (the first one also covers page load)
    lines, srt, n = [], [], 0
    for i, m in enumerate(steps):
        t0 = 0.0 if i == 0 else m["t"]
        t1 = steps[i + 1]["t"] if i + 1 < len(steps) else end
        png = work / f"cap_{i:02}_{m['key']}.png"
        panel(m["key"], png)
        dur = (t1 - t0) / speed
        lines += [f"file '{png}'", f"duration {dur:.3f}"]
        step, title, body = CAPTIONS[m["key"]]
        n += 1
        srt.append(f"{n}\n{srt_time(a.intro + t0 / speed)} --> {srt_time(a.intro + t1 / speed)}\nStep {step}: {title}. {body}\n")
    lines.append(f"file '{png}'")
    (work / "captions.txt").write_text("\n".join(lines) + "\n")

    card("intro", work / "intro.png")
    card("outro", work / "outro.png")
    x264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30"]
    run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(work / "captions.txt"), "-i", str(src / "app.webm"),
         "-filter_complex", f"[0:v]fps=30,format=yuv420p[bg];[1:v]setpts=PTS/{speed:.4f},fps=30[app];[bg][app]overlay={APP_X}:0:shortest=1[v]",
         "-map", "[v]", *x264, str(work / "main.mp4")])
    for kind, dur in (("intro", a.intro), ("outro", a.outro)):
        run([FF, "-y", "-loop", "1", "-t", f"{dur}", "-i", str(work / f"{kind}.png"),
             "-vf", f"fps=30,format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st={dur - 0.6}:d=0.6", *x264, str(work / f"{kind}.mp4")])
    out.parent.mkdir(parents=True, exist_ok=True)
    run([FF, "-y", "-i", str(work / "intro.mp4"), "-i", str(work / "main.mp4"), "-i", str(work / "outro.mp4"),
         "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
         *x264, "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", str(out)])
    out.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"wrote {out} and {out.with_suffix('.srt')}")


if __name__ == "__main__":
    main()
