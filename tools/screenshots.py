#!/usr/bin/env python3
"""Regenerate the README screenshots from invented demo data.

    .venv/bin/python tools/screenshots.py            # all scenes -> docs/screenshots/
    .venv/bin/python tools/screenshots.py hero       # one scene

Nothing here touches the network, the keyring or your real cache: every
scene runs in its own offscreen process against a throwaway database, with
an HTTP client whose transport refuses all requests.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
THEMES = Path(os.environ.get("OMARCHY_THEMES", "/usr/share/omarchy/themes"))

# name: (theme, width, height)
SCENES = {
    "hero": ("ristretto", 1600, 900),
    "theme-tokyo-night": ("tokyo-night", 1200, 740),
    "theme-latte": ("catppuccin-latte", 1200, 740),
    "details-traffic": ("ristretto", 1600, 900),
    "run-workflow": ("ristretto", 1600, 900),
    "bulk": ("ristretto", 1600, 900),
    "narrow": ("ristretto", 760, 900),
    "sign-in": ("ristretto", 960, 640),
}

NOW = time.time()
DAY = 86400


def iso(days_ago: float) -> str:
    return datetime.fromtimestamp(NOW - days_ago * DAY, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------- demo data
VIEWER = {"databaseId": 1001, "login": "mira-codes", "name": "Mira Lindqvist", "avatarUrl": "", "url": "https://github.com/mira-codes"}

# (name, owner, description, visibility, language, stars, forks, watchers, issues, prs,
#  pushed days ago, topics, license, extra)
REPOS = [
    ("hyprglow", "mira-codes", "Animated window borders and glow effects for Hyprland", "PUBLIC", "Rust", 1284, 61, 23, 14, 3, 0.1, ["hyprland", "wayland", "rust"], "MIT", {}),
    ("omarchy-weather", "mira-codes", "Weather chip and forecast panel for the Omarchy bar", "PUBLIC", "QML", 342, 18, 9, 4, 1, 0.8, ["omarchy", "qml", "weather"], "MIT", {}),
    ("dotfiles", "mira-codes", "My Arch + Hyprland setup, managed with chezmoi", "PUBLIC", "Shell", 97, 12, 4, 0, 0, 1.5, ["dotfiles", "arch-linux"], "MIT", {}),
    ("tinygrep", "mira-codes", "A tiny, fast grep with gitignore support", "PUBLIC", "Go", 611, 29, 14, 7, 2, 2.2, ["cli", "search", "go"], "Apache-2.0", {}),
    ("notes-sync", "mira-codes", "Encrypted markdown notes synced over Syncthing", "PRIVATE", "Python", 0, 0, 1, 2, 0, 3.0, ["notes", "encryption"], None, {}),
    ("pixel-forge", "mira-codes", "Pixel-art editor with onion skinning and palettes", "PUBLIC", "C++", 2210, 143, 57, 38, 9, 3.4, ["pixel-art", "editor", "qt"], "GPL-3.0", {}),
    ("portfolio", "mira-codes", "Personal site: projects, writing and talks", "PUBLIC", "TypeScript", 18, 3, 2, 0, 1, 5.0, ["astro", "website"], "MIT", {}),
    ("omarchy-pomodoro", "mira-codes", "Focus timer widget with session stats", "PUBLIC", "QML", 156, 7, 5, 3, 0, 6.0, ["omarchy", "productivity"], "MIT", {}),
    ("habit-loop", "mira-codes", "Android habit tracker with streaks and widgets", "PUBLIC", "Kotlin", 74, 6, 3, 5, 2, 9.0, ["android", "habits"], "MIT", {}),
    ("infra", "studio-north", "Terraform and Ansible for the studio's servers", "PRIVATE", "HCL", 0, 0, 3, 6, 4, 1.1, ["terraform", "ansible"], None, {"viewer_permission": "WRITE"}),
    ("design-tokens", "studio-north", "Shared color, type and spacing tokens", "INTERNAL", "JavaScript", 0, 0, 8, 1, 2, 4.2, ["design-system"], None, {"viewer_permission": "MAINTAIN"}),
    ("shader-lab", "mira-codes", "GLSL experiments and a live-reload playground", "PUBLIC", "GLSL", 431, 22, 11, 0, 0, 14.0, ["glsl", "graphics"], None, {}),
    ("wayland-screencap", "mira-codes", "Screen recording helper built on wf-recorder", "PUBLIC", "Rust", 205, 9, 6, 2, 1, 20.0, ["wayland", "recording"], "MIT", {}),
    ("rss-digest", "mira-codes", "Morning RSS digest emailed as a single page", "PUBLIC", "Python", 38, 2, 2, 1, 0, 34.0, ["rss", "email"], "MIT", {}),
    ("neovim-config", "mira-codes", "", "PUBLIC", "Lua", 52, 8, 2, 0, 0, 41.0, ["neovim"], "MIT", {"is_fork": True}),
    ("kbd-layouts", "mira-codes", "Custom keyboard layouts for Colemak-DH", "PUBLIC", "C", 19, 1, 1, 0, 0, 70.0, ["keyboard"], "MIT", {}),
    ("ci-templates", "studio-north", "Reusable GitHub Actions workflows", "PUBLIC", "YAML", 64, 11, 9, 2, 3, 12.0, ["github-actions", "ci"], "MIT", {"viewer_permission": "ADMIN"}),
    ("hackathon-2024", "mira-codes", "Weekend project: plant watering bot", "PUBLIC", "Python", 11, 0, 1, 0, 0, 380.0, ["iot"], None, {}),
    ("old-blog", "mira-codes", "Jekyll blog, replaced by portfolio", "PUBLIC", "HTML", 5, 1, 1, 0, 0, 900.0, ["jekyll"], "MIT", {"is_archived": True}),
    ("advent-of-code", "mira-codes", "Solutions in a different language each year", "PUBLIC", "Zig", 88, 4, 3, 0, 0, 280.0, ["advent-of-code"], "MIT", {}),
]

# node_id -> health signals the scenes should show
SIGNALS = {
    "pixel-forge": {"alerts": 2, "ci": "SUCCESS", "stale_prs": 3, "has_readme": True},
    "tinygrep": {"alerts": 0, "ci": "FAILURE", "stale_prs": 0, "has_readme": True},
    "infra": {"alerts": 0, "ci": "FAILURE", "stale_prs": 1, "has_readme": True},
    "shader-lab": {"alerts": 0, "ci": None, "stale_prs": 0, "has_readme": False},
    "habit-loop": {"alerts": 0, "ci": "SUCCESS", "stale_prs": 2, "has_readme": True},
}

RUNS = [
    ("CI", "completed", "success", "push", "main", 312, 0.05),
    ("Release", "in_progress", None, "workflow_dispatch", "main", 41, 0.02),
    ("CI", "completed", "failure", "pull_request", "fix/border-flicker", 311, 0.4),
    ("CI", "completed", "success", "push", "main", 310, 1.2),
    ("Nightly build", "completed", "success", "schedule", "main", 88, 1.9),
    ("CI", "completed", "cancelled", "pull_request", "feat/gradients", 309, 2.5),
]

DISPATCHABLES = [
    {"id": 7, "name": "Release", "path": ".github/workflows/release.yml", "state": "active", "inputs": [
        {"name": "version", "description": "Version to tag and publish, e.g. 1.4.0", "required": True, "type": "string", "default": "", "options": []},
        {"name": "channel", "description": "Where to publish the build", "required": True, "type": "choice", "default": "stable", "options": ["stable", "beta", "nightly"]},
        {"name": "draft", "description": "Create the GitHub release as a draft", "required": False, "type": "boolean", "default": "true", "options": []},
    ]},
    {"id": 8, "name": "Nightly build", "path": ".github/workflows/nightly.yml", "state": "active", "inputs": []},
]


def build_db(path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from repokase.api.health import compute_health
    from repokase.cache import db, store

    conn = db.connect(path)
    aid = store.save_account(conn, VIEWER)
    rows = []
    for i, (name, owner, desc, vis, lang, st, fk, wt, iss, prs, pushed, topics, lic, extra) in enumerate(REPOS):
        r = {
            "node_id": name, "database_id": 5000 + i, "owner": owner, "name": name,
            "full_name": f"{owner}/{name}", "description": desc or None,
            "url": f"https://github.com/{owner}/{name}", "visibility": vis,
            "is_archived": False, "is_fork": False, "is_template": False, "is_mirror": False,
            "primary_language": lang, "stargazers": st, "forks": fk, "watchers": wt,
            "open_issues": iss, "open_prs": prs, "default_branch": "main", "license_spdx": lic,
            "disk_kb": 900 + st * 3, "viewer_permission": "ADMIN",
            "pushed_at": iso(pushed), "created_at": iso(pushed + 400), "updated_at": iso(pushed),
            "topics": topics,
        }
        r.update(extra)
        rows.append(r)
    store.replace_repos(conn, aid, rows)
    store.mark_sync(conn, aid, "repos")

    health = {}
    for r in rows:
        sig = SIGNALS.get(r["node_id"], {"alerts": 0, "ci": "SUCCESS", "stale_prs": 0, "has_readme": True})
        health[r["node_id"]] = compute_health(r, sig, NOW)
    store.save_health(conn, aid, health, {k: SIGNALS.get(k) for k in health})

    cats = {name: store.create_category(conn, name) for name in ("Omarchy", "Tools", "Graphics", "Studio North")}
    assign = {
        "Omarchy": ["omarchy-weather", "omarchy-pomodoro", "hyprglow", "dotfiles"],
        "Tools": ["tinygrep", "wayland-screencap", "rss-digest", "kbd-layouts"],
        "Graphics": ["pixel-forge", "shader-lab", "hyprglow"],
        "Studio North": ["infra", "design-tokens", "ci-templates"],
    }
    for cat, repos in assign.items():
        for node in repos:
            store.set_repo_category(conn, aid, node, cats[cat], True)

    store.replace_workflow_runs(conn, aid, "hyprglow", [
        {"id": 90000 + n, "workflow_id": 1, "name": name, "status": status, "conclusion": concl, "event": event,
         "head_branch": branch, "run_number": num, "created_at": iso(ago), "html_url": "https://github.com/"}
        for n, (name, status, concl, event, branch, num, ago) in enumerate(RUNS)
    ])

    # 75 days of traffic with a launch spike ~3 weeks ago.
    rnd = random.Random(7)
    today = datetime.now(UTC).date()
    views, clones = [], []
    for d in range(75, -1, -1):
        day = (today - timedelta(days=d)).isoformat()
        base = 40 + 25 * (1 - d / 75)
        spike = 380 * max(0, 1 - abs(d - 22) / 4)
        v = int(base + spike + rnd.randint(-12, 14))
        views.append({"day": day, "count": v, "uniques": int(v * 0.42)})
        c = int(6 + spike * 0.09 + rnd.randint(0, 5))
        clones.append({"day": day, "count": c, "uniques": max(1, int(c * 0.6))})
    store.save_traffic(conn, "mira-codes/hyprglow", "views", views)
    store.save_traffic(conn, "mira-codes/hyprglow", "clones", clones)
    store.save_referrers(conn, "mira-codes/hyprglow", today.isoformat(), [
        {"referrer": "news.ycombinator.com", "count": 812, "uniques": 640},
        {"referrer": "github.com", "count": 233, "uniques": 120},
        {"referrer": "reddit.com", "count": 190, "uniques": 151},
        {"referrer": "omarchy.org", "count": 64, "uniques": 51},
    ])
    store.mark_sync(conn, aid, "traffic")
    store.set_setting(conn, "ui.repoList", {"sortKey": "pushed", "descending": True, "visibility": "all",
                                             "archived": "hide", "forks": "include", "language": "", "owner": "", "health": "any"})
    conn.close()


# --------------------------------------------------------------- one scene
def render(scene: str, db_path: Path, out: Path) -> None:
    theme, width, height = SCENES[scene]
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    os.environ["REPOKASE_THEME_DIR"] = str(THEMES / theme)
    sys.path.insert(0, str(ROOT / "src"))

    import httpx
    import qasync
    from PySide6 import QtQuick  # noqa: F401
    from PySide6.QtCore import Property, QObject, Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
    from PySide6.QtTest import QTest

    import repokase
    from repokase.auth.device_flow import TokenSet
    from repokase.auth.token_store import MemoryTokenStore
    from repokase.cache import db
    from repokase.controllers.actions_controller import ActionsController
    from repokase.controllers.auth_controller import AuthController
    from repokase.controllers.detail_controller import DetailController
    from repokase.controllers.repo_controller import AccountCache, RepoController
    from repokase.controllers.traffic_controller import TrafficController
    from repokase.controllers.workflows_controller import WorkflowsController
    from repokase.theme.theme import Theme

    app = QGuiApplication(sys.argv[:1])
    app.setDesktopFileName("repokase")
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    class AppInfo(QObject):
        name = Property(str, lambda s: repokase.APP_NAME, constant=True)
        tagline = Property(str, lambda s: repokase.TAGLINE, constant=True)
        version = Property(str, lambda s: repokase.__version__, constant=True)
        homepage = Property(str, lambda s: repokase.HOMEPAGE, constant=True)
        dataDir = Property(str, lambda s: "~/.local/share/repokase", constant=True)
        qtVersion = Property(str, lambda s: "6", constant=True)

    def refuse(request):
        raise httpx.ConnectError("screenshots run offline", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    conn = db.connect(db_path)
    theme_obj = Theme(watch=False)
    auth = AuthController(store=MemoryTokenStore(), http=http, accounts=AccountCache(conn))
    auth._token = TokenSet("demo", scope="read:user,repo,workflow")
    repos = RepoController(auth, conn)
    detail = DetailController(auth, repos)
    actions = ActionsController(auth, repos)
    traffic = TrafficController(auth, repos)
    workflows = WorkflowsController(auth, repos, detail)
    repos.refresh = lambda: None
    detail.refreshRuns = lambda: None
    info = AppInfo()
    for cls, name, obj in (
        (AppInfo, "App", info), (Theme, "Theme", theme_obj), (AuthController, "Auth", auth),
        (RepoController, "Repos", repos), (DetailController, "Detail", detail),
        (ActionsController, "Actions", actions), (TrafficController, "Traffic", traffic),
        (WorkflowsController, "Workflows", workflows),
    ):
        qmlRegisterSingletonInstance(cls, "Repokase", 1, 0, name, obj)

    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.load(str(ROOT / "src" / "repokase" / "qml" / "Main.qml"))
    win = engine.rootObjects()[0]
    win.resize(width, height)

    if scene == "sign-in":
        auth._set(state="awaitingUser", user_code="WDJB-MJHT",
                  verification_uri="https://github.com/login/device", expires_at=time.time() + 14 * 60 + 32)
    else:
        auth._viewer = dict(VIEWER)
        auth._state = "signedIn"
        auth.changed.emit()
        auth.signedIn.emit()
    traffic._startup.stop()
    L = repos.property("list")

    def key(k, mod=Qt.NoModifier):
        QTest.keyClick(win, k, mod)
        app.processEvents()

    def walk(item):
        yield item
        for c in item.childItems():
            yield from walk(c)

    def find(prefix):
        return [i for i in walk(win.contentItem()) if i.metaObject().className().startswith(prefix)]

    def select(name):
        key(Qt.Key_Home)
        for _ in range(L.rowOf(name)):
            key(Qt.Key_J)

    def scroll_detail_to(prefix, offset):
        body = [i for i in walk(win.contentItem()) if i.objectName() == "detailBody"][0]
        target = find(prefix)[0]
        flick = body.parentItem().parentItem()
        y = target.mapToItem(body, 0, 0).y() - offset
        flick.setProperty("contentY", max(0, min(y, flick.property("contentHeight") - flick.height())))

    async def run():
        await asyncio.sleep(0.8)
        if scene == "hero":
            select("pixel-forge")
        elif scene in ("theme-tokyo-night", "theme-latte"):
            select("hyprglow")
        elif scene == "details-traffic":
            select("hyprglow")
            await asyncio.sleep(0.3)
            scroll_detail_to("RkLineChart", 140)
            await asyncio.sleep(0.2)
            chart = find("RkLineChart")[0]
            chart.setProperty("hover", chart.property("n") - 23)
        elif scene == "run-workflow":
            select("hyprglow")
            await asyncio.sleep(0.3)
            scroll_detail_to("RkLineChart", 40)
            workflows._set(dispatchables=DISPATCHABLES, branches=["main", "feat/gradients", "fix/border-flicker"],
                           default_branch="main", loaded_for="hyprglow", loading=False)
            workflows.loadDispatch = lambda node_id: None
            from PySide6.QtCore import QMetaObject, Q_ARG
            dialog = [o for o in win.findChildren(QObject) if o.metaObject().className().startswith("WorkflowDialog")][0]
            QMetaObject.invokeMethod(dialog, "start", Q_ARG("QVariant", "hyprglow"))
            await asyncio.sleep(0.3)
            dialog.setProperty("values", {"version": "1.4.0", "channel": "stable", "draft": "true"})
        elif scene == "bulk":
            L.setProperty("sortKey", "name")
            await asyncio.sleep(0.2)
            for name in ("advent-of-code", "hackathon-2024", "kbd-layouts", "rss-digest"):
                repos.setMarked(name, True)
            select("hackathon-2024")
        elif scene == "narrow":
            select("pixel-forge")
            key(Qt.Key_Return)
        await asyncio.sleep(0.6)
        win.grabWindow().save(str(out))
        if warnings:
            print("\n".join(warnings), file=sys.stderr)
        app.quit()

    asyncio.ensure_future(run())
    with loop:
        loop.run_forever()
    conn.close()
    sys.exit(1 if warnings else 0)


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--render":
        render(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
        return 0
    scenes = sys.argv[1:] or list(SCENES)
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="repokase-shots-"))
    try:
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_DATA_HOME=str(work), XDG_CONFIG_HOME=str(work / "cfg"))
        for scene in scenes:
            db_path = work / f"{scene}.db"
            build_db(db_path)
            raw = work / f"{scene}.png"
            proc = subprocess.run([sys.executable, __file__, "--render", scene, str(db_path), str(raw)], env=env,
                                  capture_output=True, text=True, timeout=120)
            if proc.returncode != 0 or not raw.exists():
                print(f"{scene}: FAILED\n{proc.stderr}", file=sys.stderr)
                return 1
            final = OUT / f"{scene}.png"
            if shutil.which("magick"):
                subprocess.run(["magick", str(raw), "-strip", "-define", "png:compression-level=9", str(final)], check=True)
            else:
                shutil.copy(raw, final)
            print(f"{scene}: {final.relative_to(ROOT)} ({final.stat().st_size // 1024} KB)")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
