import os
import re
import subprocess
import shutil
import psutil
import socket
import platform
import datetime
import urllib.request
import urllib.parse
import urllib.error
import browser as _browser
import db
import ssh_metrics as _ssh
import spotify as _spotify


def _run(cmd, timeout=30, cwd=None):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd or os.path.expanduser("~")
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0 and not out:
            return err or f"Exit code {result.returncode}"
        return (out + ("\n" + err if err else "")).strip()
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


# ── Shell ─────────────────────────────────────────────────────────────────────

def bash(command: str, timeout: int = 30) -> str:
    return _run(command, timeout=timeout)


# ── Filesystem ────────────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    path = os.path.expanduser(path)
    try:
        with open(path, "r", errors="replace") as f:
            content = f.read()
        if len(content) > 20000:
            return content[:20000] + f"\n\n[truncated — file is {len(content)} chars]"
        return content
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written: {path}"
    except Exception as e:
        return f"Error: {e}"


def append_file(path: str, content: str) -> str:
    path = os.path.expanduser(path)
    try:
        with open(path, "a") as f:
            f.write(content)
        return f"Appended to: {path}"
    except Exception as e:
        return f"Error: {e}"


def list_directory(path: str = "~", show_hidden: bool = False) -> str:
    path = os.path.expanduser(path)
    try:
        entries = os.listdir(path)
        if not show_hidden:
            entries = [e for e in entries if not e.startswith(".")]
        entries.sort()
        lines = []
        for e in entries:
            full = os.path.join(path, e)
            kind = "DIR " if os.path.isdir(full) else "FILE"
            try:
                size = os.path.getsize(full)
                lines.append(f"{kind}  {e}  ({size:,} bytes)")
            except Exception:
                lines.append(f"{kind}  {e}")
        return "\n".join(lines) if lines else "(empty)"
    except Exception as e:
        return f"Error: {e}"


def search_files(pattern: str, path: str = "~", content_grep: str = "") -> str:
    path = os.path.expanduser(path)
    try:
        if content_grep:
            cmd = f'grep -rl "{content_grep}" "{path}" 2>/dev/null | head -50'
        else:
            cmd = f'find "{path}" -name "{pattern}" 2>/dev/null | head -50'
        return _run(cmd, timeout=15)
    except Exception as e:
        return f"Error: {e}"


def delete_file(path: str) -> str:
    path = os.path.expanduser(path)
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"Deleted: {path}"
    except Exception as e:
        return f"Error: {e}"


def move_file(src: str, dst: str) -> str:
    src = os.path.expanduser(src)
    dst = os.path.expanduser(dst)
    try:
        shutil.move(src, dst)
        return f"Moved {src} -> {dst}"
    except Exception as e:
        return f"Error: {e}"


def copy_file(src: str, dst: str) -> str:
    src = os.path.expanduser(src)
    dst = os.path.expanduser(dst)
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return f"Copied {src} -> {dst}"
    except Exception as e:
        return f"Error: {e}"


# ── System info ───────────────────────────────────────────────────────────────

def get_system_info() -> str:
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot
        net = psutil.net_io_counters()
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "unknown"

        return (
            f"Host: {hostname} ({local_ip})\n"
            f"OS: {platform.system()} {platform.release()} {platform.machine()}\n"
            f"CPU: {cpu}% used, {psutil.cpu_count()} cores\n"
            f"RAM: {mem.used / 1e9:.1f}GB / {mem.total / 1e9:.1f}GB ({mem.percent}%)\n"
            f"Disk: {disk.used / 1e9:.1f}GB / {disk.total / 1e9:.1f}GB ({disk.percent}%)\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Net TX: {net.bytes_sent / 1e6:.1f}MB  RX: {net.bytes_recv / 1e6:.1f}MB"
        )
    except Exception as e:
        return f"Error: {e}"


def list_processes(filter_name: str = "") -> str:
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                if filter_name and filter_name.lower() not in info["name"].lower():
                    continue
                procs.append(f"PID {info['pid']:6}  {info['name'][:30]:<30}  CPU {info['cpu_percent']:5.1f}%  MEM {info['memory_percent']:4.1f}%  {info['status']}")
            except Exception:
                pass
        procs.sort(key=lambda x: x)
        return "\n".join(procs[:80]) if procs else "No matching processes"
    except Exception as e:
        return f"Error: {e}"


def kill_process(pid: int = None, name: str = "") -> str:
    try:
        killed = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if pid and p.pid == pid:
                    p.terminate()
                    killed.append(f"{p.pid} ({p.name()})")
                elif name and name.lower() in p.name().lower():
                    p.terminate()
                    killed.append(f"{p.pid} ({p.name()})")
            except Exception:
                pass
        return f"Terminated: {', '.join(killed)}" if killed else "No matching process found"
    except Exception as e:
        return f"Error: {e}"


def get_network_info() -> str:
    try:
        lines = []
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    lines.append(f"{iface}: {addr.address}")
        conns = psutil.net_connections(kind="inet")
        listening = [c for c in conns if c.status == "LISTEN"]
        lines.append(f"\nListening ports: {sorted(set(c.laddr.port for c in listening))}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Desktop / UI ──────────────────────────────────────────────────────────────

def notify(title: str, message: str, urgency: str = "normal") -> str:
    try:
        _run(f'notify-send -u {urgency} "{title}" "{message}"')
        return f"Notification sent: [{title}] {message}"
    except Exception as e:
        return f"Error: {e}"


def screenshot(output_path: str = "~/screenshot.png") -> str:
    output_path = os.path.expanduser(output_path)
    # Try scrot, then import (imagemagick), then gnome-screenshot
    for cmd in [
        f"scrot '{output_path}'",
        f"import -window root '{output_path}'",
        f"gnome-screenshot -f '{output_path}'",
    ]:
        result = _run(cmd, timeout=10)
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            return f"Screenshot saved to {output_path} ({size:,} bytes)"
    return "Screenshot failed — install scrot: sudo apt install scrot"


def get_clipboard() -> str:
    for cmd in ["xclip -selection clipboard -o", "xsel --clipboard --output", "wl-paste"]:
        result = _run(cmd, timeout=5)
        if "command not found" not in result and "Error" not in result:
            return result or "(empty clipboard)"
    return "xclip not found — install: sudo apt install xclip"


def set_clipboard(text: str) -> str:
    for cmd in [
        f'echo "{text}" | xclip -selection clipboard',
        f'echo "{text}" | xsel --clipboard --input',
        f'echo "{text}" | wl-copy',
    ]:
        result = _run(cmd, timeout=5)
        if "command not found" not in result:
            return f"Clipboard set to: {text[:80]}"
    return "xclip not found — install: sudo apt install xclip"


def open_application(app: str) -> str:
    result = _run(f"nohup {app} &>/dev/null &", timeout=5)
    return f"Launched: {app}"


# ── Web ───────────────────────────────────────────────────────────────────────

def web_fetch(url: str, max_chars: int = 8000) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
            # Strip HTML tags roughly
            import re
            if "html" in content_type.lower():
                raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL)
                raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
                raw = re.sub(r"<[^>]+>", " ", raw)
                raw = re.sub(r"\s{2,}", " ", raw)
            if len(raw) > max_chars:
                raw = raw[:max_chars] + f"\n\n[truncated — {len(raw)} chars total]"
            return raw.strip()
    except Exception as e:
        return f"Error fetching {url}: {e}"


def web_search(query: str) -> str:
    """Search DuckDuckGo and return titles, URLs, and snippets."""
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        results = []
        # Extract result blocks
        blocks = re.findall(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        for href, title, snippet in blocks[:8]:
            # DuckDuckGo wraps URLs — decode the actual destination
            if "uddg=" in href:
                m = re.search(r"uddg=([^&]+)", href)
                if m:
                    href = urllib.parse.unquote(m.group(1))
            title   = re.sub(r"<[^>]+>", "", title).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            results.append(f"• {title}\n  {href}\n  {snippet}")

        return "\n\n".join(results) if results else web_fetch(
            f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}", max_chars=4000
        )
    except Exception as e:
        return f"Search error: {e}"


# ── Browser control ───────────────────────────────────────────────────────────

def browser_open(url: str) -> str:
    """Open a URL in Jarvis's controlled Firefox window so the user can see it."""
    return _browser.open_url(url)


def browser_close(tab_id: str = "all") -> str:
    """Close a browser tab by ID, or 'all' to close every tab."""
    return _browser.close_tab(tab_id)


def browser_list_tabs() -> str:
    """List all tabs currently open in the Jarvis browser."""
    return _browser.list_tabs()


def browser_get_content(tab_id: int) -> str:
    """Read the visible text content of a browser tab."""
    return _browser.get_tab_content(tab_id)


def browser_navigate(tab_id: int, url: str) -> str:
    """Navigate an existing tab to a new URL."""
    return _browser.navigate_tab(tab_id, url)


def browser_screenshot(tab_id: int, path: str = "") -> str:
    """Take a screenshot of a browser tab and save it to disk."""
    return _browser.screenshot_tab(tab_id, path)


# ── Memory ────────────────────────────────────────────────────────────────────

def remember(content: str, type: str = "fact", importance: int = 1) -> str:
    return db.store_memory(content, type=type, importance=importance)


def recall(query: str) -> str:
    return db.search_memories(query) or "Nothing relevant found in memory."


def list_memories() -> str:
    return db.list_all_memories()


def forget(memory_id: int) -> str:
    return db.delete_memory(memory_id)


# ── Topics ────────────────────────────────────────────────────────────────────

def add_topic(title: str, description: str = "") -> str:
    t = db.add_topic(title, description)
    return f"Added topic: {title} (ID {t['id']})"


def remove_topic(topic_id: int) -> str:
    return db.remove_topic(topic_id)


def set_active_topic(topic_id: int) -> str:
    return db.set_active_topic(topic_id)


def list_topics() -> str:
    topics = db.get_topics()
    if not topics:
        return "No topics yet."
    return "\n".join(
        f"ID {t['id']} {'★' if t['pinned'] else ''}{'▶' if t['active'] else ''} {t['title']}: {t['description']}"
        for t in topics
    )


# ── Concepts ──────────────────────────────────────────────────────────────────

def add_concept(text: str, category: str = "info", ttl_minutes: int = 60) -> str:
    return db.add_concept(text, category=category, ttl_minutes=ttl_minutes)


def remove_concept(concept_id: int) -> str:
    return db.remove_concept(concept_id)


# ── SSH / Remote machine tools ────────────────────────────────────────────────

def ssh_add_host(hostname: str, ip: str, username: str = "root",
                 port: int = 22, key_path: str = "", password: str = "") -> str:
    return _ssh.add_host(hostname, ip, username=username, port=port,
                         key_path=key_path, password=password)


def ssh_remove_host(hostname: str) -> str:
    return _ssh.remove_host(hostname)


def ssh_list_hosts() -> str:
    hosts = _ssh.list_hosts()
    if not hosts:
        return "No SSH hosts configured."
    lines = []
    for h in hosts:
        status = "✓" if h["enabled"] else "✗"
        err    = f" [err: {h['last_error']}]" if h.get("last_error") else ""
        lines.append(f"{status} {h['username']}@{h['hostname']} ({h['ip']}:{h['port']}){err}")
    return "\n".join(lines)


def ssh_get_metrics(hostname: str) -> str:
    m = _ssh.collect_metrics(hostname)
    if "error" in m:
        return f"Error connecting to {hostname}: {m['error']}"
    up = m.get("uptime_s", 0)
    days, rem = divmod(up, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    uptime_str = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"
    return (
        f"{hostname} — {m.get('os','')}\n"
        f"CPU: {m['cpu_pct']}%  RAM: {m['mem_pct']}%  Disk: {m['disk_pct']}%\n"
        f"Load: {m['load_1m']}  Uptime: {uptime_str}"
    )


def ssh_get_all_metrics() -> str:
    results = _ssh.collect_all_metrics()
    if not results:
        return "No SSH hosts configured."
    lines = []
    for m in results:
        if "error" in m:
            lines.append(f"✗ {m['hostname']}: {m['error']}")
        else:
            lines.append(
                f"✓ {m['hostname']} — CPU {m['cpu_pct']}% | RAM {m['mem_pct']}% | Disk {m['disk_pct']}% | Load {m['load_1m']}"
            )
    return "\n".join(lines)


def ssh_run_command(hostname: str, command: str) -> str:
    return _ssh.run_remote(hostname, command)


# ── Cron / scheduled tasks ────────────────────────────────────────────────────

def cron_list() -> str:
    return _run("crontab -l 2>/dev/null || echo '(no crontab)'")


def cron_add(schedule: str, command: str) -> str:
    existing = _run("crontab -l 2>/dev/null")
    new_line = f"{schedule} {command}"
    new_cron = (existing.strip() + "\n" + new_line).strip() + "\n"
    tmp = "/tmp/jarvis_cron_tmp"
    with open(tmp, "w") as f:
        f.write(new_cron)
    result = _run(f"crontab {tmp}")
    return f"Added cron: {new_line}"


# ── Spotify ───────────────────────────────────────────────────────────────────

def spotify_now_playing() -> str:
    info = _spotify.now_playing()
    if not info.get("running"):
        return "Spotify is not running."
    if not info.get("title"):
        return f"Spotify is {info.get('status', 'idle')} — no track info available."
    status = info.get("status", "")
    return f"{info['title']} by {info['artist']} [{status}]"


def spotify_play_pause() -> str:
    return _spotify.play_pause()


def spotify_next() -> str:
    return _spotify.next_track()


def spotify_previous() -> str:
    return _spotify.previous_track()


def spotify_stop() -> str:
    return _spotify.stop()


def spotify_volume(percent: int) -> str:
    return _spotify.set_volume(percent)


def spotify_search(query: str) -> str:
    """Open Spotify with a search so the user can browse results."""
    return _spotify.open_search(query)


def spotify_play(query: str, kind: str = "track") -> str:
    """Search Spotify and immediately play the best result (requires Web API credentials)."""
    return _spotify.search_and_play(query, kind=kind)


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "bash":               bash,
    "read_file":          read_file,
    "write_file":         write_file,
    "append_file":        append_file,
    "list_directory":     list_directory,
    "search_files":       search_files,
    "delete_file":        delete_file,
    "move_file":          move_file,
    "copy_file":          copy_file,
    "get_system_info":    get_system_info,
    "list_processes":     list_processes,
    "kill_process":       kill_process,
    "get_network_info":   get_network_info,
    "notify":             notify,
    "screenshot":         screenshot,
    "get_clipboard":      get_clipboard,
    "set_clipboard":      set_clipboard,
    "open_application":   open_application,
    "web_fetch":          web_fetch,
    "web_search":         web_search,
    "cron_list":          cron_list,
    "cron_add":           cron_add,
    "browser_open":       browser_open,
    "browser_close":      browser_close,
    "browser_list_tabs":  browser_list_tabs,
    "browser_get_content":browser_get_content,
    "browser_navigate":   browser_navigate,
    "browser_screenshot": browser_screenshot,
    "remember":           remember,
    "recall":             recall,
    "list_memories":      list_memories,
    "forget":             forget,
    "add_topic":          add_topic,
    "remove_topic":       remove_topic,
    "set_active_topic":   set_active_topic,
    "list_topics":        list_topics,
    "add_concept":        add_concept,
    "remove_concept":     remove_concept,
    "ssh_add_host":       ssh_add_host,
    "ssh_remove_host":    ssh_remove_host,
    "ssh_list_hosts":     ssh_list_hosts,
    "ssh_get_metrics":    ssh_get_metrics,
    "ssh_get_all_metrics":ssh_get_all_metrics,
    "ssh_run_command":    ssh_run_command,
    "spotify_now_playing": spotify_now_playing,
    "spotify_play_pause":  spotify_play_pause,
    "spotify_next":        spotify_next,
    "spotify_previous":    spotify_previous,
    "spotify_stop":        spotify_stop,
    "spotify_volume":      spotify_volume,
    "spotify_search":      spotify_search,
    "spotify_play":        spotify_play,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run any shell command on the local machine. Full access — sudo, apt, systemctl, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the filesystem.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (overwrite) a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append text to an existing file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default ~)"},
                    "show_hidden": {"type": "boolean"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files by name pattern or grep for text content inside files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Filename pattern (e.g. *.py)"},
                    "path": {"type": "string", "description": "Root path to search from"},
                    "content_grep": {"type": "string", "description": "Search inside files for this text"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"}
                },
                "required": ["src", "dst"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"}
                },
                "required": ["src", "dst"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get CPU, RAM, disk, uptime, network IO, and OS info for this machine.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "List running processes with CPU and memory usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_name": {"type": "string", "description": "Optional name filter"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminate a process by PID or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "name": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_info",
            "description": "Get network interfaces, IPs, and listening ports.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notify",
            "description": "Send a desktop notification popup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                    "urgency": {"type": "string", "enum": ["low", "normal", "critical"]}
                },
                "required": ["title", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Take a screenshot and save it to disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output_path": {"type": "string", "description": "Where to save the image (default ~/screenshot.png)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard",
            "description": "Read the current clipboard contents.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_clipboard",
            "description": "Set the clipboard to a given text.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Launch an application by command name (e.g. firefox, nautilus, gedit).",
            "parameters": {
                "type": "object",
                "properties": {"app": {"type": "string"}},
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and read the text content of any URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web via DuckDuckGo and return results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cron_list",
            "description": "List current user crontab entries.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cron_add",
            "description": "Add a cron job to the user crontab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule": {"type": "string", "description": "Cron schedule (e.g. '0 9 * * *')"},
                    "command": {"type": "string"}
                },
                "required": ["schedule", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": "Open a URL in Jarvis's controlled Firefox browser window so the user can see the page. Use this to showcase search results, news, videos, documentation, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to open (must start with http:// or https://)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close a browser tab by its ID number, or pass 'all' to close all open tabs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "string", "description": "Tab ID number (e.g. '1') or 'all'"}
                },
                "required": ["tab_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_list_tabs",
            "description": "List all currently open tabs in the Jarvis browser with their IDs, titles, and URLs.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_content",
            "description": "Read the visible text content of an open browser tab. Useful to extract info from a page you opened.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "Tab ID from browser_list_tabs or browser_open"}
                },
                "required": ["tab_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate an already-open tab to a new URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer"},
                    "url": {"type": "string"}
                },
                "required": ["tab_id", "url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of an open browser tab and save it to disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer"},
                    "path": {"type": "string", "description": "Where to save the PNG (optional)"}
                },
                "required": ["tab_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Save something to Jarvis's long-term memory in Supabase so it persists across restarts. Use for user preferences, facts about the user, important events, or anything worth remembering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "What to remember"},
                    "type":    {"type": "string", "enum": ["fact", "preference", "event", "task"], "description": "Category of memory"},
                    "importance": {"type": "integer", "description": "1=low, 2=medium, 3=high importance"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search long-term memory for facts, preferences, or events relevant to the current conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for in memory"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "List all stored long-term memories.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Delete a specific memory by its ID number.",
            "parameters": {
                "type": "object",
                "properties": {"memory_id": {"type": "integer"}},
                "required": ["memory_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_topic",
            "description": "Add a topic to the sidebar so it's tracked and visible. Use proactively when a new subject comes up.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_topic",
            "description": "Remove a topic from the sidebar by ID when it's resolved or no longer relevant.",
            "parameters": {
                "type": "object",
                "properties": {"topic_id": {"type": "integer"}},
                "required": ["topic_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_active_topic",
            "description": "Set a topic as the active focus (pass 0 to clear). Affects what Jarvis concentrates on.",
            "parameters": {
                "type": "object",
                "properties": {"topic_id": {"type": "integer"}},
                "required": ["topic_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_topics",
            "description": "List all current topics in the sidebar.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_concept",
            "description": "Push a concept or live insight to the right sidebar panel so the user can see it. Use for system alerts, findings, observations, or anything surfaced from data on this machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":        {"type": "string"},
                    "category":    {"type": "string", "enum": ["info", "warning", "system", "network", "idea"]},
                    "ttl_minutes": {"type": "integer", "description": "How long to show it (default 60)"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_concept",
            "description": "Remove a concept from the sidebar by ID.",
            "parameters": {
                "type": "object",
                "properties": {"concept_id": {"type": "integer"}},
                "required": ["concept_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_add_host",
            "description": "Add a Tailscale machine for persistent SSH monitoring. Jarvis will keep a live SSH connection and notify on failure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string"},
                    "ip":       {"type": "string", "description": "Tailscale IP (100.x.x.x)"},
                    "username": {"type": "string", "description": "SSH username (default: root)"},
                    "port":     {"type": "integer", "description": "SSH port (default: 22)"},
                    "key_path": {"type": "string", "description": "Path to SSH private key"},
                    "password": {"type": "string", "description": "SSH password if no key"}
                },
                "required": ["hostname", "ip"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_remove_host",
            "description": "Remove a host from SSH monitoring.",
            "parameters": {
                "type": "object",
                "properties": {"hostname": {"type": "string"}},
                "required": ["hostname"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_list_hosts",
            "description": "List all configured SSH hosts and their connection status.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_get_metrics",
            "description": "Get live CPU, RAM, disk, load, and uptime from a specific host via SSH.",
            "parameters": {
                "type": "object",
                "properties": {"hostname": {"type": "string"}},
                "required": ["hostname"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_get_all_metrics",
            "description": "Get metrics from all configured SSH hosts at once.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_now_playing",
            "description": "Get the currently playing Spotify track (title, artist, play/pause status).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_play_pause",
            "description": "Toggle Spotify play/pause.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_next",
            "description": "Skip to the next Spotify track.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_previous",
            "description": "Go back to the previous Spotify track.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_stop",
            "description": "Stop Spotify playback.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_volume",
            "description": "Set Spotify playback volume (0–100).",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {"type": "integer", "description": "Volume level 0–100"}
                },
                "required": ["percent"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_search",
            "description": "Open Spotify app focused on a search query so the user can browse and pick a result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (song, artist, album, playlist)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_play",
            "description": "Search Spotify and immediately play the best matching track, artist, or playlist. Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET configured in .env.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to play — song name, artist, playlist"},
                    "kind":  {"type": "string", "enum": ["track", "artist", "playlist"], "description": "Type of result (default: track)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_run_command",
            "description": "Run any shell command on a remote machine via SSH.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hostname": {"type": "string"},
                    "command":  {"type": "string"}
                },
                "required": ["hostname", "command"]
            }
        }
    },
]
