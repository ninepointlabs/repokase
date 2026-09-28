"""Repokase entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from . import APP_ID, APP_NAME, HOMEPAGE, TAGLINE, __version__

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
    return parser.parse_args(argv)


async def _shutdown(auth) -> None:
    # Quitting mid-refresh: cancel in-flight work so no task outlives the loop.
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    await auth.aclose()


def main(argv: list[str] | None = None) -> int:
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

    import qasync
    from PySide6.QtCore import Property, QObject, QTimer, qVersion
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

    class AppInfo(QObject):
        name = Property(str, lambda self: APP_NAME, constant=True)
        tagline = Property(str, lambda self: TAGLINE, constant=True)
        version = Property(str, lambda self: __version__, constant=True)
        homepage = Property(str, lambda self: HOMEPAGE, constant=True)
        dataDir = Property(str, lambda self: str(config.data_dir()), constant=True)
        qtVersion = Property(str, lambda self: qVersion(), constant=True)

    info = AppInfo()
    theme = Theme()
    conn = db.connect(config.data_dir() / "repokase.db")
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
    engine.load(str(HERE / "qml" / "Main.qml"))
    if not engine.rootObjects():
        return 1

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

    loop.call_soon(auth.restore)
    with loop:
        # QGuiApplication.quit() stops the qasync loop and run_forever returns.
        loop.run_forever()
        loop.run_until_complete(_shutdown(auth))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
