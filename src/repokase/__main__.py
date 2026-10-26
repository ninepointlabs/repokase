"""Repokase entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from . import (
    APP_ID,
    APP_NAME,
    COPYRIGHT,
    CREATED,
    HOMEPAGE,
    LICENSE_NAME,
    ORGANIZATION,
    SUPPORT_EMAIL,
    TAGLINE,
    __version__,
    hostenv,
)

HERE = Path(__file__).resolve().parent


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: {TAGLINE}")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument(
        "--snapshot-traffic",
        action="store_true",
        help="record today's traffic for your repositories without opening the window",
    )
    parser.add_argument(
        "--if-due",
        action="store_true",
        help="with --snapshot-traffic: skip if a snapshot ran in the last 20 hours",
    )
    # Packaging check (AppImage CI): start the full UI, report, quit.
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.if_due and not args.snapshot_traffic:
        parser.error("--if-due only works with --snapshot-traffic")
    return args


async def _shutdown(auth) -> None:
    # Quitting mid-refresh: cancel in-flight work so no task outlives the loop.
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    await auth.aclose()


def main(argv: list[str] | None = None) -> int:
    # From the AppImage: programs we start (xdg-open, the browser) must not
    # see the AppImage runtime's variables.
    hostenv.restore()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # httpx logs full request URLs at INFO; keep it quiet so nothing sensitive
    # ever lands in logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if args.snapshot_traffic:
        from .headless import snapshot_traffic_cli

        return snapshot_traffic_cli(args.if_due)

    # Every control is our own template; never let a platform style leak in.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    import PySide6
    import qasync
    from PySide6.QtCore import Property, QObject, QTimer, QUrl, Slot, qVersion
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
    from PySide6 import QtQuick  # noqa: F401  (root object must resolve to QQuickWindow)

    from . import config
    from .cache import db
    from .controllers.auth_controller import AuthController
    from .controllers.actions_controller import ActionsController
    from .controllers.detail_controller import DetailController
    from .controllers.repo_controller import AccountCache, RepoController
    from .controllers.traffic_controller import TrafficController
    from .controllers.workflows_controller import WorkflowsController
    from .theme.theme import Theme

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    # Wayland app_id -> Hyprland `class:repokase`, and .desktop association.
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(HERE / "assets" / "repokase.svg"))))

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    cache_notice = cache_error = ""
    try:
        conn, cache_notice = db.open_cache(config.data_dir() / "repokase.db")
    except db.CacheUnavailable as exc:
        # Still open the window (started from the app menu, stderr goes
        # nowhere), but only to say what's wrong.
        print(f"repokase: {exc}", file=sys.stderr)
        cache_error = str(exc)
        conn = db.connect(":memory:")

    class AppInfo(QObject):
        name = Property(str, lambda self: APP_NAME, constant=True)
        tagline = Property(str, lambda self: TAGLINE, constant=True)
        version = Property(str, lambda self: __version__, constant=True)
        homepage = Property(str, lambda self: HOMEPAGE, constant=True)
        dataDir = Property(str, lambda self: str(config.data_dir()), constant=True)
        qtVersion = Property(str, lambda self: qVersion(), constant=True)
        # For the About dialog.
        organization = Property(str, lambda self: ORGANIZATION, constant=True)
        supportEmail = Property(str, lambda self: SUPPORT_EMAIL, constant=True)
        created = Property(str, lambda self: CREATED, constant=True)
        license = Property(str, lambda self: LICENSE_NAME, constant=True)
        copyright = Property(str, lambda self: COPYRIGHT, constant=True)
        pysideVersion = Property(str, lambda self: PySide6.__version__, constant=True)
        pythonVersion = Property(str, lambda self: sys.version.split()[0], constant=True)
        icon = Property(QUrl, lambda self: QUrl.fromLocalFile(str(HERE / "assets" / "repokase.svg")), constant=True)
        # The cache was rebuilt (notice) or can't be used at all (error).
        cacheNotice = Property(str, lambda self: cache_notice, constant=True)
        cacheError = Property(str, lambda self: cache_error, constant=True)

        @Property(str, constant=True)
        def licenseText(self) -> str:
            try:
                text = (HERE / "assets" / "LICENSE.txt").read_text(encoding="utf-8")
            except OSError:
                return f"{LICENSE_NAME}, {COPYRIGHT}"
            # One line per paragraph, so it wraps to the dialog's width.
            return "\n\n".join(" ".join(p.split()) for p in text.split("\n\n") if p.strip())

        @Property(str, constant=True)
        def details(self) -> str:
            """Version details to paste into a support email."""
            return (
                f"{APP_NAME} {__version__}\n"
                f"Qt {qVersion()}, PySide6 {PySide6.__version__}, Python {sys.version.split()[0]}\n"
                f"{os.environ.get('XDG_CURRENT_DESKTOP', 'unknown desktop')}, {QGuiApplication.platformName()}"
            )

        @Slot(str)
        def copy(self, text: str) -> None:
            QGuiApplication.clipboard().setText(text)

    info = AppInfo()
    theme = Theme()
    auth = AuthController(accounts=AccountCache(conn))
    repos = RepoController(auth, conn)
    detail = DetailController(auth, repos)
    actions = ActionsController(auth, repos)
    traffic = TrafficController(auth, repos)
    workflows = WorkflowsController(auth, repos, detail)
    qmlRegisterSingletonInstance(AppInfo, "Repokase", 1, 0, "App", info)
    qmlRegisterSingletonInstance(Theme, "Repokase", 1, 0, "Theme", theme)
    qmlRegisterSingletonInstance(AuthController, "Repokase", 1, 0, "Auth", auth)
    qmlRegisterSingletonInstance(RepoController, "Repokase", 1, 0, "Repos", repos)
    qmlRegisterSingletonInstance(DetailController, "Repokase", 1, 0, "Detail", detail)
    qmlRegisterSingletonInstance(ActionsController, "Repokase", 1, 0, "Actions", actions)
    qmlRegisterSingletonInstance(TrafficController, "Repokase", 1, 0, "Traffic", traffic)
    qmlRegisterSingletonInstance(WorkflowsController, "Repokase", 1, 0, "Workflows", workflows)

    engine = QQmlApplicationEngine()
    qml_warnings: list[str] = []
    if args.self_test:
        engine.warnings.connect(lambda ws: qml_warnings.extend(w.toString() for w in ws))
    engine.load(str(HERE / "qml" / "Main.qml"))
    if not engine.rootObjects():
        return 1

    status = 0
    if args.self_test:
        def report():
            nonlocal status
            win = engine.rootObjects()[0]
            print(
                f"self-test: platform={QGuiApplication.platformName()} "
                f"app_id={QGuiApplication.desktopFileName()} visible={win.isVisible()} "
                f"theme={theme.source}/{'dark' if theme.isDark else 'light'} radius={theme.radius}",
                flush=True,
            )
            for w in qml_warnings:
                print(f"self-test: QML warning: {w}", flush=True)
            status = 1 if qml_warnings or not win.isVisible() else 0
            # CI points this at a fake xdg-open to check what children inherit.
            url = os.environ.get("REPOKASE_SELF_TEST_URL")
            if url:
                from PySide6.QtGui import QDesktopServices

                QDesktopServices.openUrl(QUrl(url))
            QTimer.singleShot(1000, app.quit)

        QTimer.singleShot(int(os.environ.get("REPOKASE_SELF_TEST_DELAY", "2000")), report)

    # Development aid: REPOKASE_SCREENSHOT=out.png grabs the window after a
    # short delay and exits.
    shot = os.environ.get("REPOKASE_SCREENSHOT")
    if shot:
        def grab():
            try:
                win = engine.rootObjects()[0]
                logging.debug("screenshot: active=%s focus=%s", win.isActive(), win.activeFocusItem())
                win.grabWindow().save(shot)
            finally:
                app.quit()

        QTimer.singleShot(int(os.environ.get("REPOKASE_SCREENSHOT_DELAY", "1500")), grab)

    if not cache_error:
        loop.call_soon(auth.restore)
    with loop:
        # QGuiApplication.quit() stops the qasync loop and run_forever returns.
        loop.run_forever()
        loop.run_until_complete(_shutdown(auth))
    conn.close()
    return status


if __name__ == "__main__":
    sys.exit(main())
