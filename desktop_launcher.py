"""
DSM Optimizer - desktop launcher.

Runs the Flask app on a loopback-only port in a background thread, then
opens a native OS window (via pywebview - WebView2 on Windows, WebKit on
macOS, WebKitGTK on Linux) pointed at it. No browser tab, no dependency on
the user's default browser, and the port is never exposed beyond localhost.

This is the entry point PyInstaller packages into the downloadable exe.
Run directly for local development: python desktop_launcher.py
"""
import os
import sys
import socket
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def _free_port():
    """Pick an unused loopback port instead of hardcoding one - avoids
    collisions if something else on the machine is already using 8765."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_server(port, timeout=10.0):
    import urllib.request
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def _splash():
    """PyInstaller-injected splash module; absent when run from source."""
    try:
        import pyi_splash  # noqa: F401  (only exists inside the frozen exe)
        return pyi_splash
    except Exception:
        return None


def _log_error(exc):
    """console=False in the frozen exe means stderr is invisible - leave a
    breadcrumb file next to the executable so failures are diagnosable."""
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
        import traceback
        with open(os.path.join(base, "launcher_error.log"), "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") +
                     "".join(traceback.format_exception(exc)) + "\n")
    except Exception:
        pass


def _run_native(url):
    """Native window via pywebview. On Windows this rides on pythonnet/.NET,
    which is the most fragile part of the whole bundle (and .NET refuses to
    load DLLs carrying the internet-download Mark of the Web) - so this is
    ALLOWED to fail; the caller falls back to the default browser."""
    if sys.platform == "win32":
        # pythonnet 3 auto-detection can pick the wrong CLR in frozen apps;
        # the classic .NET Framework loader is what pywebview/winforms needs.
        os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
    import webview
    webview.create_window(
        "DSM Optimizer", url,
        width=1280, height=860, min_size=(960, 640),
    )
    webview.start()


def main():
    splash = _splash()
    if splash:
        splash.update_text("Loading analysis engine")
    from server.app_server import create_app, serve

    port = _free_port()
    app = create_app()

    def run_server():
        # use_reloader=False is required - the reloader spawns a second
        # process, which breaks the "one app, one window" packaging model.
        serve(app, host="127.0.0.1", port=port)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    if splash:
        splash.update_text("Starting local server\u2026")
    if not _wait_for_server(port):
        if splash:
            splash.close()
        print("ERROR: local server did not start in time.", file=sys.stderr)
        sys.exit(1)

    if splash:
        splash.close()          # window appears next; hand over cleanly

    url = f"http://127.0.0.1:{port}/"
    try:
        _run_native(url)        # returns when the user closes the window
    except Exception as e:
        # Native window unavailable (typical cause on Windows: the .NET
        # bridge refusing DLLs tagged by the zip download). The app itself
        # is fine - open it in the default browser instead and keep the
        # server alive until the user closes this process.
        _log_error(e)
        import webbrowser
        webbrowser.open(url)
        try:
            while server_thread.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()