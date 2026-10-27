#!/usr/bin/env python3
"""Loopback-only public UX acceptance with synthetic data and no credentials."""

from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.test_workspace_trash_browser import Browser, assert_browser  # noqa: E402


def main() -> None:
    os.environ.update(SUPABASE_URL="", SUPABASE_PUBLISHABLE_KEY="", MT_COOKIE_SECURE="0", MT_LOCAL_ARCHIVE_PREVIEW="0")
    app = importlib.import_module("server")
    artifacts = ROOT / "tmp" / "optimization"
    artifacts.mkdir(parents=True, exist_ok=True)
    works = [
        {"id": f"browser-work-{i}", "title": f"Quiet Weather {i}", "image_url": f"/assets/art/selected-0{i % 5 + 1}.jpg",
         "original_width": 1024, "original_height": 1536, "content_type": "abstract" if i % 2 else "concrete", "ratio_label": "2:3",
         "visibility": "published", "sort_order": i, "creator": {"slug": "browser-creator", "display_name": "Browser Creator"}}
        for i in range(1, 31)
    ]

    class Handler(app.MTRequestHandler):
        mode = "normal"

        def log_message(self, *_args):
            pass

        def handle_archive_images(self, _parsed):
            if self.mode == "slow": time.sleep(13)
            try:
                if self.mode == "error":
                    self.send_json(503, {"source": "supabase-public", "error": {"message": "Works are temporarily unavailable. Please retry."}})
                else:
                    self.send_json(200, {"source": "supabase-public", "items": [] if self.mode == "empty" else works, "count": 0 if self.mode == "empty" else len(works)})
            except BrokenPipeError:
                pass

        def handle_public_creator_get(self, _slug):
            self.send_json(200, {"source": "supabase-public", "creator": {
                "slug": "browser-creator", "display_name": "Browser Creator", "professional_headline": "Photography",
                "bio": "A public biography from the creator response envelope.", "city": "Hangzhou", "country_code": "CN",
                "works": works, "work_count": len(works), "cover": None,
            }})

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    os.environ["MT_PUBLIC_BASE_URL"] = base
    browser = Browser("mt-public-optimization")
    measurements = []
    try:
        browser.close()
        # Visitor pages after the redesign (design/site-mockups-v2): About is
        # part of the homepage, Works holds the two series posters and single
        # works are viewed in the exhibition (requirements 05-07).
        routes = ("/", "/works.html", "/exhibition.html?series=grey", "/contact.html", "/auth/sign-in", "/privacy.html", "/terms.html")
        for width, height in ((1440, 900), (1024, 768), (390, 844)):
            browser.command("set", "viewport", str(width), str(height))
            for route in routes:
                browser.command("open", base + route)
                browser.wait_for("document.readyState === 'complete'")
                if route == "/":
                    browser.wait_for("document.querySelector('[data-about-name]').textContent === 'Browser Creator'")
                if route == "/works.html":
                    browser.wait_for("document.querySelector('[data-series-status-box]').dataset.seriesState === 'ready' && document.querySelectorAll('[data-series-poster]:not([hidden])').length === 2")
                if route.startswith("/exhibition.html"):
                    browser.wait_for("document.querySelector('[data-exhibition-status]').hidden === true")
                assert_browser(browser, "document.documentElement.scrollWidth <= innerWidth + 1", f"Overflow at {route} {width}")
                # Offscreen anti-bot fields are deliberately inaccessible; the
                # selected-works row may scroll horizontally on phones.
                assert_browser(browser, "[...document.querySelectorAll('button:not([hidden]), input:not([type=hidden]), select')].filter(n => n.offsetWidth && !n.closest('[hidden], .mt-honeypot[aria-hidden=true]') && !n.classList.contains('visually-hidden')).every(n => {const r=n.getBoundingClientRect();if(r.left >= -1 && r.right <= innerWidth + 1)return true;for(let p=n.parentElement;p;p=p.parentElement){if(['auto','scroll'].includes(getComputedStyle(p).overflowX)&&p.scrollWidth>p.clientWidth){const q=p.getBoundingClientRect();return q.left>=-1&&q.right<=innerWidth+1&&r.width<=p.clientWidth;}}return false;})", f"Control escapes viewport at {route} {width}")
                errors = browser.json_command("errors")
                assert errors.get("data", {}).get("errors", []) == [], f"Uncaught browser error at {route}: {errors}"
                if route in ("/", "/works.html"):
                    metrics = browser.evaluate("(async () => {const shifts=[]; const paints=[];const a=new PerformanceObserver(l=>shifts.push(...l.getEntries()));a.observe({type:'layout-shift',buffered:true});const b=new PerformanceObserver(l=>paints.push(...l.getEntries()));b.observe({type:'largest-contentful-paint',buffered:true});await new Promise(r=>setTimeout(r,100));a.disconnect();b.disconnect();return {cls:(()=>{let max=0,sum=0,start=0,last=0;for(const e of shifts.filter(e=>!e.hadRecentInput)){if(e.startTime-last>=1000||e.startTime-start>=5000){sum=0;start=e.startTime;}sum+=e.value;last=e.startTime;max=Math.max(max,sum);}return max;})(),lcp_ms:paints.at(-1)?.startTime||null,transferred_bytes:performance.getEntriesByType('resource').reduce((s,e)=>s+e.transferSize,0)};})()")
                    measurements.append({"route": route, "viewport": f"{width}x{height}", **metrics})
                    browser.command("screenshot", str(artifacts / f"public-{route.strip('/').split('.')[0] or 'home'}-{width}.png"))
            print(f"public_browser_viewport_{width}=yes", flush=True)

        browser.command("set", "viewport", "1440", "900")
        browser.command("open", base + "/contact.html")
        browser.wait_for("document.readyState === 'complete'")
        assert_browser(browser, "(async()=>{const s=async p=>{const r=await fetch(p,{cache:'no-store'});const u=new URL(r.url);return [r.status,u.pathname+u.search];};const [about]=await s('/about.html');const [,work]=await s('/work.html?id=browser-work-1');const [,series]=await s('/series.html');const [,lightbox]=await s('/lightbox.html');return about===404&&work==='/exhibition.html?work=browser-work-1'&&series==='/works.html'&&lightbox==='/works.html';})()", "Retired visitor routes are not handled")
        print("public_browser_retired_routes=yes", flush=True)

        browser.evaluate("(()=>{document.querySelector('[data-global-search-toggle]').click();const i=document.querySelector('[data-global-search-input]');i.value='Quiet Weather 3';i.dispatchEvent(new Event('input',{bubbles:true}));return true;})()")
        browser.wait_for("document.querySelector('[data-global-search-results] [role=option]')")
        assert_browser(browser, "document.querySelector('[data-global-search-results] [role=option]').getAttribute('href').startsWith('/exhibition.html?series=grey&work=browser-work-3')", "Search does not open the exhibition")
        print("public_browser_search_opens_exhibition=yes", flush=True)

        Handler.mode = "error"
        browser.command("open", base + "/works.html")
        browser.wait_for("document.querySelector('[data-series-status-box]').dataset.seriesState === 'error'")
        assert_browser(browser, "!document.querySelector('[data-series-retry]').hidden && document.querySelectorAll('[data-series-poster]:not([hidden])').length === 0", "Works error presented as empty")
        Handler.mode = "normal"
        browser.command("click", "[data-series-retry]")
        browser.wait_for("document.querySelector('[data-series-status-box]').dataset.seriesState === 'ready'")
        print("public_browser_error_retry=yes", flush=True)

        Handler.mode = "empty"
        browser.command("open", base + "/works.html")
        browser.wait_for("document.querySelector('[data-series-status-box]').dataset.seriesState === 'empty'")
        assert_browser(browser, "document.querySelectorAll('[data-series-poster]:not([hidden])').length === 0", "Empty authority fell back to samples")
        print("public_browser_authoritative_empty=yes", flush=True)

        Handler.mode = "slow"
        browser.command("open", base + "/works.html")
        browser.wait_for("document.querySelector('[data-series-status-box]').dataset.seriesState === 'error'", timeout=18)
        assert_browser(browser, "document.querySelector('[data-series-status]').textContent.includes('timed out')", "Slow request did not time out")
        print("public_browser_timeout_recovery=yes", flush=True)

        Handler.mode = "normal"
        browser.command("open", base + "/exhibition.html?series=colour&work=browser-work-2")
        browser.wait_for("document.querySelector('[data-exhibition-status]').hidden === true")
        browser.evaluate("(document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})),true)")
        browser.wait_for("new URLSearchParams(location.search).get('work') === 'browser-work-4'")
        # Blocked storage (hint, per-work display settings) must not stop paging.
        browser.evaluate("(Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new DOMException('Blocked','SecurityError')}}),document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true})),true)")
        browser.wait_for("new URLSearchParams(location.search).get('work') === 'browser-work-2'")
        print("public_browser_exhibition_paging=yes", flush=True)
        (artifacts / "public-browser-result.json").write_text(json.dumps(measurements, indent=2))
        print("public_browser_acceptance=yes", flush=True)
    finally:
        browser.close()
        server.shutdown()
        server.server_close()
        print("public_browser_sessions_closed=yes", flush=True)


if __name__ == "__main__":
    main()
