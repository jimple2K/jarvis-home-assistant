"""
Persistent SSH connection pool for Tailscale machines.
Each enabled host gets a background thread that keeps one SSH connection alive.
On failure: desktop notification + concept added to sidebar.
On recovery: notification + sidebar updated.
Metrics collected over the live connection every 60s.
"""
import paramiko
import json
import os
import subprocess
import threading
import time
import socket
from db import _conn, _lock

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS ssh_hosts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname    TEXT NOT NULL UNIQUE,
    ip          TEXT NOT NULL,
    port        INTEGER DEFAULT 22,
    username    TEXT DEFAULT 'root',
    key_path    TEXT DEFAULT '',
    password    TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    last_seen   TEXT,
    last_error  TEXT
);
CREATE TABLE IF NOT EXISTS host_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id      INTEGER NOT NULL,
    cpu_pct      REAL,
    mem_pct      REAL,
    disk_pct     REAL,
    load_1m      REAL,
    uptime_s     INTEGER,
    os_info      TEXT,
    raw          TEXT,
    collected_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(host_id) REFERENCES ssh_hosts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS hm_host_idx ON host_metrics(host_id, collected_at DESC);
"""

def init_schema():
    with _lock, _conn() as c:
        c.executescript(SCHEMA)


# ── In-memory connection pool ─────────────────────────────────────────────────

class _HostState:
    def __init__(self):
        self.client:     paramiko.SSHClient | None = None
        self.connected:  bool   = False
        self.last_error: str    = ""
        self.lock:       threading.Lock = threading.Lock()
        self.thread:     threading.Thread | None = None
        self.stop_evt:   threading.Event = threading.Event()

_pool: dict[str, _HostState] = {}
_pool_lock = threading.Lock()


# ── Notification helpers ──────────────────────────────────────────────────────

def _notify(title: str, message: str, urgency: str = "normal"):
    try:
        subprocess.Popen(["notify-send", "-u", urgency, title, message])
    except Exception:
        pass


def _set_concept(hostname: str, text: str, category: str = "network", ttl: int = 120):
    try:
        from db import add_concept
        add_concept(text, category=category, ttl_minutes=ttl)
    except Exception:
        pass


# ── SSH connect logic ─────────────────────────────────────────────────────────

def _make_client(host: dict) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    kwargs = dict(
        hostname=host["ip"],
        port=int(host["port"]),
        username=host["username"],
        timeout=10,
        banner_timeout=15,
        auth_timeout=15,
    )

    key_path = (host.get("key_path") or "").strip()
    if not key_path:
        for candidate in ["~/.ssh/id_ed25519", "~/.ssh/id_rsa", "~/.ssh/id_ecdsa"]:
            p = os.path.expanduser(candidate)
            if os.path.exists(p):
                key_path = p
                break

    if key_path:
        try:
            client.connect(**kwargs, key_filename=os.path.expanduser(key_path))
            return client
        except Exception:
            pass

    if host.get("password"):
        client.connect(**kwargs, password=host["password"])
        return client

    client.connect(**kwargs)
    return client


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 15) -> str:
    _, stdout, _ = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace").strip()


# ── Metrics script (pure /proc, no dependencies) ──────────────────────────────

_METRICS_CMD = r"""python3 -c "
import json,os,time
def r(f):
    try:
        with open(f) as fh: return fh.read()
    except: return ''
la   = r('/proc/loadavg').split(); load1=float(la[0]) if la else -1
up   = r('/proc/uptime').split(); uptime=int(float(up[0])) if up else -1
mem  = {}
for l in r('/proc/meminfo').splitlines():
    p=l.split(':')
    if len(p)==2: mem[p[0].strip()]=int(p[1].strip().split()[0])
mem_pct=round(100*(mem.get('MemTotal',0)-mem.get('MemAvailable',mem.get('MemFree',0)))/max(mem.get('MemTotal',1),1),1)
s=os.statvfs('/'); disk_pct=round(100*(s.f_blocks-s.f_bfree)/max(s.f_blocks,1),1)
c1=r('/proc/stat').splitlines()[0].split(); time.sleep(0.3); c2=r('/proc/stat').splitlines()[0].split()
i1,t1=int(c1[4]),sum(int(x) for x in c1[1:]); i2,t2=int(c2[4]),sum(int(x) for x in c2[1:])
cpu=round(100*(1-(i2-i1)/max(t2-t1,1)),1)
kv={l.split('=')[0]:l.split('=')[1].strip('\"') for l in r('/etc/os-release').splitlines() if '=' in l}
print(json.dumps({'cpu':cpu,'mem':mem_pct,'disk':disk_pct,'load1':load1,'uptime':uptime,'os':kv.get('PRETTY_NAME','Linux')}))
" 2>/dev/null || echo '{}'
"""


def _collect_over_connection(state: _HostState, host: dict):
    try:
        raw  = _run(state.client, _METRICS_CMD, timeout=20)
        data = json.loads(raw) if raw.strip().startswith("{") else {}
        if not data:
            return
        with _lock, _conn() as c:
            c.execute("""
                INSERT INTO host_metrics (host_id,cpu_pct,mem_pct,disk_pct,load_1m,uptime_s,os_info,raw)
                VALUES (?,?,?,?,?,?,?,?)
            """, (host["id"], data.get("cpu"), data.get("mem"), data.get("disk"),
                  data.get("load1"), data.get("uptime"), data.get("os"), raw))
            c.execute("UPDATE ssh_hosts SET last_seen=datetime('now'), last_error='' WHERE id=?", (host["id"],))

        # Push warning concepts
        cpu, mem, disk = data.get("cpu",-1), data.get("mem",-1), data.get("disk",-1)
        hn = host["hostname"]
        if cpu  > 85: _set_concept(hn, f"⚠ {hn}: High CPU {cpu}%",  "warning", 10)
        if mem  > 90: _set_concept(hn, f"⚠ {hn}: RAM critical {mem}%", "warning", 10)
        if disk > 90: _set_concept(hn, f"⚠ {hn}: Disk full {disk}%", "warning", 30)

    except Exception:
        raise  # bubble up so the monitor loop sees the failure


# ── Per-host monitor thread ───────────────────────────────────────────────────

RECONNECT_BASE  = 5    # seconds before first retry
RECONNECT_MAX   = 120  # cap backoff at 2 minutes
METRIC_INTERVAL = 60   # collect metrics every N seconds


def _monitor(hostname: str):
    state = _pool[hostname]
    was_connected = False
    backoff = RECONNECT_BASE
    last_metric = 0.0

    while not state.stop_evt.is_set():
        host = get_host(hostname)
        if not host or not host["enabled"]:
            state.stop_evt.wait(10)
            continue

        # ── Try to connect / keep alive ──
        with state.lock:
            need_connect = state.client is None or not _is_alive(state.client)

        if need_connect:
            if was_connected:
                # Machine just dropped
                state.connected = False
                state.last_error = "Connection lost"
                _notify(f"Jarvis — {hostname} offline",
                        f"{hostname} ({host['ip']}) lost SSH connection.",
                        urgency="critical")
                _set_concept(hostname, f"✗ {hostname} — SSH lost", "warning", 60)
                with _lock, _conn() as c:
                    c.execute("UPDATE ssh_hosts SET last_error='Connection lost' WHERE id=?", (host["id"],))
                was_connected = False

            # Attempt reconnect
            try:
                client = _make_client(host)
                # Enable keepalive so the transport stays warm
                transport = client.get_transport()
                transport.set_keepalive(30)
                with state.lock:
                    state.client    = client
                    state.connected = True
                    state.last_error = ""
                backoff = RECONNECT_BASE

                if not was_connected:
                    # First connect or recovery
                    _notify(f"Jarvis — {hostname} online",
                            f"{hostname} ({host['ip']}) SSH connected.",
                            urgency="normal")
                    _set_concept(hostname, f"✓ {hostname} — SSH live", "network", 120)
                    with _lock, _conn() as c:
                        c.execute("UPDATE ssh_hosts SET last_seen=datetime('now'), last_error='' WHERE id=?",
                                  (host["id"],))
                was_connected = True

            except Exception as e:
                state.connected  = False
                state.last_error = str(e)
                with _lock, _conn() as c:
                    c.execute("UPDATE ssh_hosts SET last_error=? WHERE id=?", (str(e), host["id"]))
                # Wait with exponential backoff
                state.stop_evt.wait(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX)
                continue

        # ── Collect metrics periodically ──
        now = time.monotonic()
        if state.connected and (now - last_metric) >= METRIC_INTERVAL:
            try:
                _collect_over_connection(state, host)
                last_metric = now
            except Exception:
                # Force reconnect on next loop
                with state.lock:
                    try: state.client.close()
                    except: pass
                    state.client = None

        state.stop_evt.wait(5)  # check every 5s


def _is_alive(client: paramiko.SSHClient) -> bool:
    try:
        t = client.get_transport()
        return t is not None and t.is_active()
    except Exception:
        return False


# ── Pool management ───────────────────────────────────────────────────────────

def _start_monitor(hostname: str):
    with _pool_lock:
        if hostname in _pool and _pool[hostname].thread and _pool[hostname].thread.is_alive():
            return
        state = _HostState()
        _pool[hostname] = state
        t = threading.Thread(target=_monitor, args=(hostname,), daemon=True, name=f"ssh-{hostname}")
        state.thread = t
        t.start()


def _stop_monitor(hostname: str):
    with _pool_lock:
        if hostname in _pool:
            _pool[hostname].stop_evt.set()
            try: _pool[hostname].client.close()
            except: pass
            _pool.pop(hostname, None)


def start_all_monitors():
    """Called at app startup — starts monitor threads for all enabled hosts."""
    for host in list_hosts():
        if host["enabled"]:
            _start_monitor(host["hostname"])


# ── Host management ───────────────────────────────────────────────────────────

def add_host(hostname: str, ip: str, username: str = "root",
             port: int = 22, key_path: str = "", password: str = "") -> str:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO ssh_hosts (hostname, ip, port, username, key_path, password)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(hostname) DO UPDATE SET
              ip=excluded.ip, port=excluded.port,
              username=excluded.username, key_path=excluded.key_path,
              password=excluded.password, enabled=1
        """, (hostname, ip, port, username, key_path, password))
    _start_monitor(hostname)
    return f"SSH monitoring started: {username}@{hostname} ({ip}:{port})"


def remove_host(hostname: str) -> str:
    _stop_monitor(hostname)
    with _lock, _conn() as c:
        c.execute("DELETE FROM ssh_hosts WHERE hostname=?", (hostname,))
    return f"Removed and disconnected: {hostname}"


def list_hosts() -> list:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT id, hostname, ip, port, username, enabled, last_seen, last_error FROM ssh_hosts"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        state = _pool.get(d["hostname"])
        d["live"]      = state.connected if state else False
        d["last_error"] = state.last_error if (state and state.last_error) else d.get("last_error", "")
        result.append(d)
    return result


def get_host(hostname: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT * FROM ssh_hosts WHERE hostname=? OR ip=?", (hostname, hostname)
        ).fetchone()
    return dict(row) if row else None


# ── On-demand metrics / commands (uses pool connection if live) ───────────────

def collect_metrics(hostname: str) -> dict:
    host = get_host(hostname)
    if not host:
        return {"error": f"No SSH config for {hostname}"}

    state = _pool.get(hostname)

    # Use existing live connection if available, else one-shot connect
    client = None
    own_client = False
    if state and state.connected and _is_alive(state.client):
        client = state.client
    else:
        try:
            client = _make_client(host)
            own_client = True
        except Exception as e:
            return {"error": str(e), "hostname": hostname}

    try:
        raw  = _run(client, _METRICS_CMD, timeout=20)
        data = json.loads(raw) if raw.strip().startswith("{") else {}
        if not data:
            return {"error": "Empty response", "hostname": hostname}

        with _lock, _conn() as c:
            c.execute("""
                INSERT INTO host_metrics (host_id,cpu_pct,mem_pct,disk_pct,load_1m,uptime_s,os_info,raw)
                VALUES (?,?,?,?,?,?,?,?)
            """, (host["id"], data.get("cpu"), data.get("mem"), data.get("disk"),
                  data.get("load1"), data.get("uptime"), data.get("os"), raw))
            c.execute("UPDATE ssh_hosts SET last_seen=datetime('now'), last_error='' WHERE id=?", (host["id"],))

        return {
            "hostname": hostname,
            "cpu_pct":  data.get("cpu",  -1),
            "mem_pct":  data.get("mem",  -1),
            "disk_pct": data.get("disk", -1),
            "load_1m":  data.get("load1",-1),
            "uptime_s": data.get("uptime",-1),
            "os":       data.get("os", ""),
        }
    finally:
        if own_client:
            try: client.close()
            except: pass


def run_remote(hostname: str, command: str) -> str:
    host  = get_host(hostname)
    if not host:
        return f"No SSH config for {hostname}"
    state = _pool.get(hostname)
    client = None
    own_client = False
    if state and state.connected and _is_alive(state.client):
        client = state.client
    else:
        try:
            client = _make_client(host)
            own_client = True
        except Exception as e:
            return f"SSH error: {e}"
    try:
        return _run(client, command, timeout=30) or "(no output)"
    finally:
        if own_client:
            try: client.close()
            except: pass


def get_recent_metrics(hostname: str) -> dict | None:
    host = get_host(hostname)
    if not host:
        return None
    with _lock, _conn() as c:
        row = c.execute("""
            SELECT cpu_pct, mem_pct, disk_pct, load_1m, uptime_s, os_info, collected_at
            FROM host_metrics WHERE host_id=? ORDER BY collected_at DESC LIMIT 1
        """, (host["id"],)).fetchone()
    if not row:
        return None
    d = dict(row)
    state = _pool.get(hostname)
    d["live"] = state.connected if state else False
    return d


def collect_all_metrics() -> list:
    hosts = [h for h in list_hosts() if h["enabled"]]
    results, lock = [], threading.Lock()
    threads = []
    for h in hosts:
        def worker(hn=h["hostname"]):
            r = collect_metrics(hn)
            with lock: results.append(r)
        t = threading.Thread(target=worker, daemon=True)
        threads.append(t); t.start()
    for t in threads: t.join(timeout=25)
    return results
