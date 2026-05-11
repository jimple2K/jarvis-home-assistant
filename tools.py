import os
import subprocess
import shutil
import glob
import psutil
import socket
import platform
import datetime
import base64
import urllib.request
import urllib.error


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
    # Use DuckDuckGo lite (text-only, no JS)
    import urllib.parse
    url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
    return web_fetch(url, max_chars=5000)


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


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "bash":            bash,
    "read_file":       read_file,
    "write_file":      write_file,
    "append_file":     append_file,
    "list_directory":  list_directory,
    "search_files":    search_files,
    "delete_file":     delete_file,
    "move_file":       move_file,
    "copy_file":       copy_file,
    "get_system_info": get_system_info,
    "list_processes":  list_processes,
    "kill_process":    kill_process,
    "get_network_info":get_network_info,
    "notify":          notify,
    "screenshot":      screenshot,
    "get_clipboard":   get_clipboard,
    "set_clipboard":   set_clipboard,
    "open_application":open_application,
    "web_fetch":       web_fetch,
    "web_search":      web_search,
    "cron_list":       cron_list,
    "cron_add":        cron_add,
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
]
