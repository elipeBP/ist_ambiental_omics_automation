"""Caminho único do SQLite do projeto (`banco_ist.db` na raiz do pipeline)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "banco_ist.db"
