"""Build an allowlisted source release; never zip the entire working directory."""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ['README.md', 'README.zh-CN.md', 'LICENSE', 'CONTRIBUTING.md', 'DEMO_GUIDE.md',
         'requirements.txt', '.env.example', '.gitignore', '.gitattributes', 'setup.bat', 'start.bat', 'update-github.bat', 'CHANGELOG.md']
FOLDERS = ['projectflow', 'static', 'tests', 'scripts', 'docs', '.github']
SUFFIXES = {'.py', '.js', '.html', '.css', '.md', '.ps1', '.yml', '.png'}


def main():
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    target = out / 'ProjectFlow-v0.2.0-source.zip'
    selected = [ROOT / name for name in FILES]
    for folder in FOLDERS:
        for file in (ROOT / folder).rglob('*'):
            if file.is_file() and file.suffix in SUFFIXES and not any(part in ('__pycache__', '.tmp', '.qa') for part in file.relative_to(ROOT).parts):
                selected.append(file)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(set(selected)):
            if not file.is_file():
                raise SystemExit('Required release file missing: ' + str(file.relative_to(ROOT)))
            archive.write(file, 'ProjectFlow/' + file.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert all(not n.endswith(('.sqlite3', '.db', '/.env')) and '/.conda-env/' not in n for n in archive.namelist())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / 'SHA256SUMS.txt').write_text(digest + '  ' + target.name + '\n', 'utf-8')
    print(str(target))
    print('Files:', len(selected), 'SHA256:', digest)


if __name__ == '__main__':
    main()
