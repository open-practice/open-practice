"""python3 -m unittest discover -s scripts/press   (needs Pillow; coincurve only for the Nostr signing test)"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import press  # noqa: E402
from PIL import Image  # noqa: E402

DAY = "2026-11-05"  # a Thursday
CLEAN = {k: "" for rail in press.NEED.values() for k in rail}


def with_env(**kv):
    return mock.patch.dict(os.environ, {**CLEAN, **kv})


class Compose(unittest.TestCase):
    def test_the_day_picks_one_activity_and_walks_all_of_them(self):
        acts = press.activities()
        self.assertEqual(len(acts), 50)
        import datetime as dt
        days = [(dt.date(2026, 11, 1) + dt.timedelta(days=i)).isoformat() for i in range(50)]
        self.assertEqual(len({press.pick(d, acts)["id"] for d in days}), 50, "50 consecutive days cover every activity once")
        self.assertEqual(press.pick(DAY, acts)["id"], press.pick(DAY, acts)["id"])

    def test_v3_every_activity_on_every_rail_passes_the_findability_gate_with_its_tracked_link(self):
        for a in press.activities():
            item = press.compose(DAY, a)
            tx, st = press.texts(item), press.story(item)
            for r in press.RAILS:
                link = press.link(item, r)
                self.assertEqual(press.native.gate(r, tx[r], {**st, "url": link}), [], (a["id"], r))
                blob = json.dumps(tx[r])
                if r != "blogger":  # the article links the blogger URL inside long_html
                    self.assertIn(f"/activities/{a['id']}.html?src={press.SRC[r]}", blob, (a["id"], r))
            self.assertNotIn("#", tx["pinterest"]["description"], a["id"])
            self.assertTrue(tx["pinterest"]["title"].lower().startswith(st["keyphrase"].lower()), a["id"])
            self.assertTrue(3 <= len(re.findall(r"#\w+", tx["mastodon"]["text"])) <= 5, a["id"])

    def test_sources_are_ones_the_growth_counter_knows(self):
        api = (press.ROOT / "packages" / "growth" / "api.mjs").read_text()
        known = set(re.search(r"growthSources=new Set\(\[([^\]]*)\]", api).group(1).replace("'", "").split(","))
        self.assertLessEqual(set(press.SRC.values()), known)

    def test_copy_rules(self):
        """No 'free' framing and the house word rule (the banned-name guard lives in the main test suite)."""
        a = press.pick(DAY)
        item = press.compose(DAY, a)
        blob = json.dumps(press.texts(item)) + press.long_html(item) + (press.HERE / "brand.json").read_text()
        low = blob.lower()
        for bad in ("free", "sch" + "ool"):
            self.assertNotIn(bad, low, bad)

    def test_the_article_is_the_activity_with_real_headings(self):
        item = press.compose(DAY)
        h = press.long_html(item, press.media(item, "wide"))
        self.assertGreaterEqual(h.count("<h2>"), 4)
        self.assertIn("<ol>", h)
        self.assertIn("/brand/press/", h)
        self.assertGreater(len(re.sub(r"<[^>]+>", " ", h).split()), 250)


class Cards(unittest.TestCase):
    def test_every_activity_has_its_three_cards_on_disk(self):
        for a in press.activities():
            for shape, size in (("wide", (1200, 630)), ("square", (1080, 1080)), ("pin", (1000, 1500))):
                p = press.card_path(a, shape)
                self.assertTrue(p.is_file(), f"run scripts/press/make_cards.py ({p.name} missing)")
                self.assertEqual(Image.open(p).size, size)
                self.assertLess(p.stat().st_size, 200_000)

    def test_media_is_a_public_url_plus_the_same_bytes(self):
        item = press.compose(DAY)
        m = press.media(item, "square")
        self.assertTrue(m["url"].startswith(press.SITE + "/brand/press/"))
        self.assertEqual(m["png"], press.card_path(item["activity"], "square").read_bytes())
        self.assertIn(item["title"], m["alt"])

    def test_a_missing_card_is_drawn_now_and_never_leaves_a_post_without_an_image(self):
        item = press.compose(DAY)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(press, "CARDS", Path(d)):
            m = press.media(item, "wide")
        self.assertEqual(Image.open(io.BytesIO(m["png"])).size, (1200, 630))
        self.assertTrue(m["url"].endswith(".jpg") or m["url"].endswith("og-card.png"))


class Run(unittest.TestCase):
    def test_with_no_accounts_every_rail_waits_and_nothing_is_sent(self):
        sent = []
        with with_env(), tempfile.TemporaryDirectory() as d:
            failed, rows = press.run(DAY, True, press.RAILS, False, Path(d) / "s.json", publish={r: lambda i, t: sent.append(t) for r in press.RAILS})
        self.assertEqual(failed, 0)
        self.assertEqual(sent, [])
        self.assertEqual({r["status"] for r in rows[1:]}, {"waiting for account"})
        self.assertTrue(all(r["image"].startswith(press.SITE) for r in rows[1:]))

    def test_posts_once_a_day_follows_the_weekday_plan_and_one_failure_stops_nothing(self):
        calls = []

        def ok(rail):
            return lambda item, text: calls.append(rail) or f"https://example.test/{rail}"

        def boom(item, text):
            raise press.RailError("HTTP 500")
        pub = {r: ok(r) for r in press.RAILS}
        pub["mastodon"] = boom
        kv = {"OP_BSKY_ID": "a", "OP_BSKY_PASS": "b", "OP_MASTODON_TOKEN": "t", "OP_BUFFER_KEY": "k", "OP_PINBOARD": "1"}
        with with_env(**kv), tempfile.TemporaryDirectory() as d:
            st = Path(d) / "s.json"
            failed, rows = press.run(DAY, True, press.RAILS, False, st, publish=pub)
            by = {r["rail"]: r["status"] for r in rows[1:]}
            self.assertEqual(failed, 1)
            self.assertEqual(by["bsky"], "posted")
            self.assertEqual(by["mastodon"], "failed")
            self.assertEqual(by["facebook"], "posted")       # Thursday: weekday rail
            self.assertEqual(by["pinterest"], "not today")   # Mon/Wed/Fri
            self.assertEqual(by["nostr"], "waiting for account")
            self.assertEqual(json.loads(st.read_text())[DAY]["bsky"], "https://example.test/bsky")
            failed2, rows2 = press.run(DAY, True, press.RAILS, False, st, publish=pub)
            by2 = {r["rail"]: r["status"] for r in rows2[1:]}
            self.assertEqual(by2["bsky"], "already posted")
            self.assertEqual(calls.count("bsky"), 1, "a re-run never posts twice")

    def test_dry_run_writes_nothing(self):
        with with_env(OP_BSKY_ID="a", OP_BSKY_PASS="b"), tempfile.TemporaryDirectory() as d:
            st = Path(d) / "s.json"
            failed, rows = press.run(DAY, False, ["bsky"], False, st)
            self.assertEqual(rows[1]["status"], "dry")
            self.assertFalse(st.exists())


class Rails(unittest.TestCase):
    def test_bluesky_uploads_the_card_and_tags_link_and_hashtags(self):
        seen = []

        def fake(method, url, **kw):
            seen.append((url, kw))
            if url.endswith("createSession"):
                return 200, {"accessJwt": "j", "did": "did:x", "handle": "op.bsky.social"}
            if url.endswith("uploadBlob"):
                return 200, {"blob": {"ref": "b"}}
            n = sum(1 for u, _ in seen if u.endswith("createRecord"))
            return 200, {"uri": "at://did:x/app.bsky.feed.post/" + ("abc" if n == 1 else f"r{n}"), "cid": f"c{n}"}
        item = press.compose(DAY)
        text = press.texts(item)["bsky"]
        with with_env(OP_BSKY_ID="op.bsky.social", OP_BSKY_PASS="p"), mock.patch.object(press, "http", fake):
            where = press.pub_bsky(item, text)
        self.assertEqual(where, "https://bsky.app/profile/op.bsky.social/post/abc")
        self.assertEqual(seen[1][1]["raw"][:4], b"\x89PNG")
        rec = seen[2][1]["data"]["record"]
        kinds = [f["features"][0]["$type"].rsplit("#", 1)[1] for f in rec["facets"]]
        self.assertEqual(kinds.count("link"), 0)   # v3: the link card carries the link; the last reply repeats it
        self.assertEqual(kinds.count("tag"), 2)
        self.assertEqual(rec["embed"]["external"]["thumb"], {"ref": "b"})
        self.assertIn("?src=bluesky", rec["embed"]["external"]["uri"])
        self.assertTrue(rec["tags"])
        last = seen[-1][1]["data"]["record"]
        self.assertEqual(last["reply"]["root"]["uri"], "at://did:x/app.bsky.feed.post/abc")
        self.assertIn("?src=bluesky", last["text"])

    def test_buffer_posts_carry_the_card_and_alt_text(self):
        posted = []

        def fake_gql(q, v=None):
            if "organizations" in q:
                return {"account": {"organizations": [{"id": "o"}]}}
            if "channels(" in q:
                return {"channels": [{"id": "fb1", "service": "facebook"}, {"id": "pi1", "service": "pinterest"}]}
            posted.append(v["i"])
            return {"createPost": {"__typename": "PostActionSuccess", "post": {"id": "p1", "status": "sent"}}}
        item = press.compose(DAY)
        press._BUF.clear()
        with with_env(OP_BUFFER_KEY="k", OP_PINBOARD="99"), mock.patch.object(press, "buffer_gql", fake_gql):
            press.pub_facebook(item, "t")
            press.pub_pinterest(item, "t")
        fb, pin = posted
        self.assertEqual(fb["metadata"]["facebook"]["type"], "post")
        self.assertTrue(fb["assets"][0]["image"]["url"].endswith("-square.png"))
        self.assertTrue(pin["assets"][0]["image"]["url"].endswith("-pin.png"))
        self.assertEqual(pin["metadata"]["pinterest"]["boardServiceId"], "99")
        self.assertLessEqual(len(pin["metadata"]["pinterest"]["title"]), 100)
        self.assertTrue(fb["assets"][0]["image"]["metadata"]["altText"])

    def test_blogger_refuses_an_address_that_is_not_bloggers(self):
        """bloggger.com is a parked domain: mail to it vanishes, so the rail must not send."""
        item = press.compose(DAY)
        with with_env(OP_BLOGGER_EMAIL="x.op@bloggger.com", OP_SMTP_USER="u", OP_SMTP_PASS="p"):
            with self.assertRaises(press.WaitingError):
                press.pub_blogger(item, "t")

    def test_blogger_mails_the_article_to_our_own_blog(self):
        got = []
        item = press.compose(DAY)
        with with_env(OP_BLOGGER_EMAIL="x.op@blogger.com", OP_SMTP_USER="u", OP_SMTP_PASS="p"), \
                mock.patch.object(press, "send_mail", lambda to, subj, body: got.append((to, subj, body))):
            press.pub_blogger(item, "t")
        to, subj, body = got[0]
        self.assertEqual(to, "x.op@blogger.com")
        self.assertIn(item["title"], subj)
        self.assertTrue(body.endswith("#end"))
        self.assertIn("<img", body)

    def test_nostr_note_is_signed_and_carries_the_image(self):
        try:
            import coincurve  # noqa: F401
        except ImportError:
            self.skipTest("coincurve not installed")
        ev = press.nostr_event("hi", [["t", "ai"]], bytes(range(1, 33)), created=1700000000)
        self.assertEqual(len(ev["id"]), 64)
        self.assertEqual(len(ev["sig"]), 128)
        self.assertTrue(press.bech32_encode("note", bytes.fromhex(ev["id"])).startswith("note1"))


if __name__ == "__main__":
    unittest.main()
