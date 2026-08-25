"""Generate rounded shopping-list PDF (by shop / aisle, with recipes column)."""

from __future__ import annotations

from collections import defaultdict
from math import ceil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import connect, portion_equivalents, shopping_lines

# Tomaten Passiert / Gewürfelt: round shopping qty up to 500 g steps
TOMATO_G_500 = {"Tomaten Passiert", "Tomaten Gewürfelt"}


def round_qty(ingredient: str, unit: str, q: float) -> int:
    if q <= 0:
        return 0
    if unit == "g" and ingredient in TOMATO_G_500:
        return int(ceil(q / 500.0 - 1e-12) * 500)
    return int(ceil(q - 1e-9))


def build_grouped(conn):
    recipe_map: dict[str, set[str]] = defaultdict(set)
    for r in conn.execute(
        """
        SELECT DISTINCT i.name AS ingredient, r.name AS recipe
        FROM recipe_line rl
        JOIN recipe r ON r.id = rl.recipe_id
        JOIN ingredient i ON i.id = rl.ingredient_id
        JOIN meal_recipe mr ON mr.recipe_id = r.id
        WHERE rl.amount_per_person > 0
        """
    ):
        recipe_map[r["ingredient"]].add(r["recipe"])

    by: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for l in shopping_lines(conn):
        qty = round_qty(l["ingredient"], l["unit"], l["quantity"])
        if qty <= 0:
            continue
        shop = l.get("shop") or "?"
        aisle = l.get("aisle") or "Uncategorized"
        recipes = ", ".join(sorted(recipe_map.get(l["ingredient"], [])))
        by[shop][aisle].append(
            {
                "qty": qty,
                "unit": l["unit"],
                "item": l["ingredient"]
                + (" (veggie)" if l.get("audience") == "veggie" else ""),
                "recipes": recipes,
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
    shops = [s for s in preferred if s in by] + sorted(s for s in by if s not in preferred)
    return shops, by


def write_pdf(out_path: Path, conn=None) -> Path:
    own = conn is None
    if own:
        conn = connect()
    portions = portion_equivalents(conn)
    shops, by = build_grouped(conn)
    if own:
        conn.close()

    font_name = "Helvetica"
    fp = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    if Path(fp).exists():
        pdfmetrics.registerFont(TTFont("ShopFont", fp))
        font_name = "ShopFont"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleDE",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
    )
    sub_style = ParagraphStyle(
        "SubDE",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        textColor=colors.HexColor("#555555"),
        spaceAfter=12,
    )
    shop_style = ParagraphStyle(
        "ShopDE",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#111111"),
    )
    aisle_style = ParagraphStyle(
        "AisleDE",
        parent=styles["Heading3"],
        fontName=font_name,
        fontSize=9,
        spaceBefore=6,
        spaceAfter=2,
        textColor=colors.HexColor("#444444"),
    )
    cell_style = ParagraphStyle(
        "CellDE",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#222222"),
    )
    cell_right = ParagraphStyle("CellRight", parent=cell_style, alignment=2)
    header_style = ParagraphStyle(
        "HeadDE",
        parent=cell_style,
        fontSize=8,
        textColor=colors.HexColor("#666666"),
    )

    story = []
    story.append(Paragraph("Einkaufsliste Jungscharlager 2026", title_style))
    story.append(
        Paragraph(
            f"Basis {portions:g} Portionen · Mi–Sa +5 → 47 · Mengen auf ganze Zahlen "
            f"(Tomaten Passiert/Gewürfelt in 500 g-Schritten) · Veggie nur für 2 Personen",
            sub_style,
        )
    )

    page_w = A4[0] - 28 * mm
    col_widths = [18 * mm, 14 * mm, 48 * mm, page_w - 80 * mm]
    invisible = colors.Color(1, 1, 1, alpha=0)
    zebra = colors.HexColor("#f7f7f7")

    for shop in shops:
        blocks = [Paragraph(shop, shop_style)]
        for aisle in sorted(by[shop]):
            items = sorted(by[shop][aisle], key=lambda x: x["item"].lower())
            blocks.append(Paragraph(aisle, aisle_style))
            data = [
                [
                    Paragraph("Menge", header_style),
                    Paragraph("Einh.", header_style),
                    Paragraph("Zutat", header_style),
                    Paragraph("Rezepte", header_style),
                ]
            ]
            for it in items:
                data.append(
                    [
                        Paragraph(str(it["qty"]), cell_right),
                        Paragraph(it["unit"], cell_style),
                        Paragraph(it["item"], cell_style),
                        Paragraph(it["recipes"] or "—", cell_style),
                    ]
                )
            t = Table(data, colWidths=col_widths, repeatRows=1)
            style_cmds = [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("BOX", (0, 0), (-1, -1), 0, invisible),
                ("INNERGRID", (0, 0), (-1, -1), 0, invisible),
                ("LINEBELOW", (0, 0), (-1, 0), 0.3, colors.HexColor("#dddddd")),
            ]
            for i in range(1, len(data)):
                if i % 2 == 0:
                    style_cmds.append(("BACKGROUND", (0, i), (-1, i), zebra))
            t.setStyle(TableStyle(style_cmds))
            blocks.append(t)
            blocks.append(Spacer(1, 2 * mm))
        story.append(KeepTogether(blocks))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)

    # markdown twin
    md = [
        "# Einkaufsliste Jungscharlager 2026",
        "",
        f"Basis {portions:g} Portionen; Mi–Sa +5 → 47. "
        "Mengen auf ganze Zahlen (Tomaten in 500 g-Schritten).",
        "",
    ]
    for shop in shops:
        md.append(f"## {shop}")
        md.append("")
        for aisle in sorted(by[shop]):
            md.append(f"### {aisle}")
            md.append("")
            md.append("| Menge | Einh. | Zutat | Rezepte |")
            md.append("|------:|:------|:------|:---------|")
            for it in sorted(by[shop][aisle], key=lambda x: x["item"].lower()):
                md.append(
                    f"| {it['qty']} | {it['unit']} | {it['item']} | {it['recipes']} |"
                )
            md.append("")
    out_path.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    return out_path


def main() -> None:
    from . import DEFAULT_DB

    out = Path(DEFAULT_DB).parent / "einkaufsliste.pdf"
    path = write_pdf(out)
    print(path)


if __name__ == "__main__":
    main()
