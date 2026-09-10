# Progress

Reverse-chronological milestone log. Newest first. Each entry states what became true and what proves
it.

## 2026-09-10 — Proved end to end, stopped pretending to log, and made the knobs configurable

126 tests. The design questions are closed; what is left is verification and the retrofits.

**A demo gamedir now exercises the whole thing** against a real `django.setup()`. Two consumers
deliberately: `demo_library`, a throwaway distribution declaring this library as a dependency, which
is the only way to reach the boot check's `Requires-Dist` path; and `demo_game`'s own app, which is
not a distribution and therefore cannot. After `cascade_migrate`, `evennia.db3` held 42 tables with
neither demo table among them, against one each in `demolib.db3` and `demogame.db3`.

It found two things reasoning had not. **Evennia's own `INSTALLED_APPS` carries AppConfig paths** —
`evennia.web.utils.adminsite.EvenniaAdminApp` — not only package names, and treating one as a missing
app killed `django.setup()` on a stock gamedir. Entries now drop trailing segments until they reach a
package. Case `DS-12`.

**And the logging shim raises before `django.setup()`.** `logger.log_file` writes through
`deferToThread`, which needs a running reactor, and every part of this library works before one
exists. A call opened the file and wrote nothing — a 0-byte `cascade.log`. The four call sites are
gone, `BC-10`, `BC-11` and `MG-07` are retired for asserting a feature the library does not have, and
`log.py` stays verbatim and uncalled with the reasoning in its docstring. Principle 8.

**Both connection knobs are configurable, defaulted by the game and overridable per alias.**
`conn_max_age` and `session_options`, each defaulting to an `UNSET` sentinel on the spec — `None`
could not be the sentinel, because Django reads it as *persist forever*. `configure()` carries the
game-wide default for aliases whose spec said nothing, which is the consumer's only lever over an
alias belonging to a library they did not write. Session options render to `-c name=value` and are
appended to whatever the URL put in `OPTIONS`, so a `?sslmode=require` survives. Cases `SP-11` to
`SP-14`, `RS-13` to `RS-20`, `CF-14`, `CF-15`.

**`required_extensions` refuses a migration against a database missing what it needs**, across every
alias rather than only the split ones — a shared alias's extension lives on the common database too.
It only reports: creating an extension needs superuser, so the message carries the command. That is
what retires the hardcoded `_VECTOR_ALIASES` tuple in FCM's deploy script. Cases `SP-15`, `SP-16`,
`MG-11` to `MG-14`.

**Two smaller corrections.** A consumer's own routers were being replaced rather than appended to,
which would have dropped a router they wrote and sent whatever it routed to `default` silently —
`configure()` now takes them and puts ours after. And an alias that cannot name an environment
variable is refused, since the alias *becomes* `DATABASE_URL_<ALIAS>` and one no shell can export is
one nobody can deploy. Cases `CF-16` and `VS-09`.

## 2026-09-08 — The rest of it: resolution, routing, configure, boot and migrate

101 tests. Every piece is built; no consumer game runs it yet.

**`resolve_database`** places one alias through the three rungs — its own URL, the common one, then a
SQLite file under `<game_dir>/server/`. A variable set to an empty string counts as unset, because an
exported-but-empty variable is an ordinary deployment state and the parser should never see one. Its
single refusal is a spec with `allow_sharing_common_db=False` landing on the shared rung: falling
through to SQLite instead would put a production database in a local file on a deployment that is
otherwise not using one. Cases `RS-01` to `RS-12`.

**`is_split` and `split_aliases`** answer whether an alias is on a database of its own, from the
environment alone. Two callers need that answer in two processes, and the failure when they disagree
is silent — a router refusing an alias's tables while Django records its migrations as applied.
Cases `SL-01` to `SL-10`.

**`CascadeRouter`** replaces the five hand-written routers across FCM with one instance per spec.
Django ships no router implementation, so those five were the same twenty-five lines with three
values changed, and all three are on the spec. Routing queries and permitting migrations stay
separate: for the archive it lets Evennia's forty-two tables be created there while still sending
every `ObjectDB` query to `default`. Cases `RT-01` to `RT-13`.

**`configure()`** is the five steps in eight lines, and the only call a consumer makes. It copies the
databases dict rather than editing the one it was handed. Its one check of its own compares each
alias's resolved SQLite path against `DATABASES["default"]["NAME"]` — not against the literal
`evennia.db3`, which is Evennia's default rather than a fixed name, so a consumer who renamed their
game database would have got no protection from a hardcoded check. Cases `CF-01` to `CF-13`.

**The boot check** asks two questions at `ready()`, the first point where Django is up. Did a library
that depends on us forget to declare anything — read off its distribution's `Requires-Dist`, skipping
optional extras? And did every declared alias reach `DATABASES`? Cases `BC-01` to `BC-12`.

**`evennia cascade_migrate`** runs the bare migrate and then one per split alias, deriving that list
through the same `split_aliases` that chose the routers. Options are forwarded to Django's `migrate`
untouched; `database` is refused, since deciding that is the helper's whole job. Cases `MG-01` to
`MG-10`.

**Two things were found by running it rather than by reasoning.**

Evennia's own `INSTALLED_APPS` carries AppConfig paths — `evennia.web.utils.adminsite.EvenniaAdminApp`
— not only package names. Django accepts both; `discover_specs` did not, and `django.setup()` died on
a stock gamedir. Entries now drop trailing segments until they reach a package, which handles
`<module>.<Class>` and `<package>.apps.<Class>` without importing the class or asking Django, neither
of which is available from a settings module. Case `DS-12`.

And the logging shim raises `ImproperlyConfigured` before `django.setup()`, tested rather than
assumed. So nothing on the settings path logs at all: those failures raise, and the traceback is the
record. The shim was **not** given a second `except` for it — it stays verbatim across the libraries,
and one that quietly worked everywhere would invite calls from where they do not belong. Principle 8.

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
