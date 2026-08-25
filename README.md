# Camp kitchen planner

SQLite model of your summer-camp food plan (from `küchenplan_26.xlsx`).

On import, **Kaiserschmarrn → Palatschinken** (GuteKüche basic recipe, scaled 5→40 portions). Veggie-only lines (Spinatknödel, Vegane Schnitzel, Gemüselaibchen, Haloumi) scale by vegetarian headcount, not the full camp.

## Web UI (GitHub Pages)

Static site under [`docs/`](docs/) with **2026 data baked into** `docs/data.json` (Speiseplan, Rezepte, Einkauf, Mengen-Rechnung).

```bash
kuchenplan export-web   # refresh docs/data.json from the DB
```

Enable Pages: Settings → Pages → Deploy from branch `main` / folder `/docs`.

## Setup

```bash
cd ~/work/kuchenplan
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
kuchenplan import
```

DB file: `data/kuchenplan.db` (local; not required for the static site)

## Ask the data

```bash
kuchenplan people                 # weighted headcount → 42
kuchenplan menu
kuchenplan recipes
kuchenplan recipes Palatschinken
kuchenplan shopping               # by aisle, with [shop]
kuchenplan shopping --by-shop     # Metro / Billa / Vöest / …
kuchenplan shopping -s Metro
kuchenplan shopping -c Fleisch
kuchenplan explain Milch          # which meals contribute
kuchenplan pdf                    # rounded shopping PDF
```

Each ingredient has an **aisle** (category) and preferred **shop** (from last year’s `shopping_done`, plus defaults).

## Formula

```
qty = amount_per_person × scale × times_on_menu
```

`scale` is full portion-equivalents (≈42) for normal lines, or veggie headcount (2) for `audience='veggie'`. Mi–Sa meals add `+5` → scale 47.
