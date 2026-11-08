"""Tests for the image branch.

The rule these lock in: a post carries an image, or it does not go out. No network — every rail is
stubbed, and the image is a 1200x630 PNG header built in memory.

Drop-in for both rails: mechanism-audit/tests/, open-practice/tools/tests/.
Run: python3 -m unittest discover -s tests -p "test_*.py"
"""
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:                                   # mechanism-audit: social.py at the repo root
    import social  # noqa: E402
    import postimage  # noqa: E402
except ImportError:                    # open-practice: tools/social.py
    from tools import social  # noqa: E402
    from tools import postimage  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1200, 630)
       + b"\x08\x06\x00\x00\x00" + b"\x00" * 64)
PREFIX = "MA_" if hasattr(social, "SITE") and "mechanism" in getattr(social, "SITE", "") else "OP_"


def img():
    return postimage.Img(PNG, url="https://example.com/card.png", alt="a card")


class NoImageMeansNoPost(unittest.TestCase):
    def test_every_rail_refuses_when_there_is_no_image(self):
        with mock.patch.object(social, "_image", side_effect=postimage.NoImage("card 404")), \
             mock.patch.object(social, "post_bsky", side_effect=AssertionError("must not post")), \
             mock.patch.object(social, "post_mastodon", side_effect=AssertionError("must not post")):
            res = social.post("hello", rails=["bsky", "mastodon"])
        self.assertFalse(res["bsky"][0])
        self.assertFalse(res["mastodon"][0])
        self.assertIn("no image", res["bsky"][1])

    def test_allow_text_only_is_the_only_way_through(self):
        with mock.patch.object(social, "_image", side_effect=postimage.NoImage("card 404")), \
             mock.patch.object(social, "post_bsky", side_effect=AssertionError("must not post")):
            res = social.post("hello", rails=["bsky"], dry=True)
            self.assertFalse(res["bsky"][0])
            res = social.post("hello", rails=["bsky"], dry=True, allow_text_only=True)
            self.assertTrue(res["bsky"][0])
            self.assertIn("WITHOUT AN IMAGE", res["bsky"][1])


class EveryRailCarriesIt(unittest.TestCase):
    def setUp(self):
        self.card = img()
        p = mock.patch.object(social, "_image", return_value=self.card)
        p.start()
        self.addCleanup(p.stop)

    def test_the_image_reaches_every_rail(self):
        seen = {}

        def spy(name):
            def inner(text, *a, **kw):
                seen[name] = kw.get("image")
                return True, "ok"
            return inner

        with mock.patch.object(social, "post_bsky", spy("bsky")), \
             mock.patch.object(social, "post_mastodon", spy("mastodon")), \
             mock.patch.object(social, "post_nostr", spy("nostr")), \
             mock.patch.object(social, "post_discord", spy("discord")), \
             mock.patch.object(social, "post_tumblr", spy("tumblr")), \
             mock.patch.object(social, "post_buffer", lambda *a, **kw: (True, "pin")):
            res = social.post("hello", rails=["bsky", "mastodon", "nostr", "discord", "tumblr", "pinterest"])
        for name in ("bsky", "mastodon", "nostr", "discord", "tumblr"):
            self.assertTrue(res[name][0], name)
            self.assertIs(seen[name], self.card, f"{name} was not handed the image")

    def test_bsky_record_embeds_the_image_and_keeps_the_link_clickable(self):
        rec = postimage.bluesky_record("hello https://a.test/x", social._facets("hello https://a.test/x"),
                                       self.card, {"$type": "blob"}, "2026-11-08T00:00:00.000Z")
        self.assertEqual(rec["embed"]["$type"], "app.bsky.embed.images")
        self.assertEqual(rec["embed"]["images"][0]["aspectRatio"], {"width": 1200, "height": 630})
        self.assertTrue(any(f["features"][0]["uri"].endswith("/x") for f in rec["facets"]))

    def test_mastodon_uploads_media_before_the_status(self):
        calls = []

        def fake_req(url, data=None, headers=None, method=None):
            calls.append((url, data))
            if "api/v2/media" in url:
                return 200, {"id": "media-1"}
            return 200, {"url": "https://m.test/@x/1"}

        with mock.patch.object(social, "_req", fake_req), \
             mock.patch.dict(os.environ, {PREFIX + "MASTODON_INSTANCE": "m.test",
                                          PREFIX + "MASTODON_TOKEN": "t"}):
            ok, _ = social.post_mastodon("hello")
        self.assertTrue(ok)
        self.assertIn("api/v2/media", calls[0][0])
        self.assertIn(b"media-1", calls[1][1])

    def test_nostr_note_carries_an_imeta_tag(self):
        captured = {}

        def fake_publish(ev, relays):
            captured["ev"] = ev
            return True

        fake_cc = mock.MagicMock()
        fake_cc.PrivateKey.return_value.public_key.format.return_value = b"\x02" + b"\x11" * 32
        fake_cc.PrivateKey.return_value.sign_schnorr.return_value = b"\x00" * 64
        with mock.patch.object(social, "_publish_nostr", fake_publish), \
             mock.patch.dict(sys.modules, {"coincurve": fake_cc}), \
             mock.patch.dict(os.environ, {PREFIX + "NOSTR_NSEC": "11" * 32}):
            ok, _ = social.post_nostr("hello")
        self.assertTrue(ok)
        tag = captured["ev"]["tags"][0]
        self.assertEqual(tag[0], "imeta")
        self.assertIn("url https://example.com/card.png", tag)
        self.assertIn("dim 1200x630", tag)
        self.assertIn("card.png", captured["ev"]["content"])

    def test_discord_embeds_the_image(self):
        sent = {}

        def fake_post(url, body, headers=None):
            sent["body"] = body
            return 200, {"id": "msg-1"}

        with mock.patch.object(social, "_json_post", fake_post), \
             mock.patch.dict(os.environ, {PREFIX + "DISCORD_WEBHOOK": "https://discord.test/hook"}):
            ok, _ = social.post_discord("hello")
        self.assertTrue(ok)
        self.assertEqual(sent["body"]["embeds"][0]["image"]["url"], "https://example.com/card.png")

    def test_tumblr_makes_the_image_native(self):
        sent = {}

        def fake_req(url, data=None, headers=None, method=None):
            sent["data"] = data
            return 200, {"response": {"id": "1"}}

        env = {PREFIX + "TUMBLR_CK": "a", PREFIX + "TUMBLR_CS": "b", PREFIX + "TUMBLR_TOKEN": "c",
               PREFIX + "TUMBLR_TOKEN_SECRET": "d", PREFIX + "TUMBLR_BLOG": "x.tumblr.com"}
        with mock.patch.object(social, "_req", fake_req), mock.patch.dict(os.environ, env):
            ok, _ = social.post_tumblr("hello")
        self.assertTrue(ok)
        self.assertIn(b"native_inline_images=true", sent["data"])


class TheBranchItself(unittest.TestCase):
    def test_hint_in_the_text_names_the_image(self):
        seen = {}

        def fake_resolve(urls, alt, fallback):
            seen["url"] = urls[0]
            return img()

        with mock.patch.object(postimage, "resolve_chain", fake_resolve):
            social._image("hello [[image:gallery/one.png]]")
        self.assertIn("gallery/one.png", seen["url"])

    def test_bad_card_falls_back_then_raises_clearly(self):
        def dead(_url):
            raise RuntimeError("404")

        with self.assertRaises(postimage.NoImage) as ctx:
            postimage.resolve("https://x.test/card.png", "alt", "", fetch_one=dead)
        self.assertIn("404", str(ctx.exception))

    def test_a_real_fallback_file_is_used_when_the_site_is_down(self):
        path = os.path.join(os.path.dirname(__file__), "..", "assets", "fallback-card.png")
        if not os.path.exists(path):
            self.skipTest("no bundled fallback in this checkout")

        def dead(_url):
            raise RuntimeError("card host down")

        got = postimage.resolve("https://x.test/card.png", "alt", path, fetch_one=dead)
        self.assertTrue(got.mime.startswith("image/"))
        self.assertEqual((got.w, got.h), (1200, 630))

    def test_verify_reports_the_card(self):
        with mock.patch.object(social, "_image", return_value=img()):
            out = social.verify()
        self.assertIn("image", out)
        self.assertIn("1200x630", out["image"])


if __name__ == "__main__":
    unittest.main()
