"""Export a self-contained JSON snapshot for the static web UI."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .db import (
    attendance_breakdown,
    camp_start_date,
    connect,
    day_date,
    explain_ingredient,
    format_day_date,
    meal_day_label,
    portion_equivalents,
    shopping_lines,
    veggie_headcount,
)
from .pdf_list import round_qty

MEAL_ORDER = {"Frühstück": 1, "Mittag": 2, "Abend": 3}


def export_snapshot(conn=None) -> dict:
    own = conn is None
    if own:
        conn = connect()

    camp = dict(conn.execute("SELECT * FROM camp WHERE id = 1").fetchone())
    start = camp_start_date(conn)
    attendance = [dict(r) for r in attendance_breakdown(conn)]
    portions = portion_equivalents(conn)
    veggies = veggie_headcount(conn)

    weighted_sum = sum(a["count"] * a["factor"] for a in attendance)

    menu = []
    for ms in conn.execute(
        """
        SELECT id, day_index, day_name, meal, headcount_note,
               veggie_option, notes, gluten_notes
        FROM meal_slot
        WHERE camp_id = 1
        ORDER BY day_index,
          CASE meal
            WHEN 'Frühstück' THEN 1 WHEN 'Mittag' THEN 2
            WHEN 'Abend' THEN 3 ELSE 4 END
        """
    ):
        recipes = [
            r["name"]
            for r in conn.execute(
                """
                SELECT r.name FROM meal_recipe mr
                JOIN recipe r ON r.id = mr.recipe_id
                WHERE mr.meal_slot_id = ?
                ORDER BY r.name
                """,
                (ms["id"],),
            )
        ]
        scale = None
        if ms["headcount_note"] and str(ms["headcount_note"]).startswith("+"):
            try:
                scale = portions + float(str(ms["headcount_note"])[1:])
            except ValueError:
                scale = portions
        else:
            scale = portions
        day_d = day_date(start, ms["day_index"]) if start else None
        menu.append(
            {
                "day_index": ms["day_index"],
                "day": ms["day_name"],
                "date": day_d.isoformat() if day_d else None,
                "date_label": format_day_date(day_d) if day_d else None,
                "meal": ms["meal"],
                "headcount_note": ms["headcount_note"],
                "scale": scale,
                "veggie_option": ms["veggie_option"],
                "notes": ms["notes"],
                "gluten_notes": ms["gluten_notes"],
                "recipes": recipes,
            }
        )

    recipes = []
    for r in conn.execute(
        "SELECT id, name, notes, source FROM recipe ORDER BY name"
    ):
        lines = []
        for ln in conn.execute(
            """
            SELECT i.name AS ingredient, rl.unit, rl.amount_per_person,
                   rl.recipe_amount, rl.yield_portions, rl.audience,
                   rl.is_side, rl.notes,
                   COALESCE(c.name, '') AS aisle
            FROM recipe_line rl
            JOIN ingredient i ON i.id = rl.ingredient_id
            LEFT JOIN category c ON c.id = i.category_id
            WHERE rl.recipe_id = ?
            ORDER BY rl.audience, i.name
            """,
            (r["id"],),
        ):
            lines.append(dict(ln))
        cook_count = conn.execute(
            """
            SELECT COUNT(*) FROM meal_recipe mr
            JOIN meal_slot ms ON ms.id = mr.meal_slot_id
            WHERE mr.recipe_id = ? AND ms.camp_id = 1
            """,
            (r["id"],),
        ).fetchone()[0]
        meals = [
            meal_day_label(
                m["day_name"],
                m["day_index"],
                start,
                m["meal"],
                headcount_note=m["headcount_note"],
            )
            for m in conn.execute(
                """
                SELECT ms.day_name, ms.day_index, ms.meal, ms.headcount_note
                FROM meal_recipe mr
                JOIN meal_slot ms ON ms.id = mr.meal_slot_id
                WHERE mr.recipe_id = ? AND ms.camp_id = 1
                ORDER BY ms.day_index,
                  CASE ms.meal
                    WHEN 'Frühstück' THEN 1 WHEN 'Mittag' THEN 2
                    WHEN 'Abend' THEN 3 ELSE 4 END
                """,
                (r["id"],),
            )
        ]
        recipes.append(
            {
                "name": r["name"],
                "notes": r["notes"],
                "source": r["source"],
                "on_menu": cook_count,
                "meals": meals,
                "lines": lines,
            }
        )

    recipe_map: dict[str, set[str]] = defaultdict(set)
    for row in conn.execute(
        """
        SELECT DISTINCT i.name AS ingredient, r.name AS recipe
        FROM recipe_line rl
        JOIN recipe r ON r.id = rl.recipe_id
        JOIN ingredient i ON i.id = rl.ingredient_id
        JOIN meal_recipe mr ON mr.recipe_id = r.id
        WHERE rl.amount_per_person > 0
        """
    ):
        recipe_map[row["ingredient"]].add(row["recipe"])

    shopping = []
    for l in shopping_lines(conn):
        name = l["ingredient"]
        qty = l["quantity"]
        rounded = round_qty(name, l["unit"], qty)
        shopping.append(
            {
                "ingredient": name,
                "unit": l["unit"],
                "aisle": l["aisle"],
                "shop": l["shop"] or "?",
                "audience": l["audience"],
                "quantity_raw": qty,
                "quantity": rounded,
                "recipes": sorted(recipe_map.get(name, [])),
                "breakdown": explain_ingredient(conn, name),
            }
        )

    preferred = [
        "Metro",
        "Billa",
        "Vöest",
        "Bäcker vor Ort",
        "DM",
        "Spende Spitz",
        "Spende Honeder",
        "Spende/Metro?",
    ]
    shops = sorted(
        {s["shop"] for s in shopping},
        key=lambda s: (preferred.index(s) if s in preferred else 99, s),
    )
    aisles = sorted({s["aisle"] for s in shopping})

    out = {
        "camp": camp,
        "attendance": attendance,
        "calculation": {
            "weighted_raw": round(weighted_sum, 4),
            "portion_equivalents": portions,
            "veggie_headcount": veggies,
            "formula": (
                "qty = amount_per_person × scale × times_on_menu; "
                "scale = portion_equivalents (+ meal +N) for normal lines, "
                "veggie_headcount for veggie-only lines"
            ),
            "rounding": (
                "Shopping quantities ceil to whole packs; "
                "Tomaten Passiert/Gewürfelt in 500 g steps"
            ),
        },
        "menu": menu,
        "recipes": recipes,
        "shopping": shopping,
        "shops": shops,
        "aisles": aisles,
    }
    if own:
        conn.close()
    return out


def _stamp_index_html(docs: Path, version: str) -> None:
    index = docs / "index.html"
    text = index.read_text(encoding="utf-8")
    text = re.sub(r'data-version="[^"]*"', f'data-version="{version}"', text)
    text = re.sub(r'href="styles\.css(?:\?v=[^"]*)?"', f'href="styles.css?v={version}"', text)
    text = re.sub(
        r'src="app\.js(?:\?v=[^"]*)?"',
        f'src="app.js?v={version}"',
        text,
    )
    index.write_text(text, encoding="utf-8")


def write_docs(docs_dir: Path | None = None) -> Path:
    root = Path(__file__).resolve().parent.parent
    docs = docs_dir or (root / "docs")
    docs.mkdir(parents=True, exist_ok=True)
    data = export_snapshot()
    data["exported_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path = docs / "data.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    _stamp_index_html(docs, version)
    return path


if __name__ == "__main__":
    p = write_docs()
    print(p)
