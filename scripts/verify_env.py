"""Fail before installation/start if the interpreter is outside this project."""
import sys
from pathlib import Path

expected = Path(__file__).resolve().parent.parent / '.conda-env'
if Path(sys.prefix).resolve() != expected.resolve() or sys.version_info[:2] != (3, 11):
    raise SystemExit('Expected project-local .conda-env with Python 3.11. Refusing global or other environment.')
import sqlite3
import ssl
print('Verified project Python:', sys.executable)
