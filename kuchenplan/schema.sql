-- Camp kitchen planner schema
PRAGMA foreign_keys = ON;

CREATE TABLE camp (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  year INTEGER NOT NULL,
  notes TEXT
);

-- Weighted headcount groups that feed portion_equivalents
CREATE TABLE attendance_group (
  id INTEGER PRIMARY KEY,
  camp_id INTEGER NOT NULL REFERENCES camp(id) ON DELETE CASCADE,
  label TEXT NOT NULL,          -- leiter | kinder
  eater_type TEXT NOT NULL,     -- normal | strong_eater | veggie
  count REAL NOT NULL DEFAULT 0,
  factor REAL NOT NULL DEFAULT 1.0,
  UNIQUE (camp_id, label, eater_type)
);

CREATE TABLE category (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ingredient (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  category_id INTEGER REFERENCES category(id),  -- aisle for shopping list
  default_unit TEXT,
  shop TEXT  -- preferred store: Metro, Billa, DM, Spende Spitz, …
);

CREATE TABLE recipe (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  notes TEXT,
  source TEXT
);

CREATE TABLE recipe_line (
  id INTEGER PRIMARY KEY,
  recipe_id INTEGER NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
  ingredient_id INTEGER NOT NULL REFERENCES ingredient(id),
  unit TEXT NOT NULL,
  recipe_amount REAL NOT NULL,   -- amount for yield_portions
  yield_portions REAL NOT NULL DEFAULT 40,
  amount_per_person REAL NOT NULL,
  is_side INTEGER NOT NULL DEFAULT 0,  -- zuspeise
  -- 'all' = scale by full portion_equivalents; 'veggie' = scale by veggie headcount only
  audience TEXT NOT NULL DEFAULT 'all' CHECK (audience IN ('all', 'veggie')),
  notes TEXT
);

CREATE TABLE meal_slot (
  id INTEGER PRIMARY KEY,
  camp_id INTEGER NOT NULL REFERENCES camp(id) ON DELETE CASCADE,
  day_name TEXT NOT NULL,
  day_index INTEGER NOT NULL,    -- 0=Sonntag …
  meal TEXT NOT NULL,            -- Frühstück | Mittag | Abend
  headcount_note TEXT,           -- e.g. +5
  veggie_option INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  gluten_notes TEXT,
  UNIQUE (camp_id, day_index, meal)
);

CREATE TABLE meal_recipe (
  id INTEGER PRIMARY KEY,
  meal_slot_id INTEGER NOT NULL REFERENCES meal_slot(id) ON DELETE CASCADE,
  recipe_id INTEGER NOT NULL REFERENCES recipe(id),
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE (meal_slot_id, recipe_id)
);

-- Static extras (shopping_done sheet) not driven by recipes
CREATE TABLE shopping_extra (
  id INTEGER PRIMARY KEY,
  camp_id INTEGER NOT NULL REFERENCES camp(id) ON DELETE CASCADE,
  category TEXT,           -- aisle label from shopping_done sections
  quantity_text TEXT,
  item TEXT NOT NULL,
  note TEXT,
  store TEXT               -- shop
);

CREATE INDEX idx_recipe_line_recipe ON recipe_line(recipe_id);
CREATE INDEX idx_meal_recipe_slot ON meal_recipe(meal_slot_id);
CREATE INDEX idx_ingredient_category ON ingredient(category_id);
