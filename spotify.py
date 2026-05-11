"""
Spotify control for Jarvis.

Tier 1 — MPRIS2 via dbus-send (works whenever the Spotify desktop app is running, no auth).
Tier 2 — Spotify Web API via spotipy (search & play by name; needs SPOTIFY_CLIENT_ID /
          SPOTIFY_CLIENT_SECRET in .env).
"""
import os
import re
import subprocess
import urllib.parse


# ── D-Bus constants ────────────────────────────────────────────────────────────

_DEST   = "org.mpris.MediaPlayer2.spotify"
_OBJ    = "/org/mpris/MediaPlayer2"
_PLAYER = "org.mpris.MediaPlayer2.Player"
_PROPS  = "org.freedesktop.DBus.Properties"


# ── Low-level D-Bus helpers ───────────────────────────────────────────────────

def _dbus_call(method: str, *args) -> tuple[str, str]:
    """Returns (stdout, error_string). error_string is '' on success."""
    cmd = ["dbus-send", "--print-reply", f"--dest={_DEST}", _OBJ, f"{_PLAYER}.{method}"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            err = r.stderr.strip()
            if "ServiceUnknown" in err or "NoReply" in err:
                return "", "Spotify is not running."
            return "", f"D-Bus error: {err}"
        return r.stdout, ""
    except FileNotFoundError:
        return "", "dbus-send not found — install dbus utilities."
    except subprocess.TimeoutExpired:
        return "", "D-Bus timed out."


def _dbus_get(prop: str) -> tuple[str, str]:
    cmd = [
        "dbus-send", "--print-reply", f"--dest={_DEST}", _OBJ,
        f"{_PROPS}.Get", f"string:{_PLAYER}", f"string:{prop}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            err = r.stderr.strip()
            if "ServiceUnknown" in err or "NoReply" in err:
                return "", "Spotify is not running."
            return "", err
        return r.stdout, ""
    except FileNotFoundError:
        return "", "dbus-send not found."
    except subprocess.TimeoutExpired:
        return "", "D-Bus timed out."


def _dbus_set(prop: str, variant_arg: str) -> str:
    cmd = [
        "dbus-send", "--print-reply", f"--dest={_DEST}", _OBJ,
        f"{_PROPS}.Set", f"string:{_PLAYER}", f"string:{prop}", variant_arg,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            err = r.stderr.strip()
            if "ServiceUnknown" in err:
                return "Spotify is not running."
            return f"D-Bus error: {err}"
        return ""
    except Exception as e:
        return str(e)


# ── Metadata parsing ──────────────────────────────────────────────────────────

def _extract_meta_field(raw: str, key: str) -> str:
    """Pull the first string value after a given xesam/mpris key."""
    pattern = rf'"{re.escape(key)}"\s+variant\s+(?:array\s*\[\s*)?string\s+"([^"]*)"'
    m = re.search(pattern, raw, re.DOTALL)
    return m.group(1) if m else ""


# ── Tier 1: MPRIS2 controls ───────────────────────────────────────────────────

def now_playing() -> dict:
    """
    Returns dict with keys: title, artist, status, running.
    'running' is False when Spotify isn't open.
    """
    meta_raw, err = _dbus_get("Metadata")
    if err:
        return {"running": False, "title": "", "artist": "", "status": ""}

    title  = _extract_meta_field(meta_raw, "xesam:title")
    artist = _extract_meta_field(meta_raw, "xesam:artist")

    status_raw, _ = _dbus_get("PlaybackStatus")
    status = ""
    m = re.search(r'string "(\w+)"', status_raw)
    if m:
        status = m.group(1)  # "Playing" | "Paused" | "Stopped"

    return {"running": True, "title": title, "artist": artist, "status": status}


def play_pause() -> str:
    _, err = _dbus_call("PlayPause")
    return err or "Toggled Spotify play/pause."


def next_track() -> str:
    _, err = _dbus_call("Next")
    return err or "Skipped to next track."


def previous_track() -> str:
    _, err = _dbus_call("Previous")
    return err or "Went to previous track."


def stop() -> str:
    _, err = _dbus_call("Stop")
    return err or "Spotify stopped."


def set_volume(percent: int) -> str:
    vol = max(0, min(100, int(percent))) / 100.0
    err = _dbus_set("Volume", f"variant:double:{vol:.4f}")
    return err or f"Spotify volume set to {percent}%."


def open_search(query: str) -> str:
    """Open Spotify app focused on a search — user picks and plays."""
    uri = f"spotify:search:{urllib.parse.quote(query)}"
    try:
        subprocess.Popen(["xdg-open", uri])
        return f"Opened Spotify search: {query}"
    except Exception as e:
        return f"Error opening Spotify: {e}"


# ── Tier 2: Spotify Web API (optional) ───────────────────────────────────────

def _sp_client():
    """Returns (spotipy.Spotify, None) or (None, error_string)."""
    cid     = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    secret  = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    redir   = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

    if not cid or not secret:
        return None, (
            "Spotify Web API not configured. "
            "Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env, "
            "then visit developer.spotify.com to create an app."
        )
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        scope = (
            "user-read-playback-state "
            "user-modify-playback-state "
            "user-read-currently-playing"
        )
        cache = os.path.join(os.path.dirname(__file__), ".spotify_token_cache")
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=cid,
            client_secret=secret,
            redirect_uri=redir,
            scope=scope,
            cache_path=cache,
            open_browser=False,
        ))
        return sp, None
    except ImportError:
        return None, "spotipy not installed — run: pip install spotipy"
    except Exception as e:
        return None, f"Spotify auth error: {e}"


def _active_device_id(sp) -> str | None:
    try:
        devs = sp.devices().get("devices", [])
        for d in devs:
            if d["is_active"]:
                return d["id"]
        return devs[0]["id"] if devs else None
    except Exception:
        return None


def search_and_play(query: str, kind: str = "track") -> str:
    """
    Search Spotify and immediately play the best result.
    kind: 'track' | 'artist' | 'playlist'
    Requires SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET in .env.
    """
    sp, err = _sp_client()
    if err:
        return err

    try:
        results = sp.search(q=query, type=kind, limit=1)
        dev_id  = _active_device_id(sp)

        if kind == "track":
            items = results.get("tracks", {}).get("items", [])
            if not items:
                return f"No tracks found for: {query}"
            t = items[0]
            sp.start_playback(device_id=dev_id, uris=[t["uri"]])
            artist = t["artists"][0]["name"] if t["artists"] else ""
            return f"Playing: {t['name']} by {artist}"

        elif kind == "artist":
            items = results.get("artists", {}).get("items", [])
            if not items:
                return f"No artist found for: {query}"
            a = items[0]
            sp.start_playback(device_id=dev_id, context_uri=a["uri"])
            return f"Playing artist: {a['name']}"

        elif kind == "playlist":
            items = results.get("playlists", {}).get("items", [])
            if not items:
                return f"No playlist found for: {query}"
            p = items[0]
            sp.start_playback(device_id=dev_id, context_uri=p["uri"])
            return f"Playing playlist: {p['name']}"

        return f"Unknown kind: {kind}"
    except Exception as e:
        return f"Spotify API error: {e}"
