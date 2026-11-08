#!/usr/bin/env python3
"""Open Practice — company social rails.

A small, self-contained poster for the Open Practice accounts. It is deliberately separate from
the Mechanism Audit and AttestOS desks: different identity, different accounts, different secrets,
and a failure here must never touch those.

    python3 tools/social.py verify              # who am I on each rail, and is the credential live?
    python3 tools/social.py armed               # just the list of rails this process can post to
    python3 tools/social.py post --text "..." [--link URL] [--tags a,b] [--rails bsky,mastodon] [--dry]

Secrets (all optional; a rail is silent until its whole set exists):
    OP_BSKY_ID, OP_BSKY_PASS                      Bluesky handle + app password
    OP_MASTODON_INSTANCE, OP_MASTODON_TOKEN       e.g. mastodon.social
    OP_NOSTR_NSEC                                 bech32 nsec, hex or nsec1...
    OP_DISCORD_WEBHOOK                            channel webhook URL
    OP_TUMBLR_CK, OP_TUMBLR_CS, OP_TUMBLR_TOKEN,
    OP_TUMBLR_TOKEN_SECRET, OP_TUMBLR_BLOG        OAuth 1.0a, blog as the dotted host
    OP_BUFFER_TOKEN                               Buffer API token (GraphQL, api.buffer.com)
    OP_PINTEREST_BOARD                            optional Pinterest board serviceId; discovered if absent

Nothing here invents credentials: every function returns (ok, detail) and a missing secret is a
skip, not an exception.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets as _secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import re

try:
    import postimage
except ImportError:  # pragma: no cover - the module sits next to this file in the repo
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import postimage

UA = "Mozilla/5.0 (compatible; OpenPracticeDesk/1.0; +https://open-practice.open-practice.workers.dev)"
SITE = os.environ.get("OP_SITE_URL", "https://open-practice.open-practice.workers.dev").rstrip("/")
CARD = f"{SITE}/brand/og-1200x630.png"
# the second hosted card: if the og card 404s, this is still a url a platform can fetch
CARD_FALLBACK = f"{SITE}/brand/github-social-1280x640.png"
TIMEOUT = 30
# ----------------------------------------------------------------------------- the image branch
_HERE = os.path.dirname(os.path.abspath(__file__))
# the fallback sits beside the rail, or one level up if the rail lives in tools/
FALLBACK_CARD = next((p for p in (os.path.join(_HERE, "assets", "fallback-card.png"),
                                 os.path.join(os.path.dirname(_HERE), "assets", "fallback-card.png"))
                      if os.path.exists(p)), os.path.join(_HERE, "assets", "fallback-card.png"))
# a per-post image can be named in the text itself: [[image:slug]] or [[image:https://…]]
_IMAGE_HINT = re.compile(r"\[\[image:([^\]]+)\]\]")


def _image(text: str, link: str = "", override: str = "") -> "postimage.Img":
    """Resolve the image for one post: an explicit one, a hint in the text, or the site card.

    Always ends with the bundled fallback, so a card 404 cannot silently produce a text-only post.
    A hint that is not a URL is resolved against the site's own asset folder.
    """
    alt = " ".join(text.split())[:280]
    want = (override or os.environ.get("OP_CARD_URL") or "").strip()
    hint = _IMAGE_HINT.search(text or "")
    if not want and hint:
        want = hint.group(1).strip()
        if not want.startswith(("http://", "https://")):
            want = SITE + "/brand/" + want
    url = want or CARD
    return postimage.resolve_chain([url, CARD_FALLBACK], alt, FALLBACK_CARD)


def _post_raw(url: str, data: bytes, headers: dict) -> dict:
    """Raw body POST, for uploadBlob: the JSON helper would re-encode the image as a string."""
    st, body = _req(url, data, headers, "POST")
    if st != 200:
        raise RuntimeError(f"{url} → {st} {str(body)[:160]}")
    return body if isinstance(body, dict) else {}





# ----------------------------------------------------------------------------- tiny http helpers
def _req(url: str, data: bytes | None = None, headers: dict | None = None,
         method: str | None = None) -> tuple[int, object]:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return resp.status, raw.decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return e.code, raw.decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001 — a rail being down must not crash the run
        return 0, repr(e)[:200]


def _json_post(url: str, body: dict, headers: dict | None = None) -> tuple[int, object]:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    return _req(url, json.dumps(body).encode(), h, "POST")


def env(*names: str) -> list[str]:
    return [(os.environ.get(n) or "").strip() for n in names]


# ----------------------------------------------------------------------------- bluesky
def post_bsky(text: str, link: str = "", tags: list[str] | None = None,
              image: "postimage.Img | None" = None) -> tuple[bool, str]:
    ident, pw = env("OP_BSKY_ID", "OP_BSKY_PASS")
    if not (ident and pw):
        return False, "skip: OP_BSKY_ID/OP_BSKY_PASS not set"
    st, sess = _json_post("https://bsky.social/xrpc/com.atproto.server.createSession",
                          {"identifier": ident, "password": pw})
    if st != 200 or not isinstance(sess, dict) or "accessJwt" not in sess:
        return False, f"login failed: {st} {str(sess)[:120]}"
    auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
    if image is None:
        try:
            image = _image(text, link)
        except postimage.NoImage as e:
            return False, f"no image, not posting: {e}"
    try:
        blob = postimage.bluesky_upload(
            image, auth,
            poster=lambda url, data, headers: _post_raw(url, data, headers))
    except (postimage.NoImage, RuntimeError) as e:
        return False, f"image upload failed, not posting: {e}"
    record = postimage.bluesky_record(
        text, _facets(text, link or ""), image, blob,
        time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), tags=tags)
    st, body = _json_post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                          {"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record}, auth)
    if st != 200:
        return False, f"createRecord {st}: {str(body)[:150]}"
    return True, (body or {}).get("uri", "posted")


def _facets(text: str, link: str = "") -> list[dict]:
    """Byte-offset facets for links. Bluesky rejects a facet whose offsets do not land on the text."""
    out, seen = [], set()
    b = text.encode("utf-8")
    for token in ([link] if link else []) + [w for w in text.split() if w.startswith(("http://", "https://"))]:
        if not token:
            continue
        i = b.find(token.encode("utf-8"))
        if i < 0 or i in seen:
            continue
        seen.add(i)
        out.append({"index": {"byteStart": i, "byteEnd": i + len(token.encode("utf-8"))},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": token}]})
    return out


# ----------------------------------------------------------------------------- mastodon
def post_mastodon(text: str, image: "postimage.Img | None" = None) -> tuple[bool, str]:
    inst, tok = env("OP_MASTODON_INSTANCE", "OP_MASTODON_TOKEN")
    if not (inst and tok):
        return False, "skip: OP_MASTODON_INSTANCE/OP_MASTODON_TOKEN not set"
    host = inst.replace("https://", "").strip("/")
    auth = {"Authorization": f"Bearer {tok}"}
    if image is None:
        try:
            image = _image(text, "")
        except postimage.NoImage as e:
            return False, f"no image, not posting: {e}"
    # media first: a status that names a media id that does not exist is rejected outright
    media_id = ""
    try:
        body, ctype = postimage.mastodon_media_body(image)
        st, media = _req(f"https://{host}/api/v2/media", body,
                         {**auth, "Content-Type": ctype}, "POST")
        if st in (200, 201, 202) and isinstance(media, dict) and media.get("id"):
            media_id = str(media["id"])
            if st == 202:                                   # accepted, still processing
                for _ in range(10):
                    time.sleep(1.5)
                    st2, m2 = _req(f"https://{host}/api/v1/media/{media_id}", headers=auth)
                    if st2 == 200:
                        break
        else:
            return False, f"media upload {st}, not posting: {str(media)[:120]}"
    except postimage.NoImage as e:
        return False, f"no image, not posting: {e}"
    fields = postimage.mastodon_status_fields(text, media_id)
    st, body = _req(f"https://{host}/api/v1/statuses", urllib.parse.urlencode(fields).encode(),
                    {**auth, "Content-Type": "application/x-www-form-urlencoded"}, "POST")
    if st not in (200, 201):
        return False, f"statuses {st}: {str(body)[:150]}"
    return True, (body or {}).get("url", "posted")


# ----------------------------------------------------------------------------- nostr
def _bech32_decode(s: str) -> bytes:
    ch = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    pos = s.rfind("1")
    data = [ch.index(c) for c in s[pos + 1:]][:-6]     # drop checksum
    acc = bits = 0
    out = bytearray()
    for v in data:
        acc, bits = (acc << 5) | v, bits + 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    return bytes(out)


def _sk() -> bytes:
    raw = (os.environ.get("OP_NOSTR_NSEC") or "").strip()
    if not raw:
        return b""
    if raw.startswith("nsec"):
        return _bech32_decode(raw)
    return bytes.fromhex(raw)


def post_nostr(text: str, relays: list[str] | None = None,
               image: "postimage.Img | None" = None) -> tuple[bool, str]:
    sk = _sk()
    if not sk:
        return False, "skip: OP_NOSTR_NSEC not set"
    try:
        import coincurve
    except ImportError:
        return False, "skip: coincurve not installed"
    if image is None:
        try:
            image = _image(text, "")
        except postimage.NoImage as e:
            return False, f"no image, not posting: {e}"
    try:
        tags = [postimage.nostr_imeta(image)]
        content = postimage.nostr_content(text, image)
    except postimage.NoImage as e:
        return False, f"no image url, not posting: {e}"
    relays = relays or [r.strip() for r in (os.environ.get("OP_NOSTR_RELAYS") or
                        # measured 2026-11-08: nos.lol, relay.nostr.band and nostr.mom time out from
                        # here; these answer in under two seconds
                        "wss://relay.damus.io,wss://relay.primal.net,wss://relay.nostr.net").split(",") if r.strip()]
    pk = coincurve.PrivateKey(sk).public_key.format(compressed=True)[1:].hex()
    ev = {"pubkey": pk, "created_at": int(time.time()), "kind": 1,
          "tags": tags, "content": content}
    ser = json.dumps([0, ev["pubkey"], ev["created_at"], ev["kind"], ev["tags"], ev["content"]],
                     separators=(",", ":"), ensure_ascii=False)
    eid = hashlib.sha256(ser.encode()).hexdigest()
    sig = coincurve.PrivateKey(sk).sign_schnorr(bytes.fromhex(eid), aux_randomness=os.urandom(32)).hex()
    ev.update({"id": eid, "sig": sig})
    ok = _publish_nostr(ev, relays)
    return (ok, f"event {eid[:16]}… " + ("accepted by a relay" if ok else "no relay accepted it"))


def _publish_nostr(ev: dict, relays: list[str]) -> bool:
    try:
        import websocket  # websocket-client
    except ImportError:
        try:
            import websockets  # noqa: F401
        except ImportError:
            return False
        return _publish_nostr_async(ev, relays)
    for url in relays:
        ws = None
        try:
            ws = websocket.create_connection(url, timeout=12, header=[f"User-Agent: {UA}"])
            ws.send(json.dumps(["EVENT", ev]))
            deadline = time.time() + 8
            while time.time() < deadline:
                ws.settimeout(max(1, deadline - time.time()))
                msg = json.loads(ws.recv())
                if msg[0] == "OK" and msg[1] == ev["id"] and msg[2]:
                    return True
                if msg[0] == "OK" and msg[1] == ev["id"]:
                    break
        except Exception:  # noqa: BLE001
            continue
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:  # noqa: BLE001
                    pass
    return False


def _publish_nostr_async(ev: dict, relays: list[str]) -> bool:
    import asyncio
    import websockets

    async def one(url: str) -> bool:
        try:
            async with websockets.connect(url, open_timeout=12) as ws:
                await ws.send(json.dumps(["EVENT", ev]))
                async with __import__("asyncio").timeout(8):
                    while True:
                        msg = json.loads(await ws.recv())
                        if msg[0] == "OK" and msg[1] == ev["id"]:
                            return bool(msg[2])
        except Exception:  # noqa: BLE001
            return False
        return False

    async def run() -> bool:
        for url in relays:
            if await one(url):
                return True
        return False

    return asyncio.run(run())


# ----------------------------------------------------------------------------- discord
def post_discord(text: str, image: "postimage.Img | None" = None) -> tuple[bool, str]:
    (wh,) = env("OP_DISCORD_WEBHOOK")
    if not wh:
        return False, "skip: OP_DISCORD_WEBHOOK not set"
    if image is None:
        try:
            image = _image(text, "")
        except postimage.NoImage as e:
            return False, f"no image, not posting: {e}"
    st, body = _json_post(wh + ("&" if "?" in wh else "?") + "wait=true",
                          postimage.discord_payload(text, image, username="Open Practice"))
    if st not in (200, 204):
        return False, f"webhook {st}: {str(body)[:150]}"
    return True, (body or {}).get("id", "posted") if isinstance(body, dict) else "posted"


# ----------------------------------------------------------------------------- tumblr (OAuth 1.0a)
def _oauth1(method: str, url: str, params: dict, ck: str, cs: str, tok: str, tsec: str) -> str:
    oauth = {
        "oauth_consumer_key": ck,
        "oauth_nonce": base64.b32encode(_secrets.token_bytes(16)).decode().strip("="),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": tok,
        "oauth_version": "1.0",
    }
    enc = lambda s: urllib.parse.quote(str(s), safe="~-._")  # noqa: E731
    allp = sorted((enc(k), enc(v)) for k, v in {**params, **oauth}.items())
    qs = "&".join(f"{k}={v}" for k, v in allp)
    base = "&".join([method.upper(), enc(url), enc(qs)])
    key = f"{enc(cs)}&{enc(tsec)}".encode()
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{enc(k)}="{enc(v)}"' for k, v in sorted(oauth.items()))


def tumblr_armed() -> bool:
    return all(env("OP_TUMBLR_CK", "OP_TUMBLR_CS", "OP_TUMBLR_TOKEN",
                   "OP_TUMBLR_TOKEN_SECRET", "OP_TUMBLR_BLOG"))


def _tumblr_title(text: str) -> str:
    """Tumblr themes render a title above the body; the first line is usually the better title.

    If that line is a whole paragraph, cut it at the end of its first sentence and then at a word
    boundary — a title of "Open Practice" on every post tells a reader nothing.
    """
    first = (text.splitlines() or [""])[0].strip()
    if not first:
        return "Open Practice"
    sentence = first.split(". ")[0].strip().rstrip(".")
    if 0 < len(sentence) <= 120:
        return sentence
    if len(first) <= 120:
        return first.rstrip(".")
    cut = first[:120].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:—- ") or "Open Practice"


def post_tumblr(text: str, tags: list[str] | None = None,
                image: "postimage.Img | None" = None) -> tuple[bool, str]:
    ck, cs, tok, tsec, blog = env("OP_TUMBLR_CK", "OP_TUMBLR_CS", "OP_TUMBLR_TOKEN",
                                  "OP_TUMBLR_TOKEN_SECRET", "OP_TUMBLR_BLOG")
    if not all([ck, cs, tok, tsec, blog]):
        return False, "skip: tumblr needs the OAuth exchange first (see tumblr_connect.py)"
    if image is None:
        try:
            image = _image(text, "")
        except postimage.NoImage as e:
            return False, f"no image, not posting: {e}"
    url = f"https://api.tumblr.com/v2/blog/{blog}/post"      # singular: the form-encoded route
    fields = {"type": "text", "format": "markdown", "title": _tumblr_title(text)}
    fields.update(postimage.tumblr_fields(text, image))
    if tags:
        fields["tags"] = ",".join(t.replace("#", "")[:40] for t in tags[:5])
    st, resp = _req(url, urllib.parse.urlencode(fields).encode(),
                    {"Authorization": _oauth1("POST", url, fields, ck, cs, tok, tsec),
                     "Content-Type": "application/x-www-form-urlencoded"}, "POST")
    if st not in (200, 201):
        return False, f"post {st}: {str(resp)[:150]}"
    return True, str((resp.get("response") or {}).get("id", "posted"))


# ----------------------------------------------------------------------------- buffer (Pinterest)
BUFFER_GQL = "https://api.buffer.com"
_ORG: dict[str, str] = {}


def _buffer(query: str, variables: dict | None = None) -> dict:
    tok = (os.environ.get("OP_BUFFER_TOKEN") or "").strip()
    if not tok:
        return {"errors": [{"message": "skip: OP_BUFFER_TOKEN not set"}]}
    body = json.dumps({"query": query, **({"variables": variables} if variables else {})}).encode()
    st, out = _req(BUFFER_GQL, body, {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, "POST")
    if st != 200:
        return {"errors": [{"message": f"http {st}: {str(out)[:160]}"}]}
    return out if isinstance(out, dict) else {"errors": [{"message": str(out)[:160]}]}


def buffer_org() -> str:
    """The organization id, cached: every Buffer call is scoped by it."""
    if "id" in _ORG:
        return _ORG["id"]
    d = _buffer("{ account { id organizations { id name } } }")
    orgs = (((d.get("data") or {}).get("account") or {}).get("organizations") or [])
    if not orgs:
        return ""
    _ORG["id"] = orgs[0]["id"]
    return _ORG["id"]


def buffer_channels() -> list[dict]:
    org = buffer_org()
    if not org:
        return []
    d = _buffer('{ channels(input:{organizationId:"%s"}) { id name service displayName isDisconnected } }' % org)
    return (d.get("data") or {}).get("channels") or []


def pinterest_board(channel_id: str) -> str:
    """The board's serviceId. Buffer needs it on every pin; a wrong one posts to no board."""
    want = (os.environ.get("OP_PINTEREST_BOARD") or "").strip()
    if want:
        return want
    d = _buffer('{ channel(input:{id:"%s"}) { metadata { ... on PinterestMetadata '
                '{ boards { id serviceId name } } } } }' % channel_id)
    ch = (d.get("data") or {}).get("channel") or {}
    boards = ((ch.get("metadata") or {}).get("boards") or [])
    return boards[0]["serviceId"] if boards else ""


def post_buffer(text: str, link: str = "", image: str = "", title: str = "") -> tuple[bool, str]:
    """Publish now to the first Pinterest channel on the account."""
    if not (os.environ.get("OP_BUFFER_TOKEN") or "").strip():
        return False, "skip: OP_BUFFER_TOKEN not set"
    pins = [c for c in buffer_channels() if (c.get("service") or "").lower() == "pinterest"]
    if not pins:
        return False, "no pinterest channel on this Buffer account"
    ch = pins[0]["id"]
    board = pinterest_board(ch)
    if not board:
        return False, "no Pinterest board found for that channel"
    inp: dict = {"channelId": ch, "text": text, "mode": "shareNow", "schedulingType": "automatic",
                 "metadata": {"pinterest": {"boardServiceId": board, "title": (title or text)[:100],
                                            "url": link or SITE}}}
    if image:
        inp["assets"] = [{"image": {"url": image, "metadata": {"altText": title or text[:200]}}}]
    d = _buffer("mutation($input: CreatePostInput!) { createPost(input: $input) { "
                "... on PostActionSuccess { post { id status } } ... on MutationError { message } } }",
                {"input": inp})
    if d.get("errors"):
        return False, str(d["errors"])[:180]
    res = (d.get("data") or {}).get("createPost") or {}
    if "post" in res:
        return True, f"pin {res['post'].get('id')} ({res['post'].get('status')})"
    msg = str(res.get("message") or res)
    # Buffer refuses the identical pin twice in a row. That is a duplicate, not a dead channel.
    if "already got this one" in msg or "same thing twice" in msg:
        return True, "skipped: buffer dedupe (identical pin posted recently)"
    return False, msg[:180]


# ----------------------------------------------------------------------------- orchestration
# names, not function objects: resolved through globals() at call time so a rail can be swapped in
# a test (or patched in a hurry) without rebuilding the table
RAILS = {"bsky": "post_bsky", "mastodon": "post_mastodon", "nostr": "post_nostr",
         "discord": "post_discord", "tumblr": "post_tumblr", "pinterest": "post_buffer"}


def armed() -> list[str]:
    out = []
    if all(env("OP_BSKY_ID", "OP_BSKY_PASS")):
        out.append("bsky")
    if all(env("OP_MASTODON_INSTANCE", "OP_MASTODON_TOKEN")):
        out.append("mastodon")
    if env("OP_NOSTR_NSEC")[0]:
        out.append("nostr")
    if env("OP_DISCORD_WEBHOOK")[0]:
        out.append("discord")
    if tumblr_armed():
        out.append("tumblr")
    if env("OP_BUFFER_TOKEN")[0]:
        out.append("pinterest")
    return out


def post(text: str, link: str = "", tags: list[str] | None = None,
         rails: list[str] | None = None, dry: bool = False,
         image: str = "", allow_text_only: bool = False) -> dict:
    """Post everywhere, with an image on every rail.

    `image` may be a URL or a local path; empty means "use the site card, then the bundled fallback".
    If neither resolves, every rail fails unless `allow_text_only` is set — the rule is that a post
    carries an image, so a missing image is an outage, not a style choice.
    """
    tags = tags or []
    # the link belongs in the text on every rail: a post without it is a dead end
    full = text if not link or link in text else f"{text}\n\n{link}"
    want = rails or armed()
    results: dict[str, tuple[bool, str]] = {}

    card = None
    why = ""
    try:
        card = _image(full, link, override=image)
    except postimage.NoImage as e:
        why = str(e)

    if card is None and not allow_text_only:
        for name in want:
            results[name] = (False, f"not posted: no image ({why})")
        return results

    for name in want:
        fn = globals().get(RAILS.get(name, ""))
        if not fn:
            results[name] = (False, "unknown rail")
            continue
        if dry:
            results[name] = (True, f"dry run" + (f" with {card}" if card else " WITHOUT AN IMAGE"))
            continue
        try:
            if name == "bsky":
                results[name] = post_bsky(full, link=link, tags=tags, image=card)
            elif name == "mastodon":
                results[name] = post_mastodon(full, image=card)
            elif name == "nostr":
                results[name] = post_nostr(full, image=card)
            elif name == "discord":
                results[name] = post_discord(full, image=card)
            elif name == "tumblr":
                results[name] = post_tumblr(full, tags=tags, image=card)
            elif name == "pinterest":
                # a pin has its own tall-format art; an explicit image or a [[image:]] hint wins,
                # otherwise the pin keeps the brand's pin card exactly as before
                explicit = bool(image or _IMAGE_HINT.search(full or ""))
                results[name] = post_buffer(full, link=link or SITE,
                                            image=(card.url if explicit else f"{SITE}/brand/card-activities.png"),
                                            title=text.split("\n")[0][:100])
            else:
                results[name] = fn(full)
        except Exception as e:  # noqa: BLE001
            results[name] = (False, f"raised {e!r}"[:180])
    return results


def verify() -> dict:
    """Read-back the identity behind each credential without posting anything."""
    out: dict[str, str] = {}
    ident, pw = env("OP_BSKY_ID", "OP_BSKY_PASS")
    if ident and pw:
        st, r = _json_post("https://bsky.social/xrpc/com.atproto.server.createSession",
                           {"identifier": ident, "password": pw})
        out["bsky"] = f"@{r['handle']} ({r['did']})" if st == 200 and isinstance(r, dict) else f"FAIL {st}"
    inst, tok = env("OP_MASTODON_INSTANCE", "OP_MASTODON_TOKEN")
    if inst and tok:
        st, r = _req(f"https://{inst.replace('https://','').strip('/')}/api/v1/accounts/verify_credentials",
                     headers={"Authorization": f"Bearer {tok}"})
        out["mastodon"] = f"@{r.get('acct')} on {inst}" if st == 200 and isinstance(r, dict) else f"FAIL {st}"
    if env("OP_NOSTR_NSEC")[0]:
        try:
            import coincurve
            out["nostr"] = "npub key " + coincurve.PrivateKey(_sk()).public_key.format(compressed=True)[1:].hex()[:16] + "…"
        except Exception as e:  # noqa: BLE001
            out["nostr"] = f"FAIL {e!r}"
    (wh,) = env("OP_DISCORD_WEBHOOK")
    if wh:
        st, r = _req(wh)
        out["discord"] = f"webhook '{r.get('name')}' ch {r.get('channel_id')}" if st == 200 and isinstance(r, dict) else f"FAIL {st}"
    if tumblr_armed():
        # read the blog back rather than trusting that five env vars exist
        ck, cs, tok, tsec = env("OP_TUMBLR_CK", "OP_TUMBLR_CS", "OP_TUMBLR_TOKEN", "OP_TUMBLR_TOKEN_SECRET")
        url = "https://api.tumblr.com/v2/user/info"
        st, r = _req(url, headers={"Authorization": _oauth1("GET", url, {}, ck, cs, tok, tsec)})
        if st == 200 and isinstance(r, dict):
            blogs = ((r.get("response") or {}).get("user") or {}).get("blogs") or []
            want = env("OP_TUMBLR_BLOG")[0]
            hit = next((b for b in blogs if b.get("name") == want), None)
            out["tumblr"] = (f"blog {hit['name']} ({hit.get('posts')} posts)" if hit
                             else f"FAIL blog '{want}' not on this account: {[b.get('name') for b in blogs]}")
        else:
            out["tumblr"] = f"FAIL {st}"
    if env("OP_BUFFER_TOKEN")[0]:
        chans = buffer_channels()
        out["pinterest"] = ("channel " + ", ".join(f"{c['service']}/{c['name']}" for c in chans)) if chans else "FAIL no channels"
    # the card is part of the credential now: a dead card URL means the rail cannot post
    try:
        img = _image("", "")
        out["image"] = f"{img.mime} {img.dim} {img.size}B"
    except postimage.NoImage as e:
        out["image"] = f"FAIL {e}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Open Practice company social rails")
    ap.add_argument("cmd", choices=["verify", "armed", "post"])
    ap.add_argument("--text", default="")
    ap.add_argument("--link", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--rails", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--image", default="", help="image url or path for this post")
    ap.add_argument("--allow-text-only", action="store_true",
                    help="post without an image (breaks the rule; for a broken card only)")
    a = ap.parse_args()

    if a.cmd == "armed":
        print(json.dumps(armed()))
        return 0
    if a.cmd == "verify":
        res = verify()
        for k, v in res.items():
            print(f"  {k:9s} {v}")
        missing = [r for r in RAILS if r not in res]
        if missing:
            print(f"  not configured: {', '.join(missing)}")
        # The daily workflow exists to catch a credential that has died, so a FAIL has to be a
        # non-zero exit — otherwise the check is decoration.
        dead = [k for k, v in res.items() if str(v).startswith("FAIL")]
        if dead:
            print(f"  DEAD CREDENTIAL(S): {', '.join(dead)}", file=sys.stderr)
            return 1
        return 0
    if not a.text:
        print("--text is required", file=sys.stderr)
        return 2
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    rails = [r.strip() for r in a.rails.split(",") if r.strip()] or None
    res = post(a.text, link=a.link, tags=tags, rails=rails, dry=a.dry)
    good = failed = 0
    for k, (ok, detail) in res.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k:9s} {detail}")
        good += bool(ok)
        failed += (not ok and not str(detail).startswith("skip"))
    # One rail failing must fail the run. Reporting success because four of five worked is how a
    # dead Pinterest channel goes unnoticed for a week.
    if failed:
        print(f"  {failed} RAIL(S) FAILED: {', '.join(sorted(k for k, (ok, d) in res.items() if not ok and not str(d).startswith('skip')))}",
              file=sys.stderr)
        return 1
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
