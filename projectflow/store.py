"""SQLite persistence. Personal and simulated-community files never overlap."""
import json
import sqlite3
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

KINDS = ('profiles', 'interests', 'sources', 'articles', 'conversations', 'messages', 'ideas',
         'experiments', 'projects', 'versions', 'tasks', 'results', 'reminders', 'snapshots',
         'comments', 'proposals')
PUBLIC_FIELDS = ('title', 'summary', 'domain', 'problem', 'progress', 'approach', 'difficulty',
                 'help', 'directions', 'materials')


def now():
    return datetime.now(timezone.utc).isoformat()


def public_fields(data):
    if not isinstance(data, dict):
        raise ValueError('公开快照格式无效')
    return {k: str(data.get(k, ''))[:20000] for k in PUBLIC_FIELDS}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            old = db.execute('PRAGMA user_version').fetchone()[0]
            if old > 2:
                raise ValueError('数据库来自更新版本，请升级软件；未修改数据')
            if old and old < 2:
                backup = self.path.with_suffix('.before-v2-' + datetime.now().strftime('%Y%m%d%H%M%S%f') + '.sqlite3')
                with closing(sqlite3.connect(backup)) as target:
                    db.backup(target)
            for kind in KINDS:
                db.execute(f'CREATE TABLE IF NOT EXISTS {kind} (id TEXT PRIMARY KEY, owner TEXT NOT NULL, parent TEXT NOT NULL DEFAULT \'\', data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
                db.execute(f'CREATE INDEX IF NOT EXISTS idx_{kind}_owner ON {kind}(owner, parent)')
            db.execute('CREATE TABLE IF NOT EXISTS migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO migrations VALUES (2, ?)', (now(),))
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def unpack(row):
        if row is None:
            raise ValueError('记录不存在或当前身份不能访问')
        return {**json.loads(row['data']), **{k: row[k] for k in ('id', 'owner', 'parent', 'created_at', 'updated_at')}}

    def list(self, kind, owner=None, parent=None):
        self.kind(kind)
        where, args = [], []
        for key, value in [('owner', owner), ('parent', parent)]:
            if value is not None:
                where.append(key + '=?')
                args.append(value)
        with self.connect() as db:
            return [self.unpack(row) for row in db.execute(f'SELECT * FROM {kind}' + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY updated_at DESC, id', args)]

    def get(self, kind, identity, owner=None):
        self.kind(kind)
        with self.connect() as db:
            row = db.execute(f'SELECT * FROM {kind} WHERE id=?' + (' AND owner=?' if owner is not None else ''), (identity, owner) if owner is not None else (identity,)).fetchone()
            return self.unpack(row)

    @staticmethod
    def kind(kind):
        if kind not in KINDS:
            raise ValueError('未知的数据类型')

    def put(self, kind, owner, data, identity=None, parent='', db=None):
        self.kind(kind)
        clean = {k: v for k, v in data.items() if k not in ('id', 'owner', 'parent', 'created_at', 'updated_at')}
        identity = identity or uuid.uuid4().hex
        stamp = now()
        def write(conn):
            old = conn.execute(f'SELECT owner FROM {kind} WHERE id=?', (identity,)).fetchone()
            if old and old['owner'] != owner:
                raise ValueError('当前身份不能修改此记录')
            conn.execute(f'INSERT INTO {kind} VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,parent=excluded.parent,updated_at=excluded.updated_at',
                         (identity, owner, parent, json.dumps(clean, ensure_ascii=False), stamp, stamp))
        if db is None:
            with self.connect() as conn:
                write(conn)
        else:
            write(db)
        return identity

    def snapshot_context(self, snapshot_id):
        snap = self.get('snapshots', snapshot_id)
        # This function deliberately has no owner/private-project lookup.
        return {'public_project': public_fields(snap), 'comments': [
            {'author': c['owner'], 'text': c.get('text', '')} for c in self.list('comments', parent=snapshot_id)[:50]]}


def is_due(reminder, today=None):
    today = today or datetime.now().astimezone().date().isoformat()
    return reminder.get('status', 'PENDING') == 'PENDING' and reminder.get('date', '9999') <= today


def task_markdown(task):
    fields = [('background', '背景信息'), ('goal', '任务目标'), ('context', '相关项目上下文'),
              ('inputs', '已知输入'), ('outputs', '预期输出'), ('constraints', '实现约束'),
              ('acceptance', '验收标准'), ('forbidden', '不允许的操作'), ('confirmation', '需要人工确认的事项')]
    return '# ' + task.get('title', '执行任务') + '\n\n' + '\n\n'.join('## ' + label + '\n\n' + str(task.get(key, '待明确')) for key, label in fields) + '\n'
