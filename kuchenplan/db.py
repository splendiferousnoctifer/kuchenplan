from __future__ import annotations

import math
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import DEFAULT_DB, SCHEMA_PATH

DEFAULT_START_DATE = "2026-08-30"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    ensure_schema(conn)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Light migrations for existing databases."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(camp)")}
    if cols and "start_date" not in cols:
        conn.execute("ALTER TABLE camp ADD COLUMN start_date TEXT")
        conn.execute(
            "UPDATE camp SET start_date = ? WHERE start_date IS NULL",
            (DEFAULT_START_DATE,),
        )
        conn.commit()


def camp_start_date(conn: sqlite3.Connection, camp_id: int = 1) -> date | None:
    row = conn.execute(
        "SELECT start_date FROM camp WHERE id = ?", (camp_id,)
    ).fetchone()
    if not row or not row["start_date"]:
        return None
    return date.fromisoformat(str(row["start_date"]))


def day_date(start: date, day_index: int) -> date:
    return start + timedelta(days=day_index)


def format_day_date(d: date) -> str:
    return f"{d.day}.{d.month}."


def meal_day_label(
    day_name: str,
    day_index: int,
    start: date | None,
    meal: str | None = None,
    *,
    headcount_note: str | None = None,
) -> str:
    label = day_name
    if start is not None:
        label = f"{day_name} {format_day_date(day_date(start, day_index))}"
    if meal:
        label = f"{label} {meal}"
    if headcount_note:
        label = f"{label} ({headcount_note})"
    return label


def portion_equivalents(conn: sqlite3.Connection, camp_id: int = 1) -> float:
    """Weighted headcount, rounded up — same idea as weekPlan!M4."""
    rows = conn.execute(
        """
        SELECT count, factor
        FROM attendance_group
        WHERE camp_id = ?
        """,
        (camp_id,),
    ).fetchall()
    total = sum(r["count"] * r["factor"] for r in rows)
    return float(math.ceil(total - 1e-9)) if total > 0 else 0.0


def veggie_headcount(conn: sqlite3.Connection, camp_id: int = 1) -> float:
    """Raw vegetarian headcount (leiter + kinder veggie)."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(count), 0) AS n
        FROM attendance_group
        WHERE camp_id = ? AND eater_type = 'veggie'
        """,
        (camp_id,),
    ).fetchone()
    return float(row["n"])


def parse_headcount_extra(note: str | None) -> float:
    """Parse meal notes like '+5' into extra eaters for that meal."""
    if not note:
        return 0.0
    m = re.fullmatch(r"\+(\d+(?:\.\d+)?)", str(note).strip())
    return float(m.group(1)) if m else 0.0


def attendance_breakdown(conn: sqlite3.Connection, camp_id: int = 1) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT label, eater_type, count, factor,
               count * factor AS weighted
        FROM attendance_group
        WHERE camp_id = ?
        ORDER BY label, eater_type
        """,
        (camp_id,),
    ).fetchall()


def recipe_cook_counts(conn: sqlite3.Connection, camp_id: int = 1) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT r.name, COUNT(*) AS n
        FROM meal_recipe mr
        JOIN meal_slot ms ON ms.id = mr.meal_slot_id
        JOIN recipe r ON r.id = mr.recipe_id
        WHERE ms.camp_id = ?
        GROUP BY r.id
        ORDER BY r.name
        """,
        (camp_id,),
    ).fetchall()
    return {r["name"]: r["n"] for r in rows}


def shopping_lines(conn: sqlite3.Connection, camp_id: int = 1) -> list[dict]:
    """
    qty = sum over menu appearances of amount_per_person × meal_scale
    meal_scale = veggie_headcount for audience='veggie'
               = portion_equivalents + parsed('+N') for audience='all'
    """
    portions = portion_equivalents(conn, camp_id)
    veggies = veggie_headcount(conn, camp_id)
    rows = conn.execute(
        """
        SELECT
          i.name AS ingredient,
          rl.unit AS unit,
          rl.audience AS audience,
          COALESCE(c.name, 'Uncategorized') AS category,
          COALESCE(c.sort_order, 999) AS category_sort,
          i.shop AS shop,
          SUM(
            rl.amount_per_person * (
              CASE
                WHEN rl.audience = 'veggie' THEN ?
                ELSE ? + CASE
                  WHEN ms.headcount_note GLOB '+[0-9]*'
                  THEN CAST(SUBSTR(ms.headcount_note, 2) AS REAL)
                  ELSE 0
                END
              END
            )
          ) AS quantity
        FROM recipe_line rl
        JOIN recipe r ON r.id = rl.recipe_id
        JOIN ingredient i ON i.id = rl.ingredient_id
        LEFT JOIN category c ON c.id = i.category_id
        JOIN meal_recipe mr ON mr.recipe_id = r.id
        JOIN meal_slot ms ON ms.id = mr.meal_slot_id AND ms.camp_id = ?
        GROUP BY i.id, rl.unit, rl.audience
        HAVING quantity > 0
        ORDER BY category_sort, i.name
        """,
        (veggies, portions, camp_id),
    ).fetchall()
    return [
        {
            "ingredient": r["ingredient"],
            "unit": r["unit"],
            "aisle": r["category"],
            "category": r["category"],
            "shop": r["shop"],
            "audience": r["audience"],
            "quantity": round(float(r["quantity"]), 6),
            "portions": portions if r["audience"] == "all" else veggies,
        }
        for r in rows
    ]


def explain_ingredient(
    conn: sqlite3.Connection, name: str, camp_id: int = 1
) -> list[dict]:
    """Break down one ingredient per recipe, with per-meal scales (+N)."""
    portions = portion_equivalents(conn, camp_id)
    veggies = veggie_headcount(conn, camp_id)
    rows = conn.execute(
        """
        SELECT
          r.name AS recipe,
          rl.unit AS unit,
          rl.audience AS audience,
          SUM(rl.amount_per_person) AS amount_per_person
        FROM recipe_line rl
        JOIN recipe r ON r.id = rl.recipe_id
        JOIN ingredient i ON i.id = rl.ingredient_id
        WHERE LOWER(i.name) = LOWER(?)
          AND EXISTS (
            SELECT 1 FROM meal_recipe mr
            JOIN meal_slot ms ON ms.id = mr.meal_slot_id
            WHERE mr.recipe_id = r.id AND ms.camp_id = ?
          )
        GROUP BY r.id, rl.unit, rl.audience
        ORDER BY r.name
        """,
        (name, camp_id),
    ).fetchall()

    out: list[dict] = []
    for r in rows:
        app = float(r["amount_per_person"])
        meals = conn.execute(
            """
            SELECT ms.day_name, ms.day_index, ms.meal, ms.headcount_note
            FROM meal_recipe mr
            JOIN meal_slot ms ON ms.id = mr.meal_slot_id
            JOIN recipe r ON r.id = mr.recipe_id
            WHERE ms.camp_id = ? AND r.name = ?
            ORDER BY ms.day_index,
              CASE ms.meal
                WHEN 'Frühstück' THEN 1 WHEN 'Mittag' THEN 2
                WHEN 'Abend' THEN 3 ELSE 4 END
            """,
            (camp_id, r["recipe"]),
        ).fetchall()
        start = camp_start_date(conn, camp_id)
        meal_labels = []
        qty_total = 0.0
        scale_sum = 0.0
        for m in meals:
            if r["audience"] == "veggie":
                scale = veggies
            else:
                scale = portions + parse_headcount_extra(m["headcount_note"])
            qty_total += app * scale
            scale_sum += scale
            extra = parse_headcount_extra(m["headcount_note"])
            label = meal_day_label(
                m["day_name"], m["day_index"], start, m["meal"]
            )
            if extra:
                label += f" (+{extra:g}→{scale:g})"
            meal_labels.append(label)
        n = len(meals)
        out.append(
            {
                "recipe": r["recipe"],
                "unit": r["unit"],
                "audience": r["audience"],
                "amount_per_person": app,
                "times_on_menu": n,
                "qty_one_cook": round(app * (scale_sum / n if n else 0), 6),
                "qty_total": round(qty_total, 6),
                "portions": round(scale_sum / n, 4) if n else 0,
                "portion_servings": round(scale_sum, 4),
                "meals": meal_labels,
            }
        )
    return out
