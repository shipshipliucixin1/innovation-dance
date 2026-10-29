"""Loopback-only HTTP adapter with strict origin/Host and CSRF checks."""
import argparse
import json
import mimetypes
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import content
from .llm import Model
from .service import Service
from .store import task_markdown


def make_server(root, port=43127, data_root=None):
    root = Path(root).resolve()
    application = Service(Path(data_root).resolve() if data_root else root, Model(Path(data_root).resolve() if data_root else root))
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log request bodies, private prompts, credentials or URLs.

        def respond(self, status, body, mime='application/json; charset=utf-8'):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(status)
            for k, v in {'Content-Type': mime, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                         'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                         'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def allowed_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.allowed_host():
                return self.respond(403, {'error': 'Host rejected'})
            path = urllib.parse.urlsplit(self.path)
            try:
                if path.path == '/health':
                    return self.respond(200, {'ok': True, 'version': '0.2.0'})
                if path.path == '/api/state':
                    query = {k: v[0] for k, v in urllib.parse.parse_qs(path.query).items()}
                    return self.respond(200, {**application.state(query), 'csrf': token})
                mapping = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/legacy-base.css': 'legacy-base.css'}
                if path.path not in mapping:
                    return self.respond(404, {'error': 'Not found'})
                file = root / 'static' / mapping[path.path]
                mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[file.suffix[1:]]
                self.respond(200, file.read_bytes(), mime + '; charset=utf-8')
            except (ValueError, KeyError) as e:
                self.respond(400, {'error': str(e)})

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.allowed_host() or self.headers.get('Origin') != origin or self.headers.get('X-ProjectFlow-CSRF') != token:
                # Drain only bounded bodies before rejecting. Closing an unread
                # POST can race with the sender and produce a Windows TCP reset
                # instead of the intended observable 403 response.
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if 0 < size <= 4 * 1024 * 1024:
                        self.connection.settimeout(5)
                        self.rfile.read(size)
                except (ValueError, OSError):
                    pass
                return self.respond(403, {'error': 'Same-origin request with CSRF token required'})
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.respond(415, {'error': 'JSON required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4 * 1024 * 1024:
                    return self.respond(413, {'error': 'Request must be 1 byte–4MB'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('请求需要 JSON 对象')
                application.scope(data)
                routes = {'/api/save': application.save, '/api/publish': application.publish,
                          '/api/proposal-status': application.proposal_status, '/api/ai': application.ai,
                          '/api/public-conversation': application.public_conversation, '/api/local-task': application.local_task,
                          '/api/sync': application.sync, '/api/import-legacy': application.legacy_import,
                          '/api/reset-demo': application.reset_demo}
                if self.path in routes:
                    result = routes[self.path](data)
                elif self.path == '/api/config':
                    result = application.model.configure(data)
                elif self.path == '/api/clear-key':
                    result = application.model.clear_key()
                elif self.path == '/api/discover':
                    # Coverage is intentionally bounded to explicitly supplied and saved sites.
                    db, owner = application.scope(data)
                    addresses = [str(data['url'])] if data.get('url') else [s['url'] for s in db.list('sources', owner)[:5]]
                    if not addresses:
                        raise ValueError('尚未配置搜索服务：请提供一个博客网址，或先保存订阅源。只检查这些网站，不进行全网搜索')
                    found, errors = [], []
                    for address in addresses:
                        try:
                            for item in content.discover(address):
                                if not any(x['url'] == item['url'] for x in found):
                                    found.append(item)
                        except ValueError as e:
                            errors.append(str(e))
                    result = {'sources': found, 'errors': errors, 'coverage': '有限发现：仅检查用户提供的网址或最多五个已有订阅源。未配置全网搜索服务；兴趣仅供人工筛选，不虚构搜索结果。'}
                elif self.path == '/api/task-export':
                    db, owner = application.scope(data)
                    result = {'markdown': task_markdown(db.get('tasks', data['id'], owner))}
                else:
                    return self.respond(404, {'error': 'Not found'})
                self.respond(200, result)
            except (ValueError, KeyError, TypeError, OverflowError) as e:
                # Known validation failures contain no credentials.
                self.respond(400, {'error': str(e)[:500]})
            except Exception:
                self.respond(500, {'error': '本地操作失败，未报告成功。请检查数据目录权限或数据库占用；不记录私人请求内容。'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.application = application
    return server


def main():
    parser = argparse.ArgumentParser(description='ProjectFlow local workspace')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PROJECTFLOW_PORT', '43127')))
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--data-root', type=Path, help='Separate data/config directory for development or QA')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        server = make_server(root, args.port, args.data_root)
    except OSError:
        raise SystemExit('Cannot bind local port. Close another ProjectFlow instance or set PROJECTFLOW_PORT.')
    address = f'http://127.0.0.1:{server.server_port}'
    print(f'ProjectFlow V0.2: {address}\nLoopback only. Keep this window open. Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
