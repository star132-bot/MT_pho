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
        {"id": f"browser-work-{i}", "title": f"Quiet Weather {i}", "image_url": f"/assets/art/{'abstract' if i % 2 else 'concrete'}-0{i % 3 + 1}.jpg",
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
        for width, height in ((1440, 900), (1024, 768), (390, 844)):
            browser.command("set", "viewport", str(width), str(height))
            for route in ("/", "/about.html", "/works.html", "/lightbox.html", "/contact.html", "/work.html?id=browser-work-1", "/creators/browser-creator", "/auth/sign-in", "/privacy.html", "/terms.html"):
                browser.command("open", base + route)
                browser.wait_for("document.readyState === 'complete'")
                if route == "/works.html": browser.wait_for("document.querySelectorAll('[data-item-id]').length === 30")
                if route == "/about.html": browser.wait_for("document.querySelector('[data-about-name]').textContent === 'Browser Creator'")
                assert_browser(browser, "document.documentElement.scrollWidth <= innerWidth + 1", f"Overflow at {route} {width}")
                # Offscreen anti-bot fields are deliberately inaccessible.
                # Ratio tabs may scroll horizontally within a bounded strip.
                assert_browser(browser, "[...document.querySelectorAll('button:not([hidden]), input:not([type=hidden]), select')].filter(n => n.offsetWidth && !n.closest('[hidden], .contact-honeypot[aria-hidden=true]')).every(n => {const r=n.getBoundingClientRect();if(r.left >= -1 && r.right <= innerWidth + 1)return true;for(let p=n.parentElement;p;p=p.parentElement){if(['auto','scroll'].includes(getComputedStyle(p).overflowX)&&p.scrollWidth>p.clientWidth){const q=p.getBoundingClientRect();return q.left>=-1&&q.right<=innerWidth+1&&r.width<=p.clientWidth;}}return false;})", f"Control escapes viewport at {route} {width}")
                errors = browser.json_command("errors")
                assert errors.get("data", {}).get("errors", []) == [], f"Uncaught browser error at {route}: {errors}"
                if route in ("/", "/works.html", "/about.html"):
                    metrics = browser.evaluate("(async () => {const shifts=[]; const paints=[];const a=new PerformanceObserver(l=>shifts.push(...l.getEntries()));a.observe({type:'layout-shift',buffered:true});const b=new PerformanceObserver(l=>paints.push(...l.getEntries()));b.observe({type:'largest-contentful-paint',buffered:true});await new Promise(r=>setTimeout(r,100));a.disconnect();b.disconnect();return {cls:(()=>{let max=0,sum=0,start=0,last=0;for(const e of shifts.filter(e=>!e.hadRecentInput)){if(e.startTime-last>=1000||e.startTime-start>=5000){sum=0;start=e.startTime;}sum+=e.value;last=e.startTime;max=Math.max(max,sum);}return max;})(),lcp_ms:paints.at(-1)?.startTime||null,transferred_bytes:performance.getEntriesByType('resource').reduce((s,e)=>s+e.transferSize,0)};})()")
                    measurements.append({"route": route, "viewport": f"{width}x{height}", **metrics})
                    browser.command("screenshot", str(artifacts / f"public-{route.strip('/').split('.')[0] or 'home'}-{width}.png"))
                if route == "/":
                    browser.command("click", "[data-marquee-pause]")
                    assert_browser(browser, "document.querySelector('[data-marquee-pause]').getAttribute('aria-pressed') === 'true' && getComputedStyle(document.querySelector('.marquee-track')).animationPlayState === 'paused'", "Marquee pause failed")
                    browser.command("click", "[data-marquee-pause]")
            print(f"public_browser_viewport_{width}=yes", flush=True)

        browser.command("open", base + "/")
        browser.evaluate("(async()=>{const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('mt-cijian-archive',4);r.onupgradeneeded=()=>{for(const name of ['images','site_settings'])if(!r.result.objectStoreNames.contains(name))r.result.createObjectStore(name,{keyPath:'id'});};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});await new Promise((resolve,reject)=>{const t=db.transaction('site_settings','readwrite');t.objectStore('site_settings').put({id:'homepage',hero:{abstract:{title:'Private preview canary'}}});t.oncomplete=resolve;t.onerror=()=>reject(t.error);});db.close();return true;})()")
        browser.command("open", base + "/")
        assert_browser(browser, "document.querySelector('[data-home-hero-panel=abstract] [data-home-hero-title]').textContent !== 'Private preview canary'", "Private homepage settings leaked into public mode")
        app.LOCAL_ARCHIVE_PREVIEW = True
        browser.command("open", base + "/")
        browser.wait_for("document.querySelector('[data-home-hero-panel=abstract] [data-home-hero-title]').textContent === 'Private preview canary'")
        app.LOCAL_ARCHIVE_PREVIEW = False
        print("public_browser_homepage_preview_isolated=yes", flush=True)

        browser.command("open", base + "/works.html")
        assert_browser(browser, "(()=>{const n=document.querySelector('[data-filter-ratio=Panorama]');n.focus();const r=n.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1;})()", "Keyboard cannot reach last ratio tab")
        print("public_browser_ratio_tabs_reachable=yes", flush=True)

        Handler.mode = "error"
        browser.command("open", base + "/works.html?type=Abstract")
        browser.wait_for("document.querySelector('[data-archive-data-status]').dataset.state === 'error'")
        assert_browser(browser, "!document.querySelector('[data-archive-retry]').hidden && document.querySelector('[data-archive-empty]').hidden", "Works error presented as empty")
        Handler.mode = "normal"
        browser.command("click", "[data-archive-retry]")
        browser.wait_for("document.querySelector('[data-archive-data-status]').dataset.state === 'ready'")
        assert_browser(browser, "document.querySelector('[data-filter-type=Abstract]').getAttribute('aria-pressed') === 'true'", "Retry lost filters")
        print("public_browser_error_retry_preserves_filters=yes", flush=True)

        Handler.mode = "error"
        browser.command("open", base + "/lightbox.html")
        browser.wait_for("document.querySelector('[data-lightbox-status]').dataset.state === 'error'")
        assert_browser(browser, "document.querySelector('[data-lightbox-empty]').hidden && !document.querySelector('[data-lightbox-retry]').hidden", "Lightbox error presented as empty")
        Handler.mode = "normal"
        browser.command("click", "[data-lightbox-retry]")
        browser.wait_for("document.querySelector('[data-lightbox-status]').dataset.state === 'ready'")
        print("public_browser_lightbox_recovery=yes", flush=True)

        Handler.mode = "empty"
        browser.command("open", base + "/works.html")
        browser.wait_for("document.querySelector('[data-archive-data-status]').dataset.state === 'ready'")
        assert_browser(browser, "!document.querySelector('[data-archive-empty]').hidden && document.querySelectorAll('[data-item-id]').length === 0", "Empty authority fell back to samples")
        print("public_browser_authoritative_empty=yes", flush=True)

        Handler.mode = "slow"
        browser.command("open", base + "/works.html")
        browser.wait_for("document.querySelector('[data-archive-data-status]').dataset.state === 'error'", timeout=18)
        assert_browser(browser, "document.querySelector('[data-archive-data-status]').textContent.includes('timed out')", "Slow request did not time out")
        print("public_browser_timeout_recovery=yes", flush=True)

        Handler.mode = "normal"
        browser.command("open", base + "/work.html?id=browser-work-1")
        browser.wait_for("document.querySelector('[data-work-detail-main]')?.getAttribute('aria-busy') === 'false' || document.querySelector('[data-work-detail-save]')?.offsetWidth > 0")
        assert_browser(browser, "(Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new DOMException('Blocked','SecurityError')}}),window.MTPresencePublicArchive.readLightboxIds().length === 0)", "Blocked storage broke reading")
        print("public_browser_blocked_storage_safe=yes", flush=True)
        (artifacts / "public-browser-result.json").write_text(json.dumps(measurements, indent=2))
        print("public_browser_acceptance=yes", flush=True)
    finally:
        browser.close()
        server.shutdown()
        server.server_close()
        print("public_browser_sessions_closed=yes", flush=True)


if __name__ == "__main__":
    main()
