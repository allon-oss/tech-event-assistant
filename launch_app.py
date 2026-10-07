"""Start the local server independently of the double-clicked console window."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent


class LaunchError(RuntimeError):
    """Short startup failure suitable for the launcher console."""


def server_command(port):
    # Windows' venv python.exe redirects to another console interpreter. That
    # interpreter creates a NEW console even when its wrapper was detached.
    # Use the same venv's windowless interpreter so there is no server console
    # for the user to close; stdout/stderr still go to the startup log.
    python = str(Path(sys.executable).with_name('pythonw.exe')) if os.name == 'nt' else sys.executable
    return [python, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
            '--server.address', '127.0.0.1', '--server.port', str(port),
            '--server.headless', 'true', '--server.showEmailPrompt', 'false',
            '--browser.serverAddress', '127.0.0.1', '--browser.serverPort', str(port)]


def spawn_detached(command, cwd, log_path):
    options = ({'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == 'nt' else {'start_new_session': True})
    # No inherited console, input stream or output pipe: closing the launcher
    # cannot send a console-close event or break the server's output stream.
    with Path(log_path).open('ab') as output:
        output.write(f'\nLaunch {datetime.now().isoformat(timespec="seconds")}\n'.encode('utf-8'))
        output.flush()
        return subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT,
                                close_fds=True, **options)


def server_healthy(port):
    # Loopback checks must not be routed through a system HTTP proxy.
    try:
        with build_opener(ProxyHandler({})).open(
            f'http://127.0.0.1:{port}/_stcore/health', timeout=1,
        ) as response:
            return response.status == 200 and response.read(16).strip() == b'ok'
    except (OSError, URLError):
        return False


def wait_for_server(process, port, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LaunchError('The server exited before it was ready. Check the local log.')
        if server_healthy(port) and process.poll() is None:
            return
        time.sleep(.2)
    raise LaunchError('Server startup timed out. Check the local log before retrying.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    os.environ.setdefault('APP_MODE', 'local')
    log_path = ROOT / f'streamlit-{args.port}.log'
    process = None
    try:
        process = spawn_detached(server_command(args.port), ROOT, log_path)
        wait_for_server(process, args.port)
    except (OSError, LaunchError) as error:
        if process is not None and process.poll() is None:
            # Only clean up this failed launch, never an existing user's server.
            if os.name == 'nt':
                # A venv python.exe may wrap another Python process on Windows.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f'Unable to stop failed startup automatically (PID {process.pid}).')
        print(f'[ERROR] {error}\nLog: {log_path}')
        return 1
    url = f'http://127.0.0.1:{args.port}'
    print(f'Ready: {url}\nBackground server PID: {process.pid}\nLog: {log_path}')
    print('The launcher may close now. The server will keep running until stopped or Windows shuts down.')
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            print('Please open the URL above in your browser.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
