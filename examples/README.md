# examples

A demo Evennia gamedir that exercises this library end to end, against a real
`django.setup()`, real routers and real migrations. The unit suite mocks every boundary — no database
is ever opened, `call_command` is never really called, and Django never consults a router. This is
where that gets checked.

## What is here

| | |
|---|---|
| `demo_library/` | A throwaway distribution declaring `evennia-database-cascade` as a dependency, with a `db_spec` and **two** apps — `demo_library` and `demo_library.extra`, covered by one spec declaring both labels. The **only** way to exercise the boot check's `Requires-Dist` path, since a gamedir is not a distribution |
| `demo_game/` | A stock `evennia --init` gamedir, plus `demo_app/` — its own app, its own model, its own `db_spec` |
| `venv/` | The demo's environment, gitignored |

Two consumers on purpose, because "a consumer" means two different things: an installed library, and
the game itself.

## Setup from scratch

The gamedir's source is checked in; its databases are not, so a fresh clone starts empty.

```bash
cd examples
python -m venv venv
./venv/bin/pip install -r requirements.txt
```

Then, from `demo_game/`, three steps in order. All three go **around** the launcher, for reasons
below:

```bash
cd demo_game
alias run='../venv/bin/python -c "
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\", \"server.conf.settings\")
import django; django.setup()
exec(sys.stdin.read())"'

# 1. create the tables
echo 'from django.core.management import call_command
call_command("cascade_migrate")' | run

# 2. create account #1, which the launcher requires
echo 'from evennia.accounts.models import AccountDB
AccountDB.objects.create_superuser("demo", "demo@example.com", "demopass123")' | run
```

Then the launcher works normally:

```bash
../venv/bin/evennia start
```

**Why go around it.** Evennia's launcher runs a database check before every command, and on a fresh
database with no account `#1` it tries to create the superuser interactively — a path that recurses
until it dies in a non-interactive shell. That is Evennia's, not ours, and it only bites on the very
first run.

## What it has proved

Run on 2026-09-12:

- **`configure()` runs in a real settings module.** Three aliases resolved — `default`, `demolib`,
  `demogame` — each to its own SQLite file under `server/`.
- **`DATABASE_ROUTERS` holds instances**, not dotted paths, and Django accepts them:
  `CascadeRouter(demolib, ('demo_library', 'demo_library_extra'))`, `CascadeRouter(demogame)`.
- **The boot check passes at a real `ready()`**, with both consumer shapes present — including
  `demo_library.extra`, which ships no `db_spec` of its own and is covered by its sibling's.
- **A spec's several app labels all route to the one alias.** `db_for_read` answers `demolib` for
  models of both `demo_library` and `demo_library_extra`, and `default` for Evennia's `ObjectDB`.
- **The router genuinely gates table creation.** After `evennia cascade_migrate`:

  | | tables | demo tables |
  |---|---|---|
  | `evennia.db3` | 42 | none |
  | `demolib.db3` | 4 | `demo_library_demorecord`, `demo_library_extra_extrarecord` |
  | `demogame.db3` | 3 | `demo_app_gamerecord` |

  No demo table reached the game database, which is the separation the whole library is for.
- **Rows follow the tables.** An ORM write and read back with no `.using()`, on all three models,
  landed in and returned from the right file.
- **The library logs without a reactor.** `server/logs/cascade.log` carries an INFO line from each
  of the three public calls, written from a settings module, from `ready()` and from a management
  command — none of which has a running Twisted reactor:

  ```
  [INFO] configured aliases: demolib (own database), demogame (own database)
  [INFO] boot check passed: 2 spec(s) declared, every alias in DATABASES
  [INFO] migrated: the game database, then on their own: demolib, demogame
  ```

  This is what `evennia-logging-extension` buys, and the reason the library binds through it rather
  than through Evennia's own `logger.log_file`. See principle 8 in [CLAUDE.md](../CLAUDE.md).

It also **caught a real defect**: the boot check demanded a `db_spec` per app, which refused a
library shipping two apps under one spec — the shape the multi-label field exists to serve. The unit
suite could not see it, because it mocks the distribution metadata this path reads.
