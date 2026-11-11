#!/usr/bin/env python3
"""Open Practice press: one practice activity a day, posted on Open Practice's own accounts, every post with a card.

  python3 scripts/press/press.py            # dry: composes today's item, prints every rail's text, sends nothing
  python3 scripts/press/press.py --live     # posts on every rail that has an account (GitHub secrets OP_*)
  python3 scripts/press/press.py --live --rails bsky,mastodon --force   # one rail, ignoring today's guard

The activity is chosen by date (all 50, in order, then round again), so the press needs no database. The card is
drawn by the shared media engine (scripts/press/mediakit.py, Open Practice brand in brand.json) and pre-rendered to
apps/web/public/brand/press/<id>-<shape>.png by scripts/press/make_cards.py, so every post has a public image URL
and the same bytes for uploads. A rail with no account is reported as waiting, never as a failure.
Today's posts are remembered in OP_PRESS_STATE (the workflow keeps it in the Actions cache), so a re-run never
posts twice. Run daily by .github/workflows/press.yml (about one billable minute a day).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import html as _html
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import mediakit  # noqa: E402
import oauth1  # noqa: E402

import native  # noqa: E402  press v3: one story, written natively per platform (playbook/PRESS-V3.md)

SITE = os.getenv("OP_SITE_URL", "https://open-practice.zlnew.workers.dev").rstrip("/")
UA = "OpenPractice-press/1.0 (+https://open-practice.zlnew.workers.dev)"
PUBLIC = ROOT / "apps" / "web" / "public"
CARDS = PUBLIC / "brand" / "press"
NOSTR_RELAYS = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.primal.net", "wss://nostr.mom", "wss://relay.snort.social"]
RAILS = ["bsky", "mastodon", "nostr", "discord", "facebook", "pinterest", "tumblr", "blogger", "linkedin"]
LABELS = {"bsky": "Bluesky", "mastodon": "Mastodon", "nostr": "Nostr", "discord": "Discord", "facebook": "Facebook page (Buffer)",
          "pinterest": "Pinterest (Buffer)", "tumblr": "Tumblr", "blogger": "Blogger (post by email)", "linkedin": "LinkedIn (Buffer)"}
NEED = {"bsky": ["OP_BSKY_ID", "OP_BSKY_PASS"], "mastodon": ["OP_MASTODON_TOKEN"], "nostr": ["OP_NOSTR_NSEC"],
        "discord": ["OP_DISCORD_WEBHOOK"], "facebook": ["OP_BUFFER_KEY"], "pinterest": ["OP_BUFFER_KEY", "OP_PINBOARD"],
        "tumblr": ["OP_TUMBLR_BLOG", "OP_TUMBLR_CONSUMER_KEY", "OP_TUMBLR_CONSUMER_SECRET", "OP_TUMBLR_TOKEN", "OP_TUMBLR_TOKEN_SECRET"],
        "blogger": ["OP_BLOGGER_EMAIL", "OP_SMTP_USER", "OP_SMTP_PASS"], "linkedin": ["OP_BUFFER_KEY"]}
# weekdays (Mon=0) each rail posts on; the daily rails post every day
DAYS = {"bsky": range(7), "mastodon": range(7), "nostr": range(7), "discord": range(7), "facebook": range(5),
        "pinterest": (0, 2, 4), "tumblr": range(5), "blogger": (1, 3, 5), "linkedin": (0, 2, 4)}
SHAPE_OF = {"bsky": "wide", "discord": "wide", "blogger": "wide", "mastodon": "square", "nostr": "square", "facebook": "square",
            "tumblr": "square", "pinterest": "pin", "linkedin": "wide"}
SRC = {"bsky": "bluesky", "mastodon": "mastodon", "nostr": "nostr", "discord": "discord", "facebook": "facebook",
       "pinterest": "pinterest", "tumblr": "tumblr", "blogger": "blogger", "linkedin": "linkedin"}  # ?src= values packages/growth/api.mjs counts
BASE_TAGS = ["AI", "LearnByDoing", "AIEngineering", "PromptEngineering", "AISkills"]
COLLECTION_TAGS = {"assistants-workflows": "AIAssistants", "prompt-craft": "PromptCraft", "learning-reasoning": "CriticalThinking",
                   "design-decisions": "DesignThinking", "workplace-writing": "AIWriting", "verify-trust": "FactChecking",
                   "vision-editing": "AIImages", "data-structures": "DataSkills", "research-evidence": "Research",
                   "creative-production": "CreativeAI"}
E = _html.escape


def env(k: str, default: str = "") -> str:
    return (os.environ.get(k) or default).strip()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RailError(Exception):
    pass


# ---------------------------------------------------------------- http (patched in tests)
def http(method: str, url: str, *, data=None, headers=None, form=None, raw=None, timeout=30):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    body = None
    if raw is not None:
        body = raw
    elif form is not None:
        body = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            got = r.read()
            return r.status, (json.loads(got) if got[:1] in (b"{", b"[") else got.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        got = e.read()
        e.close()
        try:
            return e.code, json.loads(got)
        except ValueError:
            return e.code, got.decode("utf-8", "replace")[:300]


def ok_or_raise(status, body, what):
    if not (200 <= status < 300):
        msg = (body.get("message") or body.get("error")) if isinstance(body, dict) else str(body)
        raise RailError(f"{what}: HTTP {status} {str(msg)[:160]}")
    return body


def multipart(fields: dict, file_field: str, filename: str, data: bytes, mime: str) -> tuple[bytes, str]:
    b = "----openpractice" + hashlib.sha1(data[:64] + str(time.time()).encode()).hexdigest()[:16]
    out = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    out += f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"


# ---------------------------------------------------------------- the day's item
def activities() -> list[dict]:
    out = []
    for f in sorted((PUBLIC / "activities").glob("*.json")):
        try:
            a = json.loads(f.read_text("utf-8"))
        except ValueError:
            continue
        if a.get("id") and a.get("title") and a.get("goal"):
            out.append(a)
    return sorted(out, key=lambda a: (int(a.get("number") or 999), a["id"]))


def pick(day: str, acts: list[dict] | None = None) -> dict:
    acts = acts if acts is not None else activities()
    if not acts:
        raise SystemExit("no activities found")
    n = (dt.date.fromisoformat(day) - dt.date(2026, 1, 1)).days
    return acts[n % len(acts)]


def fit(text: str, limit: int) -> str:
    """Cut at a sentence, else a word, so it fits `limit` characters."""
    text = re.sub(r"[ \t]+", " ", str(text)).strip()
    if len(text) <= limit:
        return text
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", text[: limit + 1])]
    if ends and ends[-1] >= limit // 2:
        return text[: ends[-1]].strip()
    cut = text[: limit - 1]
    cut = cut[: cut.rfind(" ")] if " " in cut[limit // 2:] else cut
    return cut.rstrip(" ,.;:") + "…"


def card_data(a: dict) -> dict:
    steps = [s.get("title", "") for s in (a.get("steps") or []) if s.get("title")][:5]
    return {"kicker": str(a.get("collectionTitle") or "Activity").upper()[:24], "number": f"{int(a.get('estimatedMinutes') or 30)} min",
            "label": a["title"], "sub": a["goal"], "rows_title": "Build it in steps",
            "rows": [{"chip": str(i + 1), "title": t} for i, t in enumerate(steps)], "seed": a["id"]}


def card_path(a: dict, shape: str) -> Path:
    return CARDS / f"{a['id']}-{shape}.png"


def media(item: dict, shape: str) -> dict:
    """The card: the pre-rendered file (public URL + bytes); if it is missing, drawn now (bytes) with the activity's
    own illustrated cover as the public URL, so no post goes out without an image."""
    a = item["activity"]
    data = card_data(a)
    alt = mediakit.alt_text("stat", data)
    p = card_path(a, shape)
    if p.is_file():
        return {"png": p.read_bytes(), "url": f"{SITE}/brand/press/{p.name}", "alt": alt, "w": mediakit.SHAPES[shape][0], "h": mediakit.SHAPES[shape][1]}
    png = mediakit.render("stat", shape, data)
    social = PUBLIC / "brand" / "social" / f"{a['id']}.jpg"
    return {"png": png, "url": f"{SITE}/brand/social/{a['id']}.jpg" if social.is_file() else f"{SITE}/brand/og-card.png", "alt": alt,
            "w": mediakit.SHAPES[shape][0], "h": mediakit.SHAPES[shape][1]}


def compose(day: str, a: dict | None = None) -> dict:
    a = a or pick(day)
    tags = BASE_TAGS + ([COLLECTION_TAGS[a["collection"]]] if a.get("collection") in COLLECTION_TAGS else [])
    level = str(a.get("level") or "").split("/")[0].strip() or "Beginner"
    return {"id": f"op-{day}-{a['id']}", "day": day, "activity": a, "title": a["title"], "goal": a["goal"], "mins": int(a.get("estimatedMinutes") or 30),
            "level": level, "collection": a.get("collectionTitle") or "", "hashtags": tags,
            "tags": ["ai", "learn by doing", "ai engineering", "prompt engineering", "ai skills", str(a.get("collectionTitle") or "").lower(), "open practice"],
            "page": f"{SITE}/activities/{a['id']}.html"}


def link(item: dict, rail: str) -> str:
    return f"{item['page']}?src={SRC[rail]}"


def steps_line(item: dict, n: int = 3) -> str:
    return "\n".join(f"{i + 1}. {s['title']}" for i, s in enumerate((item["activity"].get("steps") or [])[:n]) if s.get("title"))


KEYPHRASE = {"assistants-workflows": "AI workflow", "prompt-craft": "prompt engineering", "learning-reasoning": "critical thinking with AI",
             "design-decisions": "AI design", "workplace-writing": "AI writing", "verify-trust": "fact-checking AI",
             "vision-editing": "AI image editing", "data-structures": "data skills with AI", "research-evidence": "AI research",
             "creative-production": "creative AI"}
HOOKS = ["Reading about AI will not make you good at it. {mins} minutes of doing will.",
         "Pick one thing to build today. This one takes {mins} minutes.",
         "You learn {kp} the way you learn to cook: by making something, then tasting it.",
         "The fastest way to understand {kp} is to break a small version of it on purpose."]
LI_HOOKS = ["Most of what I know about {kp} came from doing small builds, not from reading threads.",
            "A {mins}-minute exercise teaches more about {kp} than an hour of slides.",
            "If your team is learning {kp}, give them one small build a day, not one big course."]
QUESTIONS = ["What would you build with this at work?", "Which step would trip you up first?", "Would you do this alone or with a colleague?"]


def story(item: dict) -> dict:
    """The day's activity as a press v3 story: what you build, the steps, how long it takes. All from the activity file."""
    if "_story" in item:
        return item["_story"]
    a = item["activity"]
    n = (dt.date.fromisoformat(item["day"]) - dt.date(2026, 1, 1)).days
    kp = KEYPHRASE.get(a.get("collection") or "", "AI skills")
    Kp = kp[:1].upper() + kp[1:]
    fmt = {"mins": item["mins"], "kp": kp}
    steps = [s["title"] for s in (a.get("steps") or []) if s.get("title")][:4]
    checks = [c for c in (a.get("checks") or []) if c]
    st = {"id": item["id"], "url": item["page"], "keyphrase": kp,
          "title": f"{Kp} exercise: {item['title']}", "pin_title": f"{Kp} exercise: {item['title']} ({item['mins']} min, {item['level'].lower()})",
          "blog_title": f"{item['title']}: a {item['mins']}-minute {kp} exercise",
          "hook": HOOKS[n % len(HOOKS)].format(**fmt), "hooks": {"linkedin": LI_HOOKS[n % len(LI_HOOKS)].format(**fmt)},
          "lede": f"Today's practice: {item['title']}. {item['goal']}",
          "summary": f"{item['title']} is a {item['mins']}-minute {item['level'].lower()} {kp} exercise from Open Practice. {item['goal']}",
          "points": [f"Step {i + 1}: {t}" for i, t in enumerate(steps)], "points_title": "Build it, step by step",
          "takeaway": f"You are done when: {checks[0][:1].lower() + checks[0][1:]}" if checks else "Keep what you build: it is your evidence.",
          "question": QUESTIONS[n % len(QUESTIONS)], "hashtags": item["hashtags"],
          "topics": [kp.lower(), "learn by doing", "ai skills", "ai engineering", "prompt engineering", str(item.get("collection") or "").lower(), "ai practice", "open practice"],
          "alt": mediakit.alt_text("stat", card_data(a)), "link_text": f"Open the activity: {item['title']}", "long_html": long_html(item)}
    item["_story"] = st
    return st


def texts(item: dict) -> dict:
    """Per-rail posts, each written natively for its platform (press v3, native.py) and carrying its own tracked link."""
    st = story(item)
    return {r: native.COMPOSE[r]({**st, "url": link(item, r)}) for r in RAILS}


def _post(item: dict, rail: str, post) -> dict:
    return post if isinstance(post, dict) else native.COMPOSE[rail]({**story(item), "url": link(item, rail)})


def long_html(item: dict, img: dict | None = None) -> str:
    """The article for Blogger and Tumblr: the activity itself, in full, with real headings (search reads these)."""
    a = item["activity"]
    url = link(item, "blogger")
    out = []
    if img and img.get("url"):
        out.append(f'<p><a href="{E(url)}"><img src="{E(img["url"])}" alt="{E(img["alt"][:300])}" width="{img["w"]}" height="{img["h"]}" style="max-width:100%;height:auto"></a></p>')
    out.append(f"<p><strong>{E(item['title'])}</strong> is a {item['mins']}-minute guided build from Open Practice, in the {E(item['collection'])} collection. "
               f"Level: {E(str(a.get('level') or item['level']))}. The goal: {E(item['goal'])}</p>")
    if a.get("explanation"):
        out.append(f"<h2>Why this matters</h2>\n<p>{E(a['explanation'])}</p>")
    if a.get("sampleInput"):
        out.append(f"<h2>What you start with</h2>\n<p>{E(fit(a['sampleInput'], 600))}</p>")
    st = [s for s in (a.get("steps") or []) if s.get("title")]
    if st:
        out.append("<h2>Build it, step by step</h2>\n<ol>" + "".join(f"<li><strong>{E(s['title'])}.</strong> {E(s.get('text', ''))}</li>" for s in st) + "</ol>")
    if a.get("checks"):
        out.append("<h2>How to test your result</h2>\n<ul>" + "".join(f"<li>{E(c)}</li>" for c in a["checks"]) + "</ul>")
    if a.get("commonMistakes"):
        out.append("<h2>Mistakes to watch for</h2>\n<ul>" + "".join(f"<li>{E(c)}</li>" for c in a["commonMistakes"]) + "</ul>")
    if a.get("offline"):
        out.append(f"<h2>No key? Do it on paper</h2>\n<p>{E(a['offline'])}</p>")
    if a.get("reflection"):
        out.append(f"<h2>Before you move on</h2>\n<p>{E(a['reflection'])}</p>")
    out.append(f'<p>Open the full activity, with the prompt to adapt, a worked reference and a place to keep your evidence: <a href="{E(url)}">{E(item["title"])}</a>. '
               "Open Practice teaches AI engineering by doing: bring your own key, or follow the guided template without one.</p>")
    out.append("<h2>Frequently asked questions</h2>")
    for q_, a_ in ((f"How long does {item['title']} take?", f"About {item['mins']} minutes, at {str(a.get('level') or item['level']).lower()} level."),
                   ("Do I need an API key?", "No. Bring your own key to run it against a model, or follow the guided template without one."),
                   ("What do I keep at the end?", "What you built, plus the checks you ran on it. Open Practice keeps it as your evidence.")):
        out.append(f"<h3>{E(q_)}</h3>\n<p>{E(a_)}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------- rails
def _span(text: str, part: str) -> tuple[int, int]:
    i = text.rfind(part)
    s = len(text[:i].encode("utf-8"))
    return s, s + len(part.encode("utf-8"))


def bsky_facets(text: str) -> list:
    out = []
    for m in re.finditer(r"https?://\S+", text):
        b0 = len(text[:m.start()].encode())
        out.append({"index": {"byteStart": b0, "byteEnd": b0 + len(m.group(0).encode())}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}]})
    for m in re.finditer(r"(?<!\S)#([A-Za-z][A-Za-z0-9]{1,63})", text):
        t0 = len(text[:m.start()].encode())
        out.append({"index": {"byteStart": t0, "byteEnd": t0 + len(m.group(0).encode())}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})
    return out


def pub_bsky(item, text):
    p = _post(item, "bsky", text)
    s, d = http("POST", "https://bsky.social/xrpc/com.atproto.server.createSession", data={"identifier": env("OP_BSKY_ID"), "password": env("OP_BSKY_PASS")})
    sess = ok_or_raise(s, d, "login")
    auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
    url = link(item, "bsky")
    img = media(item, "wide")
    external = {"uri": url, "title": p["card"]["title"], "description": p["card"]["description"]}
    s2, up = http("POST", "https://bsky.social/xrpc/com.atproto.repo.uploadBlob", raw=img["png"], headers={**auth, "Content-Type": "image/png"})
    external["thumb"] = ok_or_raise(s2, up, "image upload")["blob"]
    rec = {"$type": "app.bsky.feed.post", "text": p["text"], "createdAt": now_iso(), "langs": ["en"], "facets": bsky_facets(p["text"]),
           "embed": {"$type": "app.bsky.embed.external", "external": external}}
    if p.get("tags"):
        rec["tags"] = p["tags"][:8]
    s, d = http("POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=auth, data={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": rec})
    d = ok_or_raise(s, d, "post")
    root = parent = {"uri": d["uri"], "cid": d.get("cid", "")}
    for i, t in enumerate(p.get("replies") or []):  # the steps, then the finish line and the link
        try:
            r = {"$type": "app.bsky.feed.post", "text": t, "createdAt": now_iso(), "langs": ["en"], "facets": bsky_facets(t), "reply": {"root": root, "parent": parent}}
            s3, d3 = http("POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", headers=auth, data={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": r})
            d3 = ok_or_raise(s3, d3, f"reply {i + 1}")
            parent = {"uri": d3["uri"], "cid": d3.get("cid", "")}
        except Exception as e:  # noqa: BLE001  the main post is up; never re-posted
            print(f"  bsky reply {i + 1} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
            break
    return f"https://bsky.app/profile/{sess.get('handle') or env('OP_BSKY_ID')}/post/{d['uri'].rsplit('/', 1)[-1]}"


def pub_mastodon(item, text):
    p = _post(item, "mastodon", text)
    text = p["text"]
    inst = env("OP_MASTODON_INSTANCE", "https://mastodon.social").rstrip("/")
    auth = {"Authorization": f"Bearer {env('OP_MASTODON_TOKEN')}"}
    img = media(item, "square")
    body, ctype = multipart({"description": img["alt"][:1500]}, "file", "card.png", img["png"], "image/png")
    s0, up = http("POST", f"{inst}/api/v2/media", raw=body, headers={**auth, "Content-Type": ctype}, timeout=60)
    mid = ok_or_raise(s0, up, "image upload")["id"]
    for _ in range(6):  # 202 = still processing
        if s0 == 200 or (isinstance(up, dict) and up.get("url")):
            break
        time.sleep(2)
        s0, up = http("GET", f"{inst}/api/v1/media/{mid}", headers=auth)
    form = [("status", text), ("visibility", "public"), ("language", "en"), ("media_ids[]", mid)]
    s, d = http("POST", f"{inst}/api/v1/statuses", form=form, headers={**auth, "Idempotency-Key": hashlib.sha256(f"op|{item['id']}".encode()).hexdigest()})
    return ok_or_raise(s, d, "post").get("url", "")


def pub_discord(item, text):
    text = _post(item, "discord", text)["text"]
    url = env("OP_DISCORD_WEBHOOK")
    img = media(item, "wide")
    embed = {"title": item["title"][:256], "url": link(item, "discord"), "description": fit(item["goal"], 400), "color": 0xA8321E, "image": {"url": img["url"]}}
    s, d = http("POST", url + ("&" if "?" in url else "?") + "wait=true", data={"username": "Open Practice", "content": text, "embeds": [embed], "allowed_mentions": {"parse": []}})
    return f"discord message {ok_or_raise(s, d, 'webhook').get('id', '')}"


# Nostr: NIP-01 kind 1 note, BIP-340 Schnorr signature (coincurve), several relays.
_CH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _conv(data, f, t, pad=True):
    acc = bits = 0
    out, maxv = [], (1 << t) - 1
    for v in data:
        acc = (acc << f) | v
        bits += f
        while bits >= t:
            bits -= t
            out.append((acc >> bits) & maxv)
    if pad and bits:
        out.append((acc << (t - bits)) & maxv)
    return out


def bech32_encode(hrp: str, data: bytes) -> str:
    d = _conv(data, 8, 5)
    exp = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    pm = _polymod(exp + d + [0] * 6) ^ 1
    return hrp + "1" + "".join(_CH[x] for x in d + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])


def bech32_decode(s: str) -> bytes:
    s = s.lower()
    pos = s.rfind("1")
    d = [_CH.find(x) for x in s[pos + 1:]]
    return bytes(_conv(d[:-6], 5, 8, False))


def nostr_secret() -> bytes:
    v = env("OP_NOSTR_NSEC")
    b = bech32_decode(v) if v.startswith("nsec1") else bytes.fromhex(v)
    if len(b) != 32:
        raise RailError("OP_NOSTR_NSEC is not a 32-byte key")
    return b


def nostr_event(content: str, tags: list, sec: bytes, created: int | None = None) -> dict:
    from coincurve import PrivateKey
    pk = PrivateKey(sec)
    pub = pk.public_key.format(compressed=True)[1:].hex()
    created = created or int(time.time())
    ser = json.dumps([0, pub, created, 1, tags, content], separators=(",", ":"), ensure_ascii=False)
    eid = hashlib.sha256(ser.encode("utf-8")).digest()
    return {"id": eid.hex(), "pubkey": pub, "created_at": created, "kind": 1, "tags": tags, "content": content, "sig": pk.sign_schnorr(eid, os.urandom(32)).hex()}


async def _relay_send(url: str, ev: dict, timeout: float = 12.0) -> bool:
    import websockets
    try:
        async with websockets.connect(url, open_timeout=timeout, close_timeout=3, user_agent_header=UA) as ws:
            await ws.send(json.dumps(["EVENT", ev]))
            end = time.time() + timeout
            while time.time() < end:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.5, end - time.time())))
                if msg and msg[0] == "OK" and msg[1] == ev["id"]:
                    return bool(msg[2])
    except Exception:  # noqa: BLE001  one slow relay never fails the note
        return False
    return False


def pub_nostr(item, text):
    text = _post(item, "nostr", text)["text"]
    img = media(item, "square")
    tags = [["t", t] for t in dict.fromkeys(h.lower() for h in item["hashtags"])] + [["r", link(item, "nostr")]]
    text = f"{text}\n\n{img['url']}"
    tags.append(["imeta", f"url {img['url']}", "m image/png", f"dim {img['w']}x{img['h']}", f"alt {img['alt'][:400]}"])
    ev = nostr_event(text, tags, nostr_secret())

    async def all_relays():
        return await asyncio.gather(*[_relay_send(r, ev) for r in NOSTR_RELAYS])
    n = sum(asyncio.run(all_relays()))
    if not n:
        raise RailError("no relay accepted the note")
    return f"https://njump.me/{bech32_encode('note', bytes.fromhex(ev['id']))} ({n}/{len(NOSTR_RELAYS)} relays)"


BUFFER_MUTATION = ("mutation($i: CreatePostInput!) { createPost(input: $i) { __typename ... on PostActionSuccess { post { id status } } "
                   "... on InvalidInputError { message } ... on UnexpectedError { message } ... on LimitReachedError { message } } }")
_BUF: dict = {}


def buffer_gql(query, variables=None):
    s, d = http("POST", "https://api.buffer.com", data={"query": query, "variables": variables or {}}, headers={"Authorization": f"Bearer {env('OP_BUFFER_KEY')}"})
    d = ok_or_raise(s, d, "buffer")
    if d.get("errors"):
        raise RailError("buffer: " + str(d["errors"][0].get("message"))[:160])
    return d["data"]


def buffer_channel(service: str) -> dict:
    if "channels" not in _BUF:
        chans = []
        for o in (buffer_gql("query { account { organizations { id } } }")["account"]["organizations"] or [])[:3]:
            q = "query($i: ChannelsInput!) { channels(input: $i) { id service name isDisconnected } }"
            chans += [c for c in buffer_gql(q, {"i": {"organizationId": o["id"]}})["channels"] if not c.get("isDisconnected")]
        _BUF["channels"] = chans
    for c in _BUF["channels"]:
        if c["service"] == service:
            return c
    raise WaitingError(f"no {service} channel connected in Buffer yet")


def buffer_post(inp: dict) -> str:
    res = buffer_gql(BUFFER_MUTATION, {"i": inp})["createPost"]
    if res.get("__typename") != "PostActionSuccess":
        raise RailError("buffer: " + str(res.get("message") or res.get("__typename"))[:160])
    return f"buffer post {res['post']['id']} ({res['post'].get('status', '')})"


def pub_facebook(item, text):
    text = _post(item, "facebook", text)["text"]
    ch = buffer_channel("facebook")
    img = media(item, "square")
    return buffer_post({"channelId": ch["id"], "text": text, "mode": "shareNow", "schedulingType": "automatic",
                        "assets": [{"image": {"url": img["url"], "metadata": {"altText": img["alt"][:1000]}}}], "metadata": {"facebook": {"type": "post"}}})


def pub_pinterest(item, text):
    """Pinterest is a search engine: keyword-first title, a natural description with no hashtags, real alt text."""
    p = _post(item, "pinterest", text)
    ch = buffer_channel("pinterest")
    img = media(item, "pin")
    return buffer_post({"channelId": ch["id"], "text": p["description"], "mode": "shareNow", "schedulingType": "automatic",
                        "assets": [{"image": {"url": img["url"], "metadata": {"altText": (p.get("alt") or img["alt"])[:500]}}}],
                        "metadata": {"pinterest": {"boardServiceId": env("OP_PINBOARD"), "title": p["title"], "url": link(item, "pinterest")}}})


def pub_linkedin(item, text):
    """LinkedIn through Buffer: waits, never fails, until a LinkedIn channel is connected."""
    p = _post(item, "linkedin", text)
    try:
        ch = buffer_channel("linkedin")
    except Exception as e:  # noqa: BLE001
        raise WaitingError("LinkedIn is not connected in Buffer yet") from e
    img = media(item, "wide")
    return buffer_post({"channelId": ch["id"], "text": p["text"], "mode": "shareNow", "schedulingType": "automatic",
                        "assets": [{"image": {"url": img["url"], "metadata": {"altText": (p.get("alt") or img["alt"])[:1000]}}}]})


def pub_tumblr(item, text):
    """A titled text post: Tumblr search reads the title, the text and up to 30 tags. Shorter than the blog article."""
    p = _post(item, "tumblr", text)
    blog = env("OP_TUMBLR_BLOG")
    url = f"https://api.tumblr.com/v2/blog/{blog}.tumblr.com/post"
    img = media(item, "square")
    pic = f'<p><img src="{E(img["url"], quote=True)}" alt="{E(p.get("alt") or img["alt"], quote=True)}"></p>'
    form = {"type": "text", "format": "html", "title": p["title"], "body": pic + p["html"], "tags": ",".join(p["tags"]), "slug": p["slug"]}
    h = oauth1.auth_header("POST", url, form, env("OP_TUMBLR_CONSUMER_KEY"), env("OP_TUMBLR_CONSUMER_SECRET"), env("OP_TUMBLR_TOKEN"), env("OP_TUMBLR_TOKEN_SECRET"))
    st, body = http("POST", url, form=form, headers={"Authorization": h})
    resp = (ok_or_raise(st, body, "tumblr") or {}).get("response") or {}
    return f"https://{blog}.tumblr.com/post/{resp.get('id_string') or resp.get('id')}"


def send_mail(to: str, subject: str, html_body: str) -> None:  # patched in tests
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, env("OP_SMTP_USER"), to
    with smtplib.SMTP_SSL(env("OP_SMTP_HOST", "smtp.gmail.com"), 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(env("OP_SMTP_USER"), env("OP_SMTP_PASS"))
        s.sendmail(env("OP_SMTP_USER"), [to], msg.as_string())


def pub_blogger(item, text):
    """Our own blog, by Blogger's post-by-email address (one mail to our own blog, not outreach).

    The address is the whole rail, so a mistyped domain is silent data loss: Blogger's post-by-email
    addresses always end in @blogger.com, and a look-alike domain (bloggger.com is a parked one) takes
    the mail and drops it. Refuse rather than send into a hole.
    """
    to = env("OP_BLOGGER_EMAIL")
    if not to.lower().endswith("@blogger.com"):
        raise WaitingError(f"OP_BLOGGER_EMAIL {to!r} is not a Blogger post-by-email address "
                           "(they end in @blogger.com); fix it in the blog settings")
    send_mail(to, _post(item, "blogger", text)["title"], long_html(item, media(item, "wide")) + "\n#end")
    return "sent to the blog's post-by-email address"


class WaitingError(Exception):
    pass


PUBLISH = {"bsky": pub_bsky, "mastodon": pub_mastodon, "nostr": pub_nostr, "discord": pub_discord, "facebook": pub_facebook,
           "pinterest": pub_pinterest, "tumblr": pub_tumblr, "blogger": pub_blogger, "linkedin": pub_linkedin}


def creds(rail: str) -> bool:
    return all(env(k) for k in NEED[rail])


# ---------------------------------------------------------------- run
def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def run(day: str, live: bool, rails: list[str], force: bool, state_path: Path, publish: dict | None = None) -> tuple[int, list[dict]]:
    publish = PUBLISH if publish is None else publish
    item = compose(day)
    tx = texts(item)
    state = load_state(state_path)
    today = state.setdefault(day, {})
    wd = dt.date.fromisoformat(day).weekday()
    out, failed = [], 0
    for r in rails:
        row = {"rail": r, "label": LABELS[r], "image": media(item, SHAPE_OF[r])["url"]}
        if not creds(r):
            row.update(status="waiting for account", detail="add " + ", ".join(k for k in NEED[r] if not env(k)))
        elif wd not in DAYS[r] and not force:
            row.update(status="not today", detail="posts on " + ",".join("MTWTFSS"[d] for d in DAYS[r]))
        elif today.get(r) and not force:
            row.update(status="already posted", detail=today[r])
        elif probs := native.gate(r, tx[r], {**story(item), "url": link(item, r)}):
            failed += 1
            row.update(status="held", detail="findability gate: " + "; ".join(probs)[:180])  # never post a weak or broken post
        elif not live:
            row.update(status="dry", detail=(tx[r].get("text") or tx[r].get("title") or "")[:120].replace("\n", " "))
        else:
            try:
                where = publish[r](item, tx[r])
                today[r] = where
                row.update(status="posted", detail=where)
            except WaitingError as e:
                row.update(status="waiting", detail=str(e)[:200])
            except Exception as e:  # noqa: BLE001  one rail never stops the others
                failed += 1
                row.update(status="failed", detail=f"{type(e).__name__}: {str(e)[:200]}")
        out.append(row)
    if live:
        keep = {d: v for d, v in state.items() if d >= (dt.date.fromisoformat(day) - dt.timedelta(days=14)).isoformat()}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(keep, indent=1))
    return failed, [{"item": item["id"], "title": item["title"]}] + out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore the weekday plan and today's guard")
    ap.add_argument("--rails", default="", help="comma list; default all")
    ap.add_argument("--day", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    a = ap.parse_args(argv)
    if env("OP_PRESS", "on") == "off":
        print("OP_PRESS=off: the press is switched off")
        return 0
    rails = [r for r in (a.rails.split(",") if a.rails else RAILS) if r in RAILS]
    failed, rows = run(a.day, a.live, rails, a.force, Path(env("OP_PRESS_STATE", str(ROOT / ".press-state" / "state.json"))))
    head, rows = rows[0], rows[1:]
    lines = [f"## Open Practice press {a.day}: {head['title']}", "", "| rail | status | detail |", "|---|---|---|"]
    lines += [f"| {r['label']} | {r['status']} | {r['detail'].replace('|', '/')} |" for r in rows]
    print("\n".join(lines))
    if env("GITHUB_STEP_SUMMARY"):
        with open(env("GITHUB_STEP_SUMMARY"), "a") as f:
            f.write("\n".join(lines) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
