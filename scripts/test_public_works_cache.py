#!/usr/bin/env python3
"""Network-free acceptance for the cached anonymous public Works list."""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from functools import partial
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SUPABASE_URL"] = "https://fixture.supabase.co"
os.environ["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_fixture"
os.environ["MT_COOKIE_SECURE"] = "0"
os.environ["MT_PUBLIC_WORKS_CACHE_SECONDS"] = "120"

import server


BUILDS: list[int] = []


def fixture_works(version: int) -> dict:
    asset = {"id": f"asset-{version}", "signed_url": f"https://fixture.supabase.co/v{version}", "expires_in": 600}
    return {
        "items": [{"id": f"work-{version}", "display": dict(asset), "thumbnail": dict(asset)}],
        "count": 1,
        "source": "supabase-public",
    }


def fake_load(self, target_creator_slug, maximum):
    return {"version": len(BUILDS) + 1}


def fake_sign(self, result, *, maximum=100):
    BUILDS.append(result["version"])
    return fixture_works(result["version"])


def get(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/archive/images", timeout=10) as response:
        if response.status != HTTPStatus.OK:
            raise RuntimeError(f"unexpected status {response.status}")
        return json.loads(response.read())


def post(port: int, path: str) -> None:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"{}", method="POST")
    try:
        urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError:
        pass  # rejected writes still invalidate; the cache must never outlive a possible change


def main() -> None:
    server.MTRequestHandler.load_public_delivery_works = fake_load
    server.MTRequestHandler.signed_public_works = fake_sign
    app = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.MTRequestHandler, directory=str(ROOT)))
    port = app.server_address[1]
    threading.Thread(target=app.serve_forever, daemon=True).start()
    try:
        first = get(port)
        second = get(port)
        if len(BUILDS) != 1 or second["items"][0]["id"] != first["items"][0]["id"]:
            raise RuntimeError("second anonymous request was not served from the cache")
        if not 1 <= second["items"][0]["display"]["expires_in"] <= server.PUBLIC_DELIVERY_SIGNED_URL_TTL:
            raise RuntimeError("cached signed URL lifetime is not reported truthfully")

        post(port, "/api/inquiries")
        get(port)
        if len(BUILDS) != 1:
            raise RuntimeError("a public inquiry needlessly cleared the Works cache")

        post(port, "/api/admin/works/00000000-0000-4000-8000-000000000001/takedown")
        if get(port)["items"][0]["id"] != "work-2" or len(BUILDS) != 2:
            raise RuntimeError("an admin write did not invalidate the Works cache")

        post(port, "/api/me/profile")
        get(port)
        if len(BUILDS) != 3:
            raise RuntimeError("a profile write did not invalidate the Works cache")

        # A list built before a publication change must not be stored afterwards.
        generation = server.public_works_cache_generation()
        server.invalidate_public_works_cache()
        server.store_public_response(f"works:{server.PUBLIC_DELIVERY_MAX_WORKS}", fixture_works(99), generation)
        if get(port)["items"][0]["id"] == "work-99":
            raise RuntimeError("a stale in-flight build overwrote fresh publication state")

        # The background warmer fills the cache without a request context.
        server.invalidate_public_works_cache()
        builds = len(BUILDS)
        if not server.PublicWorksRefresher().refresh() or len(BUILDS) != builds + 1:
            raise RuntimeError("the background refresher did not rebuild the list")
        get(port)
        if len(BUILDS) != builds + 1:
            raise RuntimeError("a request after a warm refresh still rebuilt the list")

        server.PUBLIC_WORKS_CACHE_SECONDS = 0
        server.invalidate_public_works_cache()
        get(port)
        get(port)
        if len(BUILDS) != builds + 3:
            raise RuntimeError("MT_PUBLIC_WORKS_CACHE_SECONDS=0 did not disable caching")
    finally:
        app.shutdown()
        app.server_close()

    print("Public Works cache acceptance passed (hit, truthful expiry, admin/profile invalidation, stale-build guard, warmer, disable).")


if __name__ == "__main__":
    main()
