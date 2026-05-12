"""
github_tools.py — single-token GitHub integration for Jarvis.

Why this layout:
  • One Personal Access Token in .env (GITHUB_TOKEN) drives everything: REST
    API calls AND HTTPS git operations. No per-repo SSH keys, no flaky agents.
  • For users who want SSH for git, `gh_setup_ssh_key()` generates an ED25519
    key, uploads its public half via the API, and writes ~/.ssh/config so
    `git@github.com` "just works".
  • All exported tool functions return human-readable strings so they slot
    into Jarvis's existing TOOL_FUNCTIONS map without special-casing.

Token scopes recommended:
  - repo                 (read+write private repos, clone via HTTPS, push)
  - read:user, user:email
  - gist
  - workflow             (optional — needed to push files that touch .github/workflows)
  - admin:public_key     (optional — only if you want gh_setup_ssh_key())

The token lives in .env as GITHUB_TOKEN. The cached username lives as
GITHUB_USERNAME (auto-populated after the first valid status call).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import time
from typing import Any
from urllib.parse import quote

import requests
from dotenv import set_key

API = "https://api.github.com"
TIMEOUT = 12

# ──────────────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────────────


def _env_path() -> str:
    return os.path.join(os.path.dirname(__file__), ".env")


def _token() -> str:
    return (os.getenv("GITHUB_TOKEN") or "").strip()


def _user() -> str:
    return (os.getenv("GITHUB_USERNAME") or "").strip()


def _headers(extra: dict | None = None) -> dict:
    tok = _token()
    h = {
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           "jarvis-home-assistant",
    }
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    if extra:
        h.update(extra)
    return h


def _api(method: str, path: str, **kw) -> requests.Response:
    """Authenticated GitHub REST call. `path` starts with '/' or is absolute."""
    url = path if path.startswith("http") else f"{API}{path}"
    kw.setdefault("timeout", TIMEOUT)
    h = kw.pop("headers", None)
    return requests.request(method, url, headers=_headers(h), **kw)


def _save_username(login: str) -> None:
    try:
        set_key(_env_path(), "GITHUB_USERNAME", login)
        os.environ["GITHUB_USERNAME"] = login
    except Exception:
        pass


def _run(cmd, cwd: str | None = None, timeout: int = 60,
         input_: str | None = None, env_extra: dict | None = None) -> dict:
    """Run a subprocess (no shell). Returns {ok, code, stdout, stderr}."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd or os.path.expanduser("~"),
            input=input_, env=env,
        )
        return {
            "ok":     result.returncode == 0,
            "code":   result.returncode,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": 124, "stdout": "", "stderr": f"Timed out after {timeout}s"}
    except FileNotFoundError as e:
        return {"ok": False, "code": 127, "stdout": "", "stderr": f"Not found: {e}"}
    except Exception as e:
        return {"ok": False, "code": 1, "stdout": "", "stderr": str(e)}


def _parse_repo(repo: str) -> tuple[str, str]:
    """Accept 'owner/repo', 'repo' (assumes current user), or a github URL."""
    repo = (repo or "").strip()
    m = re.match(r"(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/.\s]+)(?:\.git)?$", repo)
    if m:
        return m.group(1), m.group(2)
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return owner.strip(), name.split("/")[0].strip()
    user = _user()
    if not user:
        raise ValueError("repo must be 'owner/name' (no GitHub username cached yet).")
    return user, repo


def _format_repo(r: dict) -> str:
    name = r.get("full_name") or r.get("name")
    desc = (r.get("description") or "").strip()
    priv = "private" if r.get("private") else "public"
    lang = r.get("language") or "—"
    stars = r.get("stargazers_count", 0)
    line = f"{name} · {priv} · {lang} · ★{stars}"
    if desc:
        line += f" — {desc}"
    return line


# ──────────────────────────────────────────────────────────────────────────────
# Status & setup
# ──────────────────────────────────────────────────────────────────────────────


def gh_status() -> dict:
    """Validate the configured token. Returns a dict for API endpoints.

    Tool-function alias `github_status()` calls this and stringifies it.
    """
    tok = _token()
    if not tok:
        return {
            "ok": False, "configured": False,
            "message": "No GitHub token configured. Open Settings → GitHub.",
        }
    try:
        r = _api("GET", "/user")
    except requests.RequestException as e:
        return {"ok": False, "configured": True, "error": str(e)}
    if r.status_code == 200:
        u = r.json()
        login = u.get("login") or ""
        if login and login != _user():
            _save_username(login)
        # Pull rate-limit headers (cheap, no extra round-trip).
        rl_remaining = r.headers.get("X-RateLimit-Remaining")
        rl_limit     = r.headers.get("X-RateLimit-Limit")
        rl_reset     = r.headers.get("X-RateLimit-Reset")
        # Token scopes are returned in X-OAuth-Scopes.
        scopes = (r.headers.get("X-OAuth-Scopes") or "").split(",")
        scopes = [s.strip() for s in scopes if s.strip()]
        return {
            "ok": True, "configured": True,
            "login":     login,
            "name":      u.get("name") or "",
            "email":     u.get("email") or "",
            "avatar":    u.get("avatar_url") or "",
            "public_repos": u.get("public_repos", 0),
            "private_repos": u.get("total_private_repos", 0),
            "scopes":    scopes,
            "rate_limit": {
                "limit":     int(rl_limit) if rl_limit else None,
                "remaining": int(rl_remaining) if rl_remaining else None,
                "reset":     int(rl_reset) if rl_reset else None,
            },
        }
    if r.status_code in (401, 403):
        return {
            "ok": False, "configured": True,
            "error": "Token is invalid or expired.",
            "status": r.status_code,
        }
    return {
        "ok": False, "configured": True,
        "error": f"HTTP {r.status_code}",
        "body": r.text[:300],
    }


def gh_configure_git_https() -> dict:
    """Configure `git` so HTTPS clones/pushes use the token automatically.

    Strategy: write the token into ~/.git-credentials and set the global
    credential helper to `store`. This is the simplest path that works
    without prompting for every git operation.
    """
    tok = _token()
    if not tok:
        return {"ok": False, "error": "No GitHub token configured."}

    # Fetch login if missing so we can write 'user:token@github.com'.
    login = _user()
    if not login:
        st = gh_status()
        if st.get("ok"):
            login = st.get("login") or ""
    user_for_url = login or "x-access-token"

    creds_path = os.path.expanduser("~/.git-credentials")
    try:
        existing = ""
        if os.path.exists(creds_path):
            with open(creds_path, "r", encoding="utf-8") as f:
                existing = f.read()
        # Strip any prior github.com line.
        kept = "\n".join(
            ln for ln in existing.splitlines()
            if "github.com" not in ln
        ).rstrip()
        new_line = f"https://{quote(user_for_url, safe='')}:{quote(tok, safe='')}@github.com"
        body = (kept + "\n" if kept else "") + new_line + "\n"
        with open(creds_path, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(creds_path, 0o600)
    except Exception as e:
        return {"ok": False, "error": f"Could not write ~/.git-credentials: {e}"}

    # Wire git globally — credential helper + a polite default identity (only
    # if missing) so commits via Jarvis don't fail with "Author identity unknown".
    _run(["git", "config", "--global", "credential.helper", "store"])
    _run(["git", "config", "--global", "url.https://github.com/.insteadOf", "git@github.com:"])
    # Set author identity if unset — derived from API.
    cur_name = _run(["git", "config", "--global", "user.name"]).get("stdout") or ""
    cur_mail = _run(["git", "config", "--global", "user.email"]).get("stdout") or ""
    info = gh_status()
    if info.get("ok"):
        if not cur_name and info.get("name"):
            _run(["git", "config", "--global", "user.name", info["name"]])
        if not cur_mail:
            email = info.get("email") or f"{info.get('login') or 'jarvis'}@users.noreply.github.com"
            _run(["git", "config", "--global", "user.email", email])

    return {"ok": True, "message": "git is now using the token for github.com HTTPS."}


def gh_setup_ssh_key(title: str | None = None) -> dict:
    """Generate an ED25519 key, upload its public half to GitHub, configure SSH.

    Idempotent: if a key with the same title already exists, we reuse it.
    """
    if not _token():
        return {"ok": False, "error": "No GitHub token configured."}

    home = os.path.expanduser("~")
    ssh_dir = os.path.join(home, ".ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    try:
        os.chmod(ssh_dir, 0o700)
    except Exception:
        pass

    key_path = os.path.join(ssh_dir, "jarvis_github_ed25519")
    pub_path = key_path + ".pub"

    if not os.path.exists(key_path):
        # Generate ed25519, no passphrase (Jarvis is unattended).
        host = socket.gethostname() or "jarvis"
        gen = _run([
            "ssh-keygen",
            "-t", "ed25519",
            "-N", "",                              # no passphrase
            "-C", f"jarvis@{host}",
            "-f", key_path,
        ], timeout=20)
        if not gen["ok"]:
            return {"ok": False, "error": f"ssh-keygen failed: {gen['stderr']}"}

    try:
        with open(pub_path, "r", encoding="utf-8") as f:
            public_key = f.read().strip()
    except Exception as e:
        return {"ok": False, "error": f"Could not read public key: {e}"}

    # Upload (or detect existing).
    chosen_title = title or f"Jarvis ({socket.gethostname() or 'local'})"
    try:
        r = _api("POST", "/user/keys", json={"title": chosen_title, "key": public_key})
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}
    uploaded = False
    if r.status_code in (200, 201):
        uploaded = True
    elif r.status_code == 422:
        # Already exists (probably a duplicate) — that's fine.
        uploaded = False
    else:
        return {
            "ok": False,
            "error": f"GitHub /user/keys returned {r.status_code}: {r.text[:200]}",
        }

    # Wire ~/.ssh/config so `git@github.com` uses this key.
    config_path = os.path.join(ssh_dir, "config")
    block = (
        "# >>> jarvis github >>>\n"
        "Host github.com\n"
        "  HostName github.com\n"
        "  User git\n"
        f"  IdentityFile {key_path}\n"
        "  IdentitiesOnly yes\n"
        "# <<< jarvis github <<<\n"
    )
    try:
        existing = ""
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                existing = f.read()
        # Replace any prior jarvis block; otherwise append.
        if "# >>> jarvis github >>>" in existing:
            existing = re.sub(
                r"# >>> jarvis github >>>.*?# <<< jarvis github <<<\n",
                "", existing, flags=re.DOTALL,
            )
        body = existing.rstrip() + ("\n\n" if existing.strip() else "") + block
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(config_path, 0o600)
    except Exception as e:
        return {"ok": False, "error": f"Could not write ~/.ssh/config: {e}"}

    # Pre-trust GitHub's host key so the first `ssh -T` doesn't hang.
    known_hosts = os.path.join(ssh_dir, "known_hosts")
    try:
        if not os.path.exists(known_hosts) or "github.com" not in open(known_hosts).read():
            sk = _run(["ssh-keyscan", "-t", "ed25519,rsa", "github.com"], timeout=10)
            if sk["ok"] and sk["stdout"]:
                with open(known_hosts, "a", encoding="utf-8") as f:
                    f.write(("\n" if open(known_hosts).read()[-1:] != "\n" else "") + sk["stdout"] + "\n") if os.path.exists(known_hosts) else f.write(sk["stdout"] + "\n")
                os.chmod(known_hosts, 0o600)
    except Exception:
        pass

    return {
        "ok": True,
        "uploaded": uploaded,
        "title": chosen_title,
        "key_path": key_path,
        "public_key": public_key,
        "message": (
            "SSH key added to GitHub and SSH config wired."
            if uploaded
            else "SSH key was already present on GitHub — config refreshed."
        ),
    }


def gh_ssh_test() -> dict:
    """Run `ssh -T git@github.com` with strict-host-key-checking off (we
    pre-trusted in setup) and a short timeout, return parsed result."""
    res = _run([
        "ssh", "-T",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=8",
        "-o", "BatchMode=yes",
        "git@github.com",
    ], timeout=15)
    output = (res["stdout"] + ("\n" + res["stderr"] if res["stderr"] else "")).strip()
    # GitHub returns exit 1 even on success (it's "interactive shell denied").
    ok = "successfully authenticated" in output.lower()
    return {"ok": ok, "output": output, "code": res["code"]}


# ──────────────────────────────────────────────────────────────────────────────
# Repos / clone / git
# ──────────────────────────────────────────────────────────────────────────────


def gh_list_repos(limit: int = 20, affiliation: str = "owner,collaborator") -> str:
    if not _token():
        return "No GitHub token configured."
    try:
        r = _api("GET", "/user/repos", params={
            "per_page": min(100, max(1, int(limit))),
            "sort": "updated",
            "affiliation": affiliation,
        })
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = r.json() or []
    if not items:
        return "No repositories found."
    return "\n".join(_format_repo(i) for i in items[:limit])


def gh_get_repo(repo: str) -> str:
    try:
        owner, name = _parse_repo(repo)
    except ValueError as e:
        return str(e)
    try:
        r = _api("GET", f"/repos/{owner}/{name}")
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code == 404:
        return f"Repo {owner}/{name} not found (or no access)."
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    d = r.json()
    parts = [
        f"{d.get('full_name')}",
        f"  Description: {d.get('description') or '—'}",
        f"  Visibility:  {'private' if d.get('private') else 'public'}",
        f"  Default:     {d.get('default_branch')}",
        f"  Lang:        {d.get('language') or '—'}",
        f"  Stars/Forks: ★{d.get('stargazers_count', 0)} · {d.get('forks_count', 0)} forks",
        f"  Open issues: {d.get('open_issues_count', 0)}",
        f"  Clone HTTPS: {d.get('clone_url')}",
        f"  Clone SSH:   {d.get('ssh_url')}",
    ]
    return "\n".join(parts)


def gh_create_repo(name: str, private: bool = True, description: str = "",
                   auto_init: bool = True) -> str:
    if not name:
        return "name required"
    if not _token():
        return "No GitHub token configured."
    payload = {
        "name": name,
        "private": bool(private),
        "description": description or "",
        "auto_init": bool(auto_init),
    }
    try:
        r = _api("POST", "/user/repos", json=payload)
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code == 201:
        d = r.json()
        return f"Created {d.get('full_name')} ({d.get('html_url')})"
    return f"HTTP {r.status_code}: {r.text[:300]}"


def gh_clone(repo: str, dest: str = "", use_ssh: bool = False) -> str:
    """Clone a repo. Defaults to HTTPS-with-token (most reliable for Jarvis)."""
    try:
        owner, name = _parse_repo(repo)
    except ValueError as e:
        return str(e)
    dest = os.path.expanduser(dest) if dest else os.path.expanduser(f"~/{name}")
    if os.path.exists(dest) and os.listdir(dest):
        return f"Destination {dest} already exists and is not empty."

    tok = _token()
    if use_ssh:
        url = f"git@github.com:{owner}/{name}.git"
    elif tok:
        url = f"https://{quote(_user() or 'x-access-token', safe='')}:{quote(tok, safe='')}@github.com/{owner}/{name}.git"
    else:
        url = f"https://github.com/{owner}/{name}.git"

    res = _run(["git", "clone", "--depth", "1", url, dest], timeout=120)
    if res["ok"]:
        return f"Cloned {owner}/{name} → {dest}"
    # Avoid leaking the token in stderr.
    err = res["stderr"].replace(tok, "***") if tok else res["stderr"]
    return f"git clone failed: {err}"


# ──────────────────────────────────────────────────────────────────────────────
# Issues, PRs, gists, search
# ──────────────────────────────────────────────────────────────────────────────


def gh_list_issues(repo: str, state: str = "open", limit: int = 10) -> str:
    try:
        owner, name = _parse_repo(repo)
    except ValueError as e:
        return str(e)
    try:
        r = _api("GET", f"/repos/{owner}/{name}/issues", params={"state": state, "per_page": min(50, limit)})
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = [i for i in r.json() if "pull_request" not in i][:limit]
    if not items:
        return f"No {state} issues in {owner}/{name}."
    return "\n".join(
        f"#{i['number']} · {i['state']} · {i.get('user', {}).get('login', '?')} — {i['title']}"
        for i in items
    )


def gh_create_issue(repo: str, title: str, body: str = "") -> str:
    if not title:
        return "title required"
    try:
        owner, name = _parse_repo(repo)
    except ValueError as e:
        return str(e)
    try:
        r = _api("POST", f"/repos/{owner}/{name}/issues", json={"title": title, "body": body})
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code == 201:
        d = r.json()
        return f"Issue #{d['number']} created: {d['html_url']}"
    return f"HTTP {r.status_code}: {r.text[:300]}"


def gh_list_prs(repo: str, state: str = "open", limit: int = 10) -> str:
    try:
        owner, name = _parse_repo(repo)
    except ValueError as e:
        return str(e)
    try:
        r = _api("GET", f"/repos/{owner}/{name}/pulls", params={"state": state, "per_page": min(50, limit)})
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = (r.json() or [])[:limit]
    if not items:
        return f"No {state} PRs in {owner}/{name}."
    return "\n".join(
        f"#{p['number']} · {p['state']} · {p['user']['login']} → {p['base']['ref']} ← {p['head']['ref']} — {p['title']}"
        for p in items
    )


def gh_create_gist(filename: str, content: str, description: str = "", public: bool = False) -> str:
    if not filename or not content:
        return "filename and content required"
    payload = {
        "description": description,
        "public": bool(public),
        "files": {filename: {"content": content}},
    }
    try:
        r = _api("POST", "/gists", json=payload)
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code == 201:
        d = r.json()
        return f"Gist created: {d['html_url']}"
    return f"HTTP {r.status_code}: {r.text[:300]}"


def gh_search_repos(query: str, sort: str = "stars", limit: int = 10) -> str:
    if not query.strip():
        return "query required"
    try:
        r = _api("GET", "/search/repositories", params={
            "q": query, "sort": sort, "order": "desc", "per_page": min(30, limit),
        })
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = (r.json().get("items") or [])[:limit]
    if not items:
        return f"No repos match {query!r}."
    return "\n".join(_format_repo(i) for i in items)


def gh_search_code(query: str, limit: int = 10) -> str:
    """Code search — only available to authenticated users with `repo` scope.
    NB: GitHub limits this to the user's repos unless `user:` / `org:` is in q.
    """
    if not query.strip():
        return "query required"
    try:
        r = _api("GET", "/search/code", params={"q": query, "per_page": min(30, limit)})
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = (r.json().get("items") or [])[:limit]
    if not items:
        return f"No code matches {query!r}."
    out = []
    for i in items:
        out.append(f"{i['repository']['full_name']} · {i['path']}")
    return "\n".join(out)


def gh_notifications(limit: int = 10) -> str:
    try:
        r = _api("GET", "/notifications", params={"per_page": min(30, limit)})
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = (r.json() or [])[:limit]
    if not items:
        return "No unread notifications."
    out = []
    for n in items:
        sub = n.get("subject") or {}
        repo = (n.get("repository") or {}).get("full_name", "?")
        out.append(f"{n.get('reason', '?'):<13} {repo} — {sub.get('type', '?')} — {sub.get('title', '')}")
    return "\n".join(out)


def gh_recent_activity(limit: int = 10) -> str:
    login = _user()
    if not login:
        st = gh_status()
        if not st.get("ok"):
            return st.get("error") or st.get("message", "Not configured.")
        login = st.get("login") or ""
    try:
        r = _api("GET", f"/users/{login}/events", params={"per_page": min(30, limit)})
    except requests.RequestException as e:
        return f"Error: {e}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    items = (r.json() or [])[:limit]
    if not items:
        return "No recent activity."
    out = []
    for e in items:
        et = e.get("type", "?").replace("Event", "")
        repo = (e.get("repo") or {}).get("name", "?")
        payload = e.get("payload") or {}
        detail = ""
        if et == "Push":
            commits = payload.get("commits") or []
            detail = f" — {len(commits)} commit(s)"
            if commits:
                first = commits[0].get("message", "").split("\n")[0][:60]
                detail += f": {first}"
        elif et == "PullRequest":
            pr = payload.get("pull_request") or {}
            detail = f" — #{pr.get('number')} {pr.get('title','')[:60]}"
        elif et == "Issues":
            iss = payload.get("issue") or {}
            detail = f" — #{iss.get('number')} {iss.get('title','')[:60]}"
        elif et == "Create" or et == "Delete":
            detail = f" — {payload.get('ref_type', '')} {payload.get('ref') or ''}"
        out.append(f"{et:<14} {repo}{detail}")
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────────────────────
# Local git helpers (path-aware)
# ──────────────────────────────────────────────────────────────────────────────


def git_status(path: str = ".") -> str:
    path = os.path.expanduser(path)
    if not os.path.isdir(os.path.join(path, ".git")) and not _run(["git", "-C", path, "rev-parse"], timeout=5)["ok"]:
        return f"Not a git repo: {path}"
    res = _run(["git", "-C", path, "status", "--short", "--branch"], timeout=15)
    return res["stdout"] or res["stderr"] or "(clean working tree)"


def git_pull(path: str = ".") -> str:
    path = os.path.expanduser(path)
    res = _run(["git", "-C", path, "pull", "--ff-only"], timeout=90)
    if res["ok"]:
        return res["stdout"] or "Already up to date."
    return res["stderr"] or res["stdout"] or "Pull failed."


def git_commit_push(path: str, message: str, branch: str = "") -> str:
    """Stage + commit everything in `path`, then push to `branch` (or current)."""
    path = os.path.expanduser(path)
    if not _run(["git", "-C", path, "rev-parse"], timeout=5)["ok"]:
        return f"Not a git repo: {path}"
    if not message.strip():
        return "commit message required"

    add = _run(["git", "-C", path, "add", "-A"], timeout=30)
    if not add["ok"]:
        return f"git add failed: {add['stderr']}"

    # Skip the commit if there are no staged changes.
    diff = _run(["git", "-C", path, "diff", "--cached", "--name-only"], timeout=10)
    if not diff["stdout"]:
        return "Nothing to commit."

    cm = _run(["git", "-C", path, "commit", "-m", message], timeout=30)
    if not cm["ok"]:
        return f"git commit failed: {cm['stderr']}"

    push_cmd = ["git", "-C", path, "push"]
    if branch:
        push_cmd += ["origin", branch]
    push = _run(push_cmd, timeout=120)
    if push["ok"]:
        return cm["stdout"] + "\n" + push["stdout"]
    return cm["stdout"] + "\n" + (push["stderr"] or "push failed")


def git_log(path: str = ".", limit: int = 10) -> str:
    path = os.path.expanduser(path)
    res = _run(
        ["git", "-C", path, "log",
         f"-n{int(limit)}",
         "--pretty=format:%h · %an · %ar · %s"],
        timeout=15,
    )
    return res["stdout"] or res["stderr"] or "(no commits)"


def git_branch_list(path: str = ".") -> str:
    path = os.path.expanduser(path)
    res = _run(["git", "-C", path, "branch", "-vv"], timeout=10)
    return res["stdout"] or res["stderr"] or "(no branches)"


def git_create_branch(path: str, branch: str) -> str:
    path = os.path.expanduser(path)
    if not branch.strip():
        return "branch name required"
    res = _run(["git", "-C", path, "checkout", "-b", branch.strip()], timeout=15)
    return res["stdout"] or res["stderr"]


def git_checkout(path: str, ref: str) -> str:
    path = os.path.expanduser(path)
    res = _run(["git", "-C", path, "checkout", ref], timeout=20)
    return res["stdout"] or res["stderr"]
