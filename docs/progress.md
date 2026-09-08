# Progress

Reverse-chronological milestone log. Newest first. Each entry states what became true and what proves
it.

## 2026-09-08 — Three units: finding the specs, declaring one, and judging the set

30 tests. Nothing resolves a database yet — the resolver, the router, `configure()` and the migrate
helper are all still to come.

**`discover_specs(installed_apps)`** imports `<app>.db_spec` for each app it is handed and collects
what it finds. It returns a list rather than a mapping keyed by alias, deliberately: a mapping would
let the second of two specs claiming one alias overwrite the first, and the collision is the thing
`validate_specs` exists to report. Cases `DS-01` to `DS-11`.

**It refuses to swallow a broken spec.** Python raises `ModuleNotFoundError` both for an app with no
`db_spec` and for a `db_spec` whose own imports are broken, so a blanket catch drops the second
silently — the library's alias never gets configured, its models fall through to `default`, and the
game starts and runs with its tables in the database they exist to stay out of. The two are told
apart by the `name` on the exception, which also separates a third case: an app listed in
`INSTALLED_APPS` that does not exist at all. Three outcomes, three messages, two exception types —
`MissingAppError` and `SpecImportError`, both chaining the original. Cases `DS-06`, `DS-08`, `DS-09`,
`DS-11`.

Only `ModuleNotFoundError` is intercepted. Anything else a `db_spec` raises propagates untouched, so
a consumer whose spec has a genuine bug in it reads their own traceback with nothing of ours in the
middle. Case `DS-06`.

**`AliasSpec`** is a frozen dataclass with five fields: `app_label`, `alias`, `sqlite_filename`, and
the two permissions — `allow_sharing_common_db` and `allow_foreign_tables_in_own_db`. The two
`allow_` fields are the outbound and inbound halves of one question, named at length because they are
read by someone installing a library rather than by us. `evennia-archive` is the library that needs
both: it may not share the game's database, and Evennia's own tables must be allowed into its. Cases
`SP-01` to `SP-10`.

Frozen because a spec is a declaration rather than state, and `discover_specs` hands back the object
it found rather than a copy. `sqlite_filename` derives from the alias in `__post_init__`, since its
default depends on another field.

**`validate_specs(specs)`** collects every problem and raises once, rather than stopping at the
first and turning a misconfigured install into one restart per mistake. It refuses an empty alias or
app label, two specs claiming one alias, one app label declared against two aliases, and an alias of
`default` — which cannot be renamed in Django, so the literal string is exact rather than a guess,
and a spec claiming it would replace the game's own connection. Cases `VS-01` to `VS-08`.

The collision between an alias's SQLite file and the game's own database file is deliberately not
here: it needs `game_dir` to resolve a path, so it belongs to `configure()`. It will compare the
resolved path against `DATABASES["default"]["NAME"]` rather than testing for the literal
`evennia.db3` — Evennia's filename is a default rather than a fixed name, so a consumer who changed
it would get no protection from a hardcoded check.

## 2026-09-08 — Scaffold, and the design behind it

**The repo is standards-compliant and empty of implementation.** `pip install -e .` and
`python runtests.py` both succeed against one smoke case.

**The design was agreed in conversation, from four existing copies of the same logic.** FCM's
`src/game/server/conf/db_config.py` resolves five aliases through three rungs and derives its routers
from the result. `evennia-ai-memory`, `evennia-message-bus` and `fcm-xrpl` each reimplement the three
rungs in their own `config.py` — and none of the three has the router half. Their install docs tell a
consumer to append the router unconditionally, which is wrong whenever the alias is not split: a bare
`migrate` records the app's migrations as applied while `allow_migrate()` blocks the tables, and the
follow-up `migrate --database <alias>` reads the same `django_migrations` table and does nothing. The
tables are never created and nothing errors.

**What was settled:**

- The three rungs, in order: `DATABASE_URL_<ALIAS>`, then `DATABASE_URL`, then a SQLite file.
- A library declares a spec and nothing else.
- The consumer calls `configure()` once, in `settings.py`. That is the only seam: `AppConfig.ready()`
  runs after both settings have been read.
- `configure()` finds the specs itself, by scanning `INSTALLED_APPS` for a `db_spec` module. That is
  what lets one call cover every installed library.
- Split is declared by the environment — own URL set, or no `DATABASE_URL` at all — not derived by
  comparing connection settings.
- One parameterised router replaces the five hand-written ones.
- Validation splits in two: the specs when `configure()` runs, and a boot cross-check in `ready()`
  that every app with a `db_spec` has its alias in `DATABASES`.
- `CONN_MAX_AGE` and the Postgres session options arrive as knobs with defaults, not constants.

**The cases drafted at this point were drafted wrong** — in one pass, ahead of any discussion of how
the library decomposes, so they assumed units and signatures nobody had reviewed. They were moved to
[test-plan-prefilled.md](test-plan-prefilled.md) and are being worked through one unit at a time.
