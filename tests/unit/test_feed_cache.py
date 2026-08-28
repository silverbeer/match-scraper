"""Unit tests for the conditional-request cache on the assist feeds.

The schedule feed is ~7 MB and moves only when the platform re-syncs, so an
unchanged run should cost a 304 rather than a full download (SB-884). Every
cache failure must degrade to a normal fetch — a broken cache that broke a
scrape would be worse than no cache at all.
"""

import httpx
import pytest

from src.scraper.assist_client import AssistClient, FeedCache

PAYLOAD = {"events": [], "synced_at": "2026-08-28T10:40:11Z"}
URL = "https://mls-assist.theintelligenceplatform.com/data/schedule/x.json"
ETAG = '"fc8363aa5a54fef106e0172f7058aaa1"'
LAST_MODIFIED = "Fri, 28 Aug 2026 10:40:15 GMT"


def _client(handler, cache):
    return AssistClient(
        season_year=2026,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        cache=cache,
    )


class TestFeedCacheStore:
    def test_round_trips_payload_and_validators(self, tmp_path):
        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {"etag": ETAG, "last-modified": LAST_MODIFIED})

        payload, headers = cache.load(URL)

        assert payload == PAYLOAD
        assert headers["If-None-Match"] == ETAG
        assert headers["If-Modified-Since"] == LAST_MODIFIED

    def test_a_response_with_no_validators_is_not_stored(self, tmp_path):
        """Nothing to revalidate against means nothing worth keeping."""
        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {})

        assert cache.load(URL) == (None, {})

    def test_unconfigured_cache_is_a_no_op(self):
        cache = FeedCache(None)
        cache.store(URL, PAYLOAD, {"etag": ETAG})

        assert not cache.enabled
        assert cache.load(URL) == (None, {})

    def test_corrupt_entry_is_ignored_rather_than_raised(self, tmp_path):
        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {"etag": ETAG})
        path = next(tmp_path.glob("*.json"))
        path.write_text("{ truncated")

        assert cache.load(URL) == (None, {})

    def test_unwritable_directory_does_not_raise(self, tmp_path):
        blocked = tmp_path / "file-not-a-dir"
        blocked.write_text("in the way")
        cache = FeedCache(blocked / "cache")

        cache.store(URL, PAYLOAD, {"etag": ETAG})  # must not raise

        assert cache.load(URL) == (None, {})

    def test_url_is_not_used_as_a_path(self, tmp_path):
        """A competition key with a slash must not write outside the directory."""
        cache = FeedCache(tmp_path)
        cache.store("https://x/../../etc/passwd.json", PAYLOAD, {"etag": ETAG})

        written = list(tmp_path.iterdir())
        assert len(written) == 1
        assert written[0].parent == tmp_path

    def test_entries_are_written_atomically(self, tmp_path):
        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {"etag": ETAG})

        assert not list(tmp_path.glob("*.tmp"))


class TestConditionalFetch:
    @pytest.mark.asyncio
    async def test_first_fetch_sends_no_validators_and_caches(self, tmp_path):
        seen = []

        def handler(request):
            seen.append(dict(request.headers))
            return httpx.Response(
                200,
                json=PAYLOAD,
                headers={"etag": ETAG, "last-modified": LAST_MODIFIED},
            )

        cache = FeedCache(tmp_path)
        async with _client(handler, cache) as client:
            payload = await client._fetch_json(URL)

        assert payload == PAYLOAD
        assert "if-none-match" not in seen[0]
        assert cache.load(URL)[0] == PAYLOAD

    @pytest.mark.asyncio
    async def test_304_returns_the_cached_body(self, tmp_path):
        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {"etag": ETAG})
        seen = []

        def handler(request):
            seen.append(request.headers.get("if-none-match"))
            return httpx.Response(304)

        async with _client(handler, cache) as client:
            payload = await client._fetch_json(URL)

        assert payload == PAYLOAD
        assert seen == [ETAG]

    @pytest.mark.asyncio
    async def test_changed_feed_replaces_the_cached_body(self, tmp_path):
        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {"etag": ETAG})
        fresh = {"events": [{"id": 1}], "synced_at": "2026-09-07T10:00:00Z"}

        def handler(request):
            return httpx.Response(200, json=fresh, headers={"etag": '"new"'})

        async with _client(handler, cache) as client:
            payload = await client._fetch_json(URL)

        assert payload == fresh
        assert cache.load(URL) == (fresh, {"If-None-Match": '"new"'})

    @pytest.mark.asyncio
    async def test_304_without_a_cached_body_refetches(self, tmp_path):
        """Told "unchanged" with nothing to show for it, ask again in full.

        Decoding the empty 304 body would raise AssistSeasonNotPublished, and
        the season would be reported as unreleased because of a missing cache
        file.
        """
        calls = []

        def handler(request):
            calls.append(request.headers.get("if-none-match"))
            if len(calls) == 1:
                return httpx.Response(304)
            return httpx.Response(200, json=PAYLOAD, headers={"etag": ETAG})

        cache = FeedCache(tmp_path)
        cache.store(URL, PAYLOAD, {"etag": ETAG})
        next(tmp_path.glob("*.json")).unlink()  # body vanishes after load
        payload, conditional = cache.load(URL)
        assert payload is None

        # Force the 304-with-no-body path: validators sent, nothing stored.
        async with _client(handler, cache) as client:
            client.cache.store(URL, PAYLOAD, {"etag": ETAG})
            next(tmp_path.glob("*.json")).write_text("{ truncated")
            result = await client._fetch_json(URL)

        assert result == PAYLOAD
