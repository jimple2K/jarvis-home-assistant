"""
Headed Firefox instance that Jarvis fully controls.
Runs on its own thread; Flask calls go through a command queue.
"""
import threading
import queue
import time
import re

_cmd_q   = queue.Queue()
_results = {}
_events  = {}
_lock    = threading.Lock()
_cid     = 0
_thread  = None


def _next_id():
    global _cid
    with _lock:
        _cid += 1
        return _cid


def _dispatch(action, **kwargs):
    cid = _next_id()
    ev  = threading.Event()
    with _lock:
        _events[cid] = ev
    _cmd_q.put({"id": cid, "action": action, **kwargs})
    if not ev.wait(timeout=30):
        return {"error": "Browser timeout"}
    with _lock:
        result = _results.pop(cid, {"error": "No result"})
        _events.pop(cid, None)
    return result


def _worker():
    from playwright.sync_api import sync_playwright

    pages   = {}   # {tab_id: page}
    counter = [0]

    with sync_playwright() as pw:
        browser = pw.firefox.launch(
            headless=False,
            args=["--no-first-run"],
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
        )

        def resolve(cid, result):
            with _lock:
                _results[cid] = result
                if cid in _events:
                    _events[cid].set()

        while True:
            try:
                cmd = _cmd_q.get(timeout=1)
            except queue.Empty:
                continue

            cid    = cmd["id"]
            action = cmd["action"]

            try:
                if action == "open":
                    url = cmd["url"]
                    counter[0] += 1
                    tid  = counter[0]
                    page = ctx.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    pages[tid] = page
                    resolve(cid, {"tab_id": tid, "title": page.title(), "url": page.url})

                elif action == "close":
                    tid = cmd.get("tab_id")
                    if tid == "all":
                        for pg in list(pages.values()):
                            try: pg.close()
                            except: pass
                        pages.clear()
                        resolve(cid, {"closed": "all tabs"})
                    else:
                        tid = int(tid)
                        if tid in pages:
                            pages[tid].close()
                            del pages[tid]
                            resolve(cid, {"closed": tid})
                        else:
                            resolve(cid, {"error": f"Tab {tid} not found"})

                elif action == "list":
                    tabs = []
                    for tid, pg in list(pages.items()):
                        try:
                            tabs.append({"id": tid, "title": pg.title(), "url": pg.url})
                        except Exception:
                            pass
                    resolve(cid, {"tabs": tabs})

                elif action == "content":
                    tid = int(cmd["tab_id"])
                    if tid in pages:
                        pg   = pages[tid]
                        text = pg.inner_text("body")
                        text = re.sub(r"\s{3,}", "\n", text)
                        if len(text) > 10000:
                            text = text[:10000] + "\n...[truncated]"
                        resolve(cid, {"content": text, "title": pg.title(), "url": pg.url})
                    else:
                        resolve(cid, {"error": f"Tab {tid} not found"})

                elif action == "navigate":
                    tid = int(cmd["tab_id"])
                    if tid in pages:
                        pages[tid].goto(cmd["url"], wait_until="domcontentloaded", timeout=20000)
                        resolve(cid, {"title": pages[tid].title(), "url": pages[tid].url})
                    else:
                        resolve(cid, {"error": f"Tab {tid} not found"})

                elif action == "screenshot":
                    tid  = int(cmd["tab_id"])
                    path = cmd.get("path", f"/tmp/jarvis_tab_{tid}.png")
                    if tid in pages:
                        pages[tid].screenshot(path=path, full_page=False)
                        resolve(cid, {"path": path})
                    else:
                        resolve(cid, {"error": f"Tab {tid} not found"})

                elif action == "stop":
                    browser.close()
                    break

            except Exception as e:
                resolve(cid, {"error": str(e)})


def _ensure():
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_worker, daemon=True, name="jarvis-browser")
        _thread.start()
        time.sleep(1.5)


# ── Public API (called from tools.py) ────────────────────────────────────────

def open_url(url: str) -> str:
    _ensure()
    r = _dispatch("open", url=url)
    if "error" in r:
        return f"Error: {r['error']}"
    return f"Opened tab {r['tab_id']} — {r['title']} ({r['url']})"


def close_tab(tab_id) -> str:
    _ensure()
    r = _dispatch("close", tab_id=tab_id)
    if "error" in r:
        return f"Error: {r['error']}"
    return f"Closed: {r['closed']}"


def list_tabs() -> str:
    _ensure()
    r = _dispatch("list")
    tabs = r.get("tabs", [])
    if not tabs:
        return "No open tabs in Jarvis browser."
    return "\n".join(f"Tab {t['id']}: {t['title']} — {t['url']}" for t in tabs)


def get_tab_content(tab_id: int) -> str:
    _ensure()
    r = _dispatch("content", tab_id=tab_id)
    if "error" in r:
        return f"Error: {r['error']}"
    return f"[{r['title']}]\n{r['content']}"


def navigate_tab(tab_id: int, url: str) -> str:
    _ensure()
    r = _dispatch("navigate", tab_id=tab_id, url=url)
    if "error" in r:
        return f"Error: {r['error']}"
    return f"Tab {tab_id} now at: {r['title']} ({r['url']})"


def screenshot_tab(tab_id: int, path: str = "") -> str:
    _ensure()
    kwargs = {"tab_id": tab_id}
    if path:
        kwargs["path"] = path
    r = _dispatch("screenshot", **kwargs)
    if "error" in r:
        return f"Error: {r['error']}"
    return f"Screenshot saved: {r['path']}"


def stop():
    global _thread
    _dispatch("stop")
    _thread = None
