#!/usr/bin/env python3
"""postimage — the image branch the small rails never had.

The AttestOS press engine has carried an image on every post since 2026-09-27: a rendered card, a
static fallback when the renderer is down, and a per-rail way to attach it. The smaller company rails
(`mechanism-audit/social.py`, `open-practice/tools/social.py`) had a card URL defined and never used
it, so their posts went out as bare text. This module is that branch, extracted so both rails can
share it instead of growing two versions of the same idea.

Design rules, in the order they matter:

1. **No image, no post.** `resolve()` returns an `Img` or raises `NoImage`. Callers fail the rail
   rather than shipping text-only — a silent downgrade is exactly how this bug survived.
2. **A fallback is part of the branch.** If the site's card 404s or the network is down, a bundled
   PNG is used. Only if both fail does the post fail.
3. **No third-party packages.** Stdlib only, so a rail cannot be taken offline by a pip install.
4. **Pure builders for the rails.** Every platform's payload is built by a pure function here, so the
   shape of a Bluesky record or a Nostr `imeta` tag can be tested without a network.

Per rail:
    Bluesky   uploadBlob → app.bsky.embed.images
    Mastodon  POST /api/v2/media → media_ids[] on the status
    Nostr     ["imeta", "url …", "m …", "dim WxH", "alt …"]
    Discord   embed.image.url (Discord fetches the URL itself)
    Tumblr    markdown image + native_inline_images=true
    Pinterest assets[0].image.url (Buffer) — already did this

CLI, for checking a card before you trust it:
    python3 postimage.py https://example.com/card.png
    python3 postimage.py --file path/to/card.png
    python3 postimage.py --selftest
"""
from __future__ import annotations

import json
import mimetypes
import os
import struct
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; postimage/1.0)"
TIMEOUT = 30
BSKY_MAX = 1_000_000          # Bluesky rejects blobs over ~1 MB; a bigger card must fall back
DISCOURSE_MAX = 8_000_000     # Mastodon's default media ceiling


class NoImage(RuntimeError):
    """Nothing to attach — the caller must fail the rail, not post without one."""


class Img:
    """An image ready to travel: a public URL for the rails that fetch it, and the bytes for the
    rails that upload it."""

    __slots__ = ("url", "data", "mime", "w", "h", "alt")

    def __init__(self, data: bytes = b"", url: str = "", alt: str = ""):
        self.data = data or b""
        self.url = url or ""
        self.alt = (alt or "").strip()[:1000]
        self.mime = sniff(data) if self.data else ""
        self.w, self.h = dimensions(self.data) if self.data else (0, 0)

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def dim(self) -> str:
        return f"{self.w}x{self.h}" if self.w and self.h else ""

    def __repr__(self) -> str:                      # keeps secrets out of logs: no data, no headers
        return f"Img({self.mime}, {self.dim}, {self.size}B, url={'yes' if self.url else 'no'})"


# --------------------------------------------------------------------------- sniffing
def sniff(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def dimensions(data: bytes) -> tuple[int, int]:
    """Width and height from the header, without decoding the image."""
    if not data:
        return 0, 0
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8 ":
            return struct.unpack("<HH", data[26:30])
        if kind == b"VP8L":
            b = data[21:25]
            w = 1 + (((b[1] & 0x3F) << 8) | b[0])
            h = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
            return w, h
        if kind == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return w, h
    if data[:3] == b"\xff\xd8\xff":                 # walk the JPEG segments to the start-of-frame
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg
    return 0, 0


# --------------------------------------------------------------------------- fetching
def fetch(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def from_file(path: str, alt: str = "") -> Img:
    with open(path, "rb") as f:
        return Img(f.read(), url="", alt=alt)


def resolve(card_url: str = "", alt: str = "", fallback: str = "", *, max_bytes: int = DISCOURSE_MAX,
            fetch_one=fetch) -> Img:
    """The branch. Try the site card, then the bundled fallback, then give up loudly.

    `fallback` may be a local path (preferred, always works) or another URL.
    """
    problems = []
    if card_url:
        try:
            data = fetch_one(card_url)
            if len(data) < 1024:
                problems.append(f"{card_url}: {len(data)} bytes is not an image")
            elif not sniff(data).startswith("image/"):
                problems.append(f"{card_url}: content is {sniff(data)}")
            elif len(data) > max_bytes:
                problems.append(f"{card_url}: {len(data)} bytes over the {max_bytes} cap")
            else:
                return Img(data, url=card_url, alt=alt)
        except Exception as exc:                     # noqa: BLE001 — any failure means "try the fallback"
            problems.append(f"{card_url}: {type(exc).__name__} {exc}")
    if fallback:
        try:
            if "://" in fallback:
                return Img(fetch_one(fallback), url=fallback, alt=alt)
            return from_file(fallback, alt=alt)
        except Exception as exc:                     # noqa: BLE001
            problems.append(f"fallback {fallback}: {type(exc).__name__} {exc}")
    raise NoImage("no image available — " + "; ".join(problems or ["no card url and no fallback"]))


def resolve_chain(urls: list[str], alt: str = "", local: str = "", *,
                  max_bytes: int = BSKY_MAX, fetch_one=fetch) -> Img:
    """Try each url in turn, then the bundled file. The one the rails use.

    The urls matter for the rails that attach by reference (Discord, Tumblr, Nostr, Pinterest); the
    file is the last resort for the rails that upload bytes (Bluesky, Mastodon). A post with an image
    nobody can fetch is still a broken post, so a url is always preferred over a local file.
    """
    problems = []
    for url in [u for u in urls if u]:
        try:
            return resolve(url, alt, "", max_bytes=max_bytes, fetch_one=fetch_one)
        except NoImage as exc:
            problems.append(str(exc))
    if local:
        try:
            img = resolve("", alt, local, max_bytes=max_bytes, fetch_one=fetch_one)
            if img.mime.startswith("image/"):
                return img
        except NoImage as exc:
            problems.append(str(exc))
    raise NoImage("no image available — " + " | ".join(problems or ["nothing to try"]))


def resolve_for_bluesky(card_url: str = "", alt: str = "", fallback: str = "") -> Img:
    """Bluesky has the tightest ceiling, so it picks first and everything else reuses its choice."""
    try:
        return resolve(card_url, alt, fallback, max_bytes=BSKY_MAX)
    except NoImage:
        # the card may be a fine JPEG that is simply too big; the fallback is a small PNG
        if fallback:
            img = resolve("", alt, fallback, max_bytes=BSKY_MAX)
            img.url = card_url or img.url
            return img
        raise


# --------------------------------------------------------------------------- Bluesky
def bluesky_upload(img: Img, auth: dict, poster=None) -> dict:
    """Upload as a blob and return the reference Bluesky wants in an embed."""
    if not img.data:
        raise NoImage("bluesky needs the bytes, not just the url")
    post = poster or _post_bytes
    out = post("https://bsky.social/xrpc/com.atproto.repo.uploadBlob", img.data,
               {**auth, "Content-Type": img.mime or "image/png"})
    if not isinstance(out, dict) or "blob" not in out:
        raise RuntimeError(f"uploadBlob returned {str(out)[:160]}")
    return out["blob"]


def bluesky_record(text: str, facets: list[dict], img: Img, blob: dict, created: str,
                   tags: list[str] | None = None) -> dict:
    """One embed only, and the image wins: a link card and an image cannot both be attached, and a
    post with an image is the rule. The link still arrives as a facet, so it stays clickable."""
    record: dict = {"text": text, "createdAt": created, "langs": ["en"], "facets": facets}
    if tags:
        record["tags"] = [t.replace("#", "")[:64] for t in tags][:8]
    images = [{"alt": img.alt or text[:1000], "image": blob}]
    if img.w and img.h:
        images[0]["aspectRatio"] = {"width": img.w, "height": img.h}
    record["embed"] = {"$type": "app.bsky.embed.images", "images": images}
    return record


# --------------------------------------------------------------------------- Mastodon
def mastodon_media_headers(auth: str) -> dict:
    return {"Authorization": auth}


def mastodon_media_body(img: Img, boundary: str = "") -> tuple[bytes, str]:
    """The multipart body for POST /api/v2/media, and the boundary to name in the header."""
    boundary = boundary or "postimage" + os.urandom(8).hex()
    name = "card." + (img.mime.split("/")[-1] if img.mime.startswith("image/") else "png")
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: {img.mime or 'image/png'}\r\n\r\n").encode() + img.data + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="description"\r\n\r\n'
        f"{img.alt}\r\n--{boundary}--\r\n").encode()
    return body, f"multipart/form-data; boundary={boundary}"


def mastodon_status_fields(text: str, media_id: str = "") -> dict:
    fields: dict = {"status": text}
    if media_id:
        fields["media_ids[]"] = media_id
    return fields


# --------------------------------------------------------------------------- Nostr
def nostr_imeta(img: Img) -> list[str]:
    """NIP-92/NIP-94 inline metadata: enough for a client to show the image and for a reader to
    know what it is without fetching it first."""
    if not img.url:
        raise NoImage("nostr needs a public url for the image (clients fetch it themselves)")
    tag = ["imeta", f"url {img.url}"]
    if img.mime:
        tag.append(f"m {img.mime}")
    if img.dim:
        tag.append(f"dim {img.dim}")
    if img.alt:
        tag.append(f"alt {img.alt}")
    return tag


def nostr_content(text: str, img: Img) -> str:
    """A bare URL on its own line renders as an image in most clients; the imeta tag does the rest."""
    if not img.url:
        raise NoImage("nostr needs a public url for the image")
    return f"{text}\n\n{img.url}"


# --------------------------------------------------------------------------- Discord, Tumblr
def discord_payload(text: str, img: Img, username: str = "") -> dict:
    if not img.url:
        raise NoImage("discord needs a public url (it fetches the embed itself)")
    out: dict = {"content": text[:1900],
                 "embeds": [{"image": {"url": img.url}}],
                 "allowed_mentions": {"parse": []}}
    if img.alt:
        out["embeds"][0]["description"] = img.alt[:300]
    if username:
        out["username"] = username
    return out


def tumblr_fields(text: str, img: Img) -> dict:
    """`native_inline_images` makes Tumblr host its own copy, so the post survives the card URL
    changing. A dead image URL is worse than no post."""
    if not img.url:
        raise NoImage("tumblr needs a public url for the inline image")
    body = f"![{img.alt or 'card'}]({img.url})\n\n{text}"
    return {"body": body[:3000], "native_inline_images": "true"}


# --------------------------------------------------------------------------- http shim
def _post_bytes(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} → {e.code} {e.read()[:160]!r}") from None


# --------------------------------------------------------------------------- cli
def _selftest() -> int:
    ok = 0
    bad = 0

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal ok, bad
        if cond:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ {name} {detail}")

    # a 2x3 PNG header is enough to prove the parser, no image decoding involved
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1200, 630)
           + b"\x08\x06\x00\x00\x00" + b"\x00" * 40)
    check("png sniff", sniff(png) == "image/png")
    check("png dimensions", dimensions(png) == (1200, 630), str(dimensions(png)))
    check("jpg sniff", sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == "image/jpeg")
    check("gif dimensions", dimensions(b"GIF89a" + struct.pack("<HH", 600, 400)) == (600, 400))
    check("short buffer is not an image", dimensions(b"abc") == (0, 0))

    img = Img(png, url="https://example.com/card.png", alt=" a card ")
    check("alt trimmed", img.alt == "a card")
    check("dim property", img.dim == "1200x630")
    check("repr leaks no bytes", "PNG" not in repr(img))

    tag = nostr_imeta(img)
    check("imeta leads with url", tag[0] == "imeta" and tag[1] == "url https://example.com/card.png")
    check("imeta carries dim", "dim 1200x630" in tag)
    check("imeta carries alt", "alt a card" in tag)

    rec = bluesky_record("hello", [], img, {"$type": "blob"}, "2026-11-08T00:00:00.000Z")
    check("bsky embed is images", rec["embed"]["$type"] == "app.bsky.embed.images")
    check("bsky carries aspect", rec["embed"]["images"][0]["aspectRatio"] == {"width": 1200, "height": 630})

    body, ctype = mastodon_media_body(img, boundary="B")
    check("mastodon multipart names the file", b'name="file"; filename="card.png"' in body)
    check("mastodon content type", ctype == "multipart/form-data; boundary=B")
    check("mastodon status field", mastodon_status_fields("x", "42")["media_ids[]"] == "42")

    check("discord embed", discord_payload("x", img)["embeds"][0]["image"]["url"].endswith("card.png"))
    check("tumblr inline", tumblr_fields("x", img)["native_inline_images"] == "true")

    # the branch itself: card fails → fallback; both fail → NoImage
    def boom(_url):
        raise RuntimeError("404")

    # chain: first url dies, second answers
    def only_second(url, timeout=30):
        if "primary" in url:
            raise RuntimeError("404")
        return b"\x89PNG\r\n\x1a\n" + struct.pack(">II", 10, 10) + b"\x00" * 1280

    got = resolve_chain(["https://x/primary.png", "https://x/secondary.png"], "alt", "", fetch_one=only_second)
    check("chain falls to the second url", got.url.endswith("secondary.png"))
    try:
        resolve_chain(["https://x/primary.png"], "alt", "", fetch_one=only_second)
        check("chain raises when nothing answers", False)
    except NoImage:
        check("chain raises when nothing answers", True)
    try:
        resolve("https://x/y.png", "alt", "", fetch_one=boom)
        check("no image raises", False)
    except NoImage:
        check("no image raises", True)

    print(f"  {'✓' if not bad else '✗'} postimage selftest: {ok}/{ok + bad}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return _selftest()
    if argv[0] == "--file":
        img = from_file(argv[1], alt=os.environ.get("POSTIMAGE_ALT", ""))
        print(f"{argv[1]}: {img.mime} {img.dim} {img.size} bytes")
        return 0 if img.mime.startswith("image/") else 1
    url = argv[0]
    try:
        img = Img(fetch(url), url=url)
    except Exception as exc:                        # noqa: BLE001
        print(f"✗ {url}: {type(exc).__name__} {exc}", file=sys.stderr)
        return 1
    ok = img.mime.startswith("image/") and img.size > 1024
    fits = img.size <= BSKY_MAX
    print(f"{'✓' if ok else '✗'} {url}: {img.mime} {img.dim} {img.size} bytes "
          f"(bluesky {'ok' if fits else 'TOO BIG — needs the fallback'})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
