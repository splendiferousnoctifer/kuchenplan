"""Camp kitchen planner — SQLite-backed recipes, headcount, shopping."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent
DEFAULT_DB = ROOT_DIR / "data" / "kuchenplan.db"
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"
