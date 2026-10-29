"""Offline, redacting publication guard for working files, index and Git history.

No credentials are printed. This is a conservative heuristic, not proof that
arbitrary private information is absent. Review screenshots/content manually.
"""
import argparse
import fnmatch
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
MAX_BLOB = 8 * 1024 * 1024
BAD_DIRS = {'.conda-env', '.venv', 'node_modules', '__pycache__', 'data', '.qa', '.tmp',
            '.test-tmp', 'dist', 'build', '.aws', '.ssh', '.codex', '.agents', 'private', 'exports', 'backups'}
BAD_NAMES = ('*.sqlite3*', '*.db', '*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa*', 'id_ed25519*',
             'credentials.json', 'secrets.json', 'tokens.json', '.netrc', '.npmrc', '*.log',
             '*.zip', '*.bak', '*.backup', 'projectflow-*-export.json', 'projectflow-backup-*.json')
SIGNATURES = {
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    'github-token': re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'),
    'provider-api-key': re.compile(rb'\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b'),
    'aws-access-key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'google-api-key': re.compile(rb'\bAIza[A-Za-z0-9_-]{30,}\b'),
    'slack-token': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'credential-url': re.compile(rb'https?://[^\s/:@\"\']+:[^\s/@\"\']+@[^\s/\"\']+'),
}
ASSIGNMENT = re.compile(
    r'''(?im)["']?\b(?:LLM_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|api_key|apikey|access_token|auth_token|password|secret)\b["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']''')
DOTENV = re.compile(r'(?im)^[ \t]*(?:LLM_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|API_KEY|ACCESS_TOKEN|PASSWORD|SECRET)[ \t]*=[ \t]*([A-Za-z0-9_./+=:-]+)[ \t]*(?:#.*)?$')
# Exact, visibly fictional values already used by the offline tests.
FIXTURES = {'PRIVATE_KEY', 'NO_WRITE', 'fixture-not-a-real-key'}


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise ValueError('Git command failed: ' + ' '.join(args[:2]) + ' (no credentials logged)')
    return result.stdout


def blocked_path(path):
    path = path.replace('\\', '/')
    parts = PurePosixPath(path.lower()).parts
    if any(p in BAD_DIRS for p in parts):
        return True
    name = parts[-1] if parts else ''
    if name.startswith('.env') and path != '.env.example':
        return True
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in BAD_NAMES)


def placeholder(value, path):
    value = value.strip().strip('"\'')
    if not value:
        return True
    if path.replace('\\', '/').startswith('tests/') and value in FIXTURES:
        return True
    return value in {'YOUR_API_KEY', 'your-api-key', 'your_api_key', '<API_KEY>', '<your-key>', 'change-me'}


def inspect(data, path):
    findings = []
    if blocked_path(path):
        findings.append(('private-or-generated-path', 0))
    if len(data) > MAX_BLOB:
        findings.append(('oversized-file-needs-manual-review', 0))
        return findings
    for label, pattern in SIGNATURES.items():
        for match in pattern.finditer(data):
            findings.append((label, data[:match.start()].count(b'\n') + 1))
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return findings  # Binary signature checks above still apply.
    for pattern in (ASSIGNMENT, DOTENV):
        for match in pattern.finditer(text):
            if not placeholder(match.group(1), path):
                findings.append(('literal-credential-assignment', text[:match.start()].count('\n') + 1))
    return sorted(set(findings))


def staged_entries():
    entries = []
    for entry in git('ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        mode, oid, stage = meta.decode().split()
        if stage != '0':
            raise ValueError('Resolve unmerged index entries before publication')
        if mode not in ('100644', '100755'):
            raise ValueError('Review non-regular indexed file before publication: ' + path.decode('utf-8'))
        entries.append((oid, path.decode('utf-8')))
    return entries


def history_entries():
    # Includes all refs and reflogs, so deleted historical secrets are examined.
    entries = []
    objects = git('rev-list', '--objects', '--all', '--reflog').splitlines()
    for line in objects:
        oid, _, path = line.partition(b' ')
        kind = git('cat-file', '-t', oid.decode()).strip()
        if path and kind == b'blob':
            entries.append((oid.decode(), path.decode('utf-8')))
        elif kind == b'commit':
            entries.append((oid.decode(), '.history/commit-' + oid.decode()[:12]))
    for ref in git('for-each-ref', '--format=%(objecttype) %(objectname)').splitlines():
        kind, oid = ref.split(b' ', 1)
        if kind == b'tag':
            entries.append((oid.decode(), '.history/tag-' + oid.decode()[:12]))
    return entries


def scan(worktree=True):
    reported, checked = [], set()
    counts = {'working_files': 0, 'indexed_files': 0, 'historical_objects': 0}
    if worktree:
        for raw in git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0'):
            if not raw:
                continue
            path = raw.decode('utf-8')
            file = ROOT / path
            if not file.exists():
                continue
            if file.is_symlink():
                reported.append(('working tree', path, 'symlink-needs-manual-review', 0))
                continue
            counts['working_files'] += 1
            for label, line in inspect(file.read_bytes(), path):
                reported.append(('working tree', path, label, line))
    for scope, entries, counter in [('index', staged_entries(), 'indexed_files'), ('history', history_entries(), 'historical_objects')]:
        for oid, path in entries:
            counts[counter] += 1
            if (oid, path) in checked:
                continue
            checked.add((oid, path))
            for label, line in inspect(git('cat-file', '-p', oid), path):
                reported.append((scope, path, label, line))
    return counts, reported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged-only', action='store_true', help='Check index and history without unstaged working files')
    args = parser.parse_args()
    try:
        counts, findings = scan(not args.staged_only)
    except (ValueError, OSError) as error:
        print('Publication check could not complete:', str(error))
        return 2
    print('Checked:', ', '.join(f'{k}={v}' for k, v in counts.items()))
    if findings:
        print('STOP: potential sensitive material; do not push. Values are redacted.')
        for scope, path, label, line in findings:
            print(f'  {scope}: {path}:{line} [{label}]')
        return 1
    print('PASS: no known credential signatures or prohibited paths detected.')
    print('Heuristic check only; manually review new content and screenshots before publishing.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
