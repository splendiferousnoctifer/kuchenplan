"""CLI for camp kitchen questions and shopping calculations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DEFAULT_DB
from .db import (
    attendance_breakdown,
    connect,
    explain_ingredient,
    portion_equivalents,
    recipe_cook_counts,
    shopping_lines,
)
from .import_xlsx import import_xlsx


def _fmt_qty(q: float) -> str:
    if abs(q - round(q)) < 1e-9:
        return str(int(round(q)))
    return f"{q:.4g}"


def cmd_people(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    rows = attendance_breakdown(conn, args.camp)
    portions = portion_equivalents(conn, args.camp)
    print(f"{'group':<8} {'type':<14} {'count':>6} {'factor':>7} {'weighted':>9}")
    total_w = 0.0
    for r in rows:
        w = float(r["weighted"])
        total_w += w
        print(
            f"{r['label']:<8} {r['eater_type']:<14} {r['count']:>6g} "
            f"{r['factor']:>7g} {w:>9g}"
        )
    print(f"{'':-<48}")
    print(f"{'sum weighted':<30} {total_w:>9g}")
    print(f"{'portion equivalents (ceil)':<30} {portions:>9g}")
    extras = conn.execute(
        """
        SELECT DISTINCT headcount_note, COUNT(*) AS meals
        FROM meal_slot
        WHERE camp_id = ? AND headcount_note IS NOT NULL AND headcount_note != ''
        GROUP BY headcount_note
        """,
        (args.camp,),
    ).fetchall()
    for e in extras:
        extra = float(str(e["headcount_note"]).lstrip("+"))
        label = f"meal override {e['headcount_note']}"
        detail = f"→ {portions + extra:g} on {e['meals']} meals"
        print(f"{label:<30} {detail}")
    conn.close()


def cmd_menu(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    rows = conn.execute(
        """
        SELECT ms.day_name, ms.meal, GROUP_CONCAT(r.name, ', ') AS recipes,
               ms.headcount_note, ms.notes, ms.gluten_notes
        FROM meal_slot ms
        LEFT JOIN meal_recipe mr ON mr.meal_slot_id = ms.id
        LEFT JOIN recipe r ON r.id = mr.recipe_id
        WHERE ms.camp_id = ?
        GROUP BY ms.id
        ORDER BY ms.day_index, CASE ms.meal
          WHEN 'Frühstück' THEN 1 WHEN 'Mittag' THEN 2 WHEN 'Abend' THEN 3 ELSE 4 END
        """,
        (args.camp,),
    ).fetchall()
    for r in rows:
        extra = []
        if r["headcount_note"]:
            extra.append(str(r["headcount_note"]))
        if r["notes"]:
            extra.append(str(r["notes"]))
        suffix = f"  ({'; '.join(extra)})" if extra else ""
        print(f"{r['day_name']:<12} {r['meal']:<10} {r['recipes']}{suffix}")
    conn.close()


def cmd_recipes(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    if args.name:
        rows = conn.execute(
            """
            SELECT r.name, i.name AS ingredient, rl.unit, rl.recipe_amount,
                   rl.yield_portions, rl.amount_per_person, rl.notes, r.source
            FROM recipe_line rl
            JOIN recipe r ON r.id = rl.recipe_id
            JOIN ingredient i ON i.id = rl.ingredient_id
            WHERE LOWER(r.name) = LOWER(?)
            ORDER BY rl.id
            """,
            (args.name,),
        ).fetchall()
        if not rows:
            print(f"No recipe named {args.name!r}", file=sys.stderr)
            sys.exit(1)
        print(f"{rows[0]['name']}  (source: {rows[0]['source']})")
        for r in rows:
            print(
                f"  {_fmt_qty(r['amount_per_person'])} {r['unit']}/person  "
                f"{r['ingredient']:20}  "
                f"(batch {_fmt_qty(r['recipe_amount'])} / {r['yield_portions']:g})"
                + (f"  — {r['notes']}" if r["notes"] else "")
            )
    else:
        counts = recipe_cook_counts(conn, args.camp)
        rows = conn.execute(
            "SELECT name, source FROM recipe ORDER BY name"
        ).fetchall()
        for r in rows:
            n = counts.get(r["name"], 0)
            flag = f"×{n}" if n else "  "
            print(f"{flag:>3}  {r['name']}")
    conn.close()


def cmd_shopping(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    lines = shopping_lines(conn, args.camp)
    if args.json:
        print(json.dumps(lines, ensure_ascii=False, indent=2))
        conn.close()
        return
    portions = next((l["portions"] for l in lines if l.get("audience") == "all"), None)
    print(f"# Shopping (full camp ≈ {portions:g} portion-equivalents)\n")

    def include(line: dict) -> bool:
        if args.category and args.category.lower() not in (line.get("aisle") or "").lower():
            return False
        if args.shop and args.shop.lower() not in (line.get("shop") or "").lower():
            return False
        return True

    lines = [l for l in lines if include(l)]

    if args.by_shop:
        lines.sort(key=lambda l: ((l.get("shop") or "zzz"), l.get("aisle") or "", l["ingredient"]))
        current_shop = object()
        current_aisle = object()
        for line in lines:
            shop = line.get("shop") or "?"
            aisle = line.get("aisle") or "Uncategorized"
            if shop != current_shop:
                current_shop = shop
                current_aisle = object()
                print(f"\n# {shop}")
            if aisle != current_aisle:
                current_aisle = aisle
                print(f"\n## {aisle}")
            tag = "  (veggie)" if line.get("audience") == "veggie" else ""
            print(
                f"  {_fmt_qty(line['quantity']):>8} {line['unit']:<4}  "
                f"{line['ingredient']}{tag}"
            )
    else:
        current = None
        for line in lines:
            aisle = line.get("aisle") or "Uncategorized"
            if aisle != current:
                current = aisle
                print(f"\n## {aisle}")
            shop = line.get("shop") or "?"
            tag = "  (veggie)" if line.get("audience") == "veggie" else ""
            print(
                f"  {_fmt_qty(line['quantity']):>8} {line['unit']:<4}  "
                f"{line['ingredient']:<22}  [{shop}]{tag}"
            )
    conn.close()


def cmd_explain(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    parts = explain_ingredient(conn, args.ingredient, args.camp)
    if not parts:
        print(f"No contributions for {args.ingredient!r}", file=sys.stderr)
        sys.exit(1)
    total = sum(p["qty_total"] for p in parts)
    unit = parts[0]["unit"]
    print(f"{args.ingredient}: {_fmt_qty(total)} {unit}\n")
    for p in parts:
        meals = ", ".join(p["meals"])
        who = "veggie" if p.get("audience") == "veggie" else "all"
        print(
            f"  {_fmt_qty(p['qty_total']):>8} {p['unit']}  "
            f"{p['recipe']}  [{who}]  "
            f"({_fmt_qty(p['amount_per_person'])}/p × {p['portions']:g} × {p['times_on_menu']})"
        )
        print(f"           meals: {meals}")
    conn.close()


def cmd_import(args: argparse.Namespace) -> None:
    import_xlsx(args.xlsx, args.db)


def cmd_pdf(args: argparse.Namespace) -> None:
    from .pdf_list import write_pdf

    out = Path(args.out) if args.out else Path(args.db).parent / "einkaufsliste.pdf"
    path = write_pdf(out)
    print(path)


def cmd_export_web(args: argparse.Namespace) -> None:
    from .export_web import write_docs

    path = write_docs(Path(args.out) if args.out else None)
    print(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="kuchenplan",
        description="Camp kitchen DB — people, menu, recipes, shopping",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite path")
    parser.add_argument("--camp", type=int, default=1)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="Import xlsx (replaces Kaiserschmarrn)")
    p.add_argument(
        "xlsx",
        nargs="?",
        default=str(__import__("pathlib").Path.home() / "Downloads" / "küchenplan_26.xlsx"),
    )
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("people", help="Show weighted headcount")
    p.set_defaults(func=cmd_people)

    p = sub.add_parser("menu", help="Show week menu")
    p.set_defaults(func=cmd_menu)

    p = sub.add_parser("recipes", help="List recipes or show one")
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_recipes)

    p = sub.add_parser("shopping", help="Computed shopping list")
    p.add_argument("--category", "-c", help="Filter by aisle")
    p.add_argument("--shop", "-s", help="Filter by shop")
    p.add_argument("--by-shop", action="store_true", help="Group by shop then aisle")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_shopping)

    p = sub.add_parser("explain", help="Why an ingredient quantity")
    p.add_argument("ingredient")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("pdf", help="Write rounded shopping PDF")
    p.add_argument("--out", help="Output PDF path")
    p.set_defaults(func=cmd_pdf)

    p = sub.add_parser("export-web", help="Bake data.json for docs/ GitHub Pages site")
    p.add_argument("--out", help="docs directory (default: ./docs)")
    p.set_defaults(func=cmd_export_web)

    args = parser.parse_args(argv)
    args.db = __import__("pathlib").Path(args.db)
    args.func(args)


if __name__ == "__main__":
    main()
