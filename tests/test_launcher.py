"""Server lifetime and startup errors, independent of the Streamlit business UI."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener


class LauncherTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows console regression')
    def test_background_interpreter_has_no_console_and_keeps_project_environment(self):
        from launch_app import server_command, spawn_detached
        # Use the actual interpreter selected for Streamlit. The Windows venv
        # python.exe wrapper can recreate a console despite DETACHED_PROCESS.
        probe = (
            'import ctypes,json,sys,streamlit; from ctypes import wintypes; '
            'k=ctypes.WinDLL("kernel32"); k.GetConsoleWindow.restype=wintypes.HWND; '
            'print(json.dumps({"console":k.GetConsoleWindow(), '
            '"prefix":sys.prefix,"streamlit":streamlit.__file__}),flush=True)'
        )
        with tempfile.TemporaryDirectory(prefix='background interpreter ') as directory:
            log = Path(directory) / 'probe.log'
            child = spawn_detached([server_command(8501)[0], '-X', 'utf8', '-c', probe],
                                   Path.cwd(), log)
            self.assertEqual(child.wait(timeout=15), 0)
            result = json.loads(log.read_text(encoding='utf-8').splitlines()[-1])
            self.assertIsNone(result['console'], 'The server must not own a closeable console')
            self.assertEqual(Path(result['prefix']), Path(sys.prefix))
            self.assertTrue(Path(result['streamlit']).is_relative_to(Path(sys.prefix)))

    def test_server_survives_launcher_exit_and_keeps_output_log(self):
        self._check_server_survives_launcher_exit(terminate_launcher=False)

    def test_server_survives_forced_launcher_termination(self):
        self._check_server_survives_launcher_exit(terminate_launcher=True)

    def _check_server_survives_launcher_exit(self, terminate_launcher):
        with tempfile.TemporaryDirectory(prefix='event launcher ') as directory:
            root = Path(directory)
            # Real HTTP child; use our launcher from an intermediate process.
            child = root / 'server.py'
            child.write_text(
                'from http.server import HTTPServer, BaseHTTPRequestHandler\n'
                'import sys, threading\n'
                'class Handler(BaseHTTPRequestHandler):\n'
                ' def do_GET(self):\n'
                '  self.send_response(200); self.end_headers(); self.wfile.write(b"ok")\n'
                '  if self.path == "/shutdown": threading.Thread(target=self.server.shutdown).start()\n'
                'server=HTTPServer(("127.0.0.1",int(sys.argv[1])),Handler)\n'
                'guard=threading.Timer(15,server.shutdown); guard.daemon=True; guard.start()\n'
                'server.serve_forever(); server.server_close(); guard.cancel()\n', encoding='utf-8')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            parent_code = (
                'from launch_app import spawn_detached, wait_for_server, server_command; '
                'import sys; from pathlib import Path; '
                'p=spawn_detached([server_command(8501)[0],sys.argv[1],sys.argv[2]], '
                'Path(sys.argv[3]),Path(sys.argv[3])/"service.log"); '
                'wait_for_server(p,int(sys.argv[2]),timeout=8); print(p.pid,flush=True); '
                'sys.stdin.read() if sys.argv[4] == "hold" else None'
            )
            parent = subprocess.Popen(
                [sys.executable, '-X', 'utf8', '-c', parent_code, str(child), str(port), str(root),
                 'hold' if terminate_launcher else 'exit'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace')
            try:
                # The intermediate launcher prints only once its service is ready.
                # Its own timeout bounds this read if startup fails.
                ready = parent.stdout.readline().strip()
                if terminate_launcher:
                    parent.terminate()
                _, errors = parent.communicate(timeout=12)
                self.assertTrue(ready, errors)
                self.assertGreater(int(ready), 0)
                if not terminate_launcher:
                    self.assertEqual(parent.returncode, 0, errors)
                from launch_app import server_healthy
                self.assertTrue(server_healthy(port))
                self.assertIn('GET /_stcore/health', (root / 'service.log').read_text())
            finally:
                if parent.poll() is None:
                    parent.terminate()
                    parent.communicate(timeout=5)
                # The fixture exposes shutdown so cleanup needs no process-kill rights.
                try:
                    with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/shutdown', timeout=2):
                        pass
                except OSError:
                    # The child may already have failed before binding a socket.
                    pass
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        (root / 'service.log').unlink()
                        break
                    except PermissionError:
                        time.sleep(.05)

    def test_early_exit_is_reported_even_if_another_server_answers(self):
        from launch_app import wait_for_server, LaunchError
        child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(2)'])
        child.wait(timeout=5)
        with patch('launch_app.server_healthy', return_value=True):
            with self.assertRaisesRegex(LaunchError, 'exited'):
                wait_for_server(child, 8501, timeout=1)

    def test_timeout_has_friendly_error(self):
        from launch_app import wait_for_server, LaunchError
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
        try:
            with patch('launch_app.server_healthy', return_value=False):
                with self.assertRaisesRegex(LaunchError, 'timed out'):
                    wait_for_server(child, 8501, timeout=.1)
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_server_command_preserves_local_only_binding_and_security_defaults(self):
        from launch_app import server_command
        command = server_command(8542)
        self.assertEqual(Path(command[0]).parent, Path(sys.executable).parent)
        self.assertEqual(command[command.index('--server.address') + 1], '127.0.0.1')
        self.assertEqual(command[command.index('--server.port') + 1], '8542')
        self.assertEqual(command[command.index('--server.headless') + 1], 'true')
        self.assertNotIn('--server.enableXsrfProtection', command)
        self.assertNotIn('--server.enableCORS', command)
        self.assertTrue(Path(command[4]).is_absolute())


if __name__ == '__main__':
    unittest.main()
