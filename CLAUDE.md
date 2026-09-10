# CLAUDE.md

> **Project-wide working rules and cross-repo context live in the FCM umbrella repo's `CLAUDE.md`**,
> loaded automatically when you work from the umbrella root. If you opened this repo directly instead
> of via the umbrella, relaunch from the umbrella root for the full context. This file holds only this
> repo's specific instructions.

Instructions for Claude (and other LLM agents) working in this repository.

## What this project is

`evennia-database-cascade` resolves an [Evennia](https://www.evennia.com/) game's database aliases
from the environment, and derives the routers to match. A library that owns tables declares a spec;
the game makes one call in its settings; each alias then lands on a database of its own, on the
game's, or in a local SQLite file, according to what the deployment set. Tagline: **"One settings
call. SQLite locally, Postgres in production, a database of its own when you want one."**

For the big-picture overview, read [README.md](README.md).
For the design wiki, read [docs/INDEX.md](docs/INDEX.md).

## Project status

**Complete and unproven — no consumer runs it yet.** For what exists, what proves it and what does
not exist yet, read [docs/progress.md](docs/progress.md) — it is the only place that state is kept,
so this section stays a pointer rather than a second copy that ages.

## Where to read first

1. [README.md](README.md) — what the library is and the problem it solves.
2. [docs/test-plan.md](docs/test-plan.md) — the agreed behaviour, case by case. **A behavioural
   change starts here**, before any test and any code.
3. [docs/installing.md](docs/installing.md) — the consumer-facing shape: the spec, the one call,
   and the environment variables.
4. [docs/progress.md](docs/progress.md) — what actually exists right now.

## Load-bearing architectural principles

Agreed in the design conversation of 2026-09-08. Every implementation decision must respect them.

1. **The library does not own game concepts.** It knows about Django database aliases, routers and
   migrations. Rooms, items, characters, economies and quest state belong to the consumer game and
   are never named here.
2. **No FCM-specific assumptions.** This library is being extracted from FCM's `server/conf/db_config.py`
   and the hand-rolled cascades in four repos. What comes with it must be general: `CONN_MAX_AGE = 0`
   is a Twisted threading decision and `hnsw.iterative_scan` is a pgvector one, so both arrive as
   configurable knobs with defaults rather than as constants. Default to "consumer concern" when
   uncertain.
3. **Test-first.** A case lands in [docs/test-plan.md](docs/test-plan.md), then the test, then the
   code. See [test-first-process.md](../../design/test-first-process.md).
4. **The settings module is the only seam.** `DATABASES` and `DATABASE_ROUTERS` are plain names in a
   module Django executes once, before the app registry exists. `AppConfig.ready()` runs too late —
   both settings are read lazily by `ConnectionHandler` and `ConnectionRouter`, so mutating them
   there works only until something has already touched a connection. The library therefore does its
   work in a function the consumer calls from `settings.py`, and nowhere else.
5. **A spec is data, and must import nothing from Django.** The consumer's `settings.py` imports it
   before `django.setup()`, so a spec module that reaches `models.py` or anything touching the app
   registry raises at that import. The same holds for every module on the settings path, including
   the package `__init__.py` — a spec carries no router reference at all, because `configure()`
   builds the routers itself.
6. **The environment declares the split; the library only reads it.** An alias is on a different
   database from `default` when its own URL is set, or when no `DATABASE_URL` exists at all and every
   alias falls to its own SQLite file. Absence declares as much as presence. Nothing is inferred by
   comparing connection settings.
7. **Routing and migration read one answer.** The set of split aliases decides both which routers are
   active and which aliases need `migrate --database <alias>`. They come from the same call, because
   the failure when they disagree is silent: a router refuses the tables while Django records the
   migrations as applied, leaving a database that looks migrated and holds nothing.
8. **This library logs nothing, and that is an agreed exception to the logging standard.** Evennia's
   `logger.log_file` writes through `deferToThread`, which needs a running Twisted reactor, and every
   part of this library works before one exists — `configure()` while the consumer's settings module
   is still executing, the boot check during `django.setup()`, the migrate helper in a management
   command process that starts no reactor at all. A call opens the file and writes nothing. Measured,
   not reasoned: a 0-byte `cascade.log` beside a demo gamedir that had just refused a migration.

   A mechanism of our own was considered and judged unnecessary. Every failure here is fatal — the
   server does not start, or the command dies — so the exception and its traceback are already in
   front of whoever needs them.

   `log.py` stays, verbatim and uncalled, so the library lints as one of the corpus rather than
   looking like it forgot; its docstring carries this reasoning. The single `log_shim_unused` warning
   is the deliberate note. **Do not "fix" it by adding a call site** — the call would do nothing, and
   `CascadeRouter` is the only thing here that runs with a reactor up, with nothing to report.
9. **`INSTALLED_APPS` is the consumer's, and unvalidatable.** A library left out of it never has its
   `ready()` run, so nothing of ours can notice. Everything after that point is validated as hard as
   it can be — spec fields when `configure()` runs, and the presence cross-check at boot.

## Out of scope

Decided as questions arise — the project is too young for a settled list. Rulings so far:

- **Deciding whether an alias should be split.** That is a deployment decision, made by setting or
  not setting an environment variable. The library reads the decision; it never second-guesses it.
- **Owning any tables of its own.** The library configures other libraries' databases and has no
  models, no migrations and no alias.

## Working conventions

- **Editing design docs.** Update or add design documents whenever an architectural decision is made
  or refined. Capture the *why*, not just the *what*. Index new docs in [docs/INDEX.md](docs/INDEX.md).
- **Don't put implementation detail in this file or README.** Link out to `docs/` instead. Keep
  `CLAUDE.md` and `README.md` stable; let `docs/` churn.
- **License.** BSD 3-Clause. Source files carry an SPDX header on the first line
  (`# SPDX-License-Identifier: BSD-3-Clause`).

## Documentation discipline (load-bearing)

Design documents in `docs/` must reflect decisions **actually discussed and agreed on with the project
owner**. They are not a place to forward-design the system from first principles or extrapolate
"reasonable defaults" from a starting point.

**Rules:**

1. **Only capture what was discussed and agreed.** If the conversation establishes a principle, do not
   extrapolate it into specifics that were not raised — API shapes, naming conventions, adoption
   checklists.
2. **Flag open questions explicitly.** Write `[TBD — needs discussion: <what is open>]` so a future
   session picks the topic up deliberately rather than inheriting an unagreed assumption.
3. **Smaller is better.** Three discussed points captured faithfully beat three discussed points plus
   seven invented ones. Resist filling out sections "for completeness".

This matters more here than in a mature library: the library is a scaffold, so anything written
confidently about an unwritten part would be invention.

## Repository layout

```
evennia-database-cascade/
├── CLAUDE.md                  # this file
├── README.md
├── LICENSE                    # BSD 3-Clause
├── pyproject.toml
├── runtests.py                # standalone test runner (no consumer gamedir needed)
├── docs/                      # design wiki (humans + LLMs)
├── src/
│   └── evennia_database_cascade/
│       ├── __init__.py        # re-exports the consumer-facing surface
│       ├── apps.py            # AppConfig; ready() runs the boot check
│       ├── config.py          # every constant, the settings accessors, check_settings()
│       ├── configure.py       # configure() — the one call a consumer makes
│       ├── discovery.py       # discover_specs / validate_specs
│       ├── log.py             # the logging shim
│       ├── management/
│       │   └── commands/
│       │       └── cascade_migrate.py
│       ├── migrate.py         # migrate_all()
│       ├── resolve.py         # the three rungs, and the split rule
│       ├── router.py          # CascadeRouter
│       ├── spec.py            # AliasSpec
│       └── tests.py           # unit tests (run via runtests.py)
└── tests/                     # standalone test settings (test_settings.py, urls.py)
```

**Everything above is on the settings path except `apps.py`, `migrate.py` and the management
command.** Those three run after `django.setup()`, so they may import Django and they may log. The
rest may do neither — see principles 4, 5 and 8.

## Tools and environment

- Python 3.10+ (pinned via `pyproject.toml`).
- Runtime dependencies: Evennia, and `dj-database-url` for parsing the URLs.
- Tests run through Django's test runner via `python runtests.py` — not pytest.
- Development uses a dedicated venv at `venv/` (gitignored), independent of any consumer game.

## Sibling libraries to reference

- **[../evennia-archive/](../evennia-archive/)** — the library that shaped two of the spec's fields,
  and the one whose tables share names with Evennia's. Read
  [its `installing.md`](../evennia-archive/docs/installing.md) before touching
  `allow_sharing_common_db`, and its `CLAUDE.md` § *Out of scope*, which records the resolution
  helper it is deliberately not writing while it waits for this library.
- **[../evennia-message-bus/](../evennia-message-bus/)** and
  **[../evennia-ai-memory/](../evennia-ai-memory/)** — two of the four hand-rolled cascades this
  library replaces. Their `config.py` is what the resolver is being generalised from, and their
  READMEs carry the unconditional `DATABASE_ROUTERS` append that this library removes.
- **[../evennia-equipment/](../evennia-equipment/)** — the reference shape for the docs surfaces,
  the README, and the numbered `installing.md` spine.
- **`src/game/server/conf/db_config.py`** in the umbrella — the original, resolving five aliases and
  deriving its routers from the result. Not a library, but the working implementation this one is
  extracted from.
