# Installing

What a game does to run this library, and what a library that owns tables does to be found by it.

## 1. Install the package

Nothing is published yet, so install from a checkout:

```
pip install -e path/to/evennia-database-cascade
```

A library that declares a spec depends on this one, so installing that library brings this in.

## 2. Add the app

In your settings, alongside every library whose tables you want placed:

```python
INSTALLED_APPS += ["evennia_database_cascade"]
```

This is what runs the boot check. Without it your aliases are still resolved — `configure()` does
that — but nothing checks the result afterwards.

## 3. Declare a spec, if your own game owns tables

A library that owns tables ships this already, and you do nothing. A consumer game that owns tables
declares one the same way. Put it in a module called `db_spec` that imports nothing from Django:

```python
# world/db_spec.py
from evennia_database_cascade import AliasSpec

SPEC = AliasSpec(
    app_label="my_app",
    alias="my_alias",
)
```

Two fields are required and six have defaults:

| Field | Default | What it says |
|---|---|---|
| `app_label` | required | The Django app label the router matches models on — `model._meta.app_label` |
| `alias` | required | The `DATABASES` key. `migrate --database <alias>` takes it, and `DATABASE_URL_<ALIAS>` derives from it |
| `sqlite_filename` | `<alias>.db3` | The file this alias falls back to when no URL names a database for it |
| `allow_sharing_common_db` | `True` | May this alias live in the database the common URL names? |
| `allow_foreign_tables_in_own_db` | `False` | May another app's tables be migrated into this alias's database? |
| `conn_max_age` | the game's | How long this alias's connection is kept before being closed. Left alone, the value passed to `configure()` applies |
| `session_options` | the game's | Postgres session parameters for this alias, as `{name: value}`. Left alone, the value passed to `configure()` applies |
| `required_extensions` | none | Postgres extensions the database behind this alias must already have, by name |

The two `allow_` fields are the outbound and inbound halves of the same question, and they are
independent — a library can want either, both or neither.

**Set `allow_sharing_common_db=False`** where the library's tables share names with the framework's.
Pointing such an alias at the game's database does not give it a second set of tables, it hands it
the live ones. `evennia-archive` is the case: it is a clone of Evennia's schema, so `objectdb` in the
archive and `objectdb` in the game are the same forty-two table names.

**Set `allow_foreign_tables_in_own_db=True`** only where that is the point — the same schema clone is
the example, since Evennia's own tables are exactly what belongs in the archive.

## 4. Make the call

One call, after your `INSTALLED_APPS` edits, in the same settings module:

```python
import os
from evennia_database_cascade import configure

DATABASES, DATABASE_ROUTERS = configure(
    DATABASES, INSTALLED_APPS, GAME_DIR, os.environ
)
```

It scans `INSTALLED_APPS` for apps declaring a spec, validates the set, resolves each alias, and
returns `DATABASES` with those entries filled in and `DATABASE_ROUTERS` holding a router for exactly
the aliases that need one. Your `default` entry is untouched, and the dict you passed in is not
modified — the return is a copy.

**If you already have routers of your own**, hand them over so they survive:

```python
DATABASE_ROUTERS = ["world.routers.MyRouter"]

DATABASES, DATABASE_ROUTERS = configure(
    DATABASES, INSTALLED_APPS, GAME_DIR, os.environ, routers=DATABASE_ROUTERS
)
```

Yours stay at the front and ours are appended. Leave the argument off and the return replaces the
list, which is fine when it held nothing and a silent loss when it did.

**Order matters and nothing can check it.** A spec belonging to an app added below this line is not
there to be found. Keep the call at the end of the database section of your settings.

**Why it cannot live anywhere else.** `DATABASES` and `DATABASE_ROUTERS` are read before the app
registry exists, so `AppConfig.ready()` is too late — see principle 4 in [CLAUDE.md](../CLAUDE.md).

## 5. Choose where each alias lives

Per alias, in the deployment's environment. Three rungs, first match wins:

| Set | Where the alias lands |
|---|---|
| `DATABASE_URL_<ALIAS>` | its own database, at that URL |
| `DATABASE_URL` | the game's database |
| neither | a SQLite file under `<GAME_DIR>/server/` |

The variable name is the alias, upper-cased and prefixed: alias `ai_memory` reads
`DATABASE_URL_AI_MEMORY`. You do not choose that name — it derives from the alias, so it is the same
shape for every library you install.

Set nothing and every alias is a separate SQLite file, which is the local development case and needs
no configuration at all.

An alias whose spec sets `allow_sharing_common_db=False` refuses the middle rung rather than
following it, so `DATABASE_URL` alone is an error for it. Give it its own variable or leave it on
SQLite.

## 6. Migrate

```
evennia cascade_migrate
```

It runs a bare `migrate`, then `migrate --database <alias>` for every alias on a database of its own,
and reports which those were. Options are forwarded, so `--verbosity 2` and `--noinput` work as
usual.

**Before any of that it checks required extensions**, across every alias, and refuses if one is
missing — naming the extension, the database, and the `CREATE EXTENSION` command to run. It only
reports: creating an extension needs superuser, which an application role deliberately is not. The
refusal comes first because a migration creating a column of that type fails halfway rather than
cleanly.

Doing it by hand is the same two steps:

```
evennia migrate
evennia migrate --database <alias>   # once per alias on its own database
```

An alias sharing the game's database is covered by the bare call. An alias on its own is not — its
router refuses those tables everywhere else, so it needs the second form. Miss one and Django records
those migrations as applied with no tables created, and nothing errors.

A deploy script with its own diagnostics can call `migrate_all()` directly rather than the command;
it is the same code, and the command is a four-line wrapper.

## Required settings

**None.** Everything the library needs arrives as arguments to `configure()` or as the environment
variables in step 5 — deliberately, since the settings module is still executing when `configure()`
runs, so nothing can read `settings.X` at that point.

## Optional settings

**`CASCADE_COMMON_URL_VAR`** — the name of the variable holding the shared database. Defaults to
`DATABASE_URL`.

Declare it and pass it in, so one value serves both processes:

```python
CASCADE_COMMON_URL_VAR = "DATABASE_URL_SHARD0"

DATABASES, DATABASE_ROUTERS = configure(
    DATABASES, INSTALLED_APPS, GAME_DIR, os.environ,
    common_url_var=CASCADE_COMMON_URL_VAR,
)
```

It is a setting rather than only an argument because the value has to be known twice: `configure()`
reads it from your settings module, and `evennia cascade_migrate` runs later in a different process
and reads it back from the same place.

**Where this matters:** a deployment running several instances from one codebase — a router and a
shard, each with its own settings module and its own game database. Each declares its own value, and
each is launched with `--settings`. Aliases genuinely shared between them carry their own
`DATABASE_URL_<ALIAS>` and never reach this rung at all.

## The connection lifetime

Not a setting — an argument, because only `configure()` reads it:

```python
DATABASES, DATABASE_ROUTERS = configure(
    DATABASES, INSTALLED_APPS, GAME_DIR, os.environ, default_conn_max_age=0
)
```

`0` is the default and closes the connection at the end of each unit of work. That is the safe end of
the scale and the right answer for Evennia: database work is dispatched to short-lived Twisted worker
threads, and a connection persisted there is never reconsidered and never handed back. FullCircleMUD
reached its Postgres connection limit before setting it, and the game locked up because nothing new
could connect.

Raise it only with that in mind. `None` means keep connections forever.

A single library whose access pattern genuinely differs can override it on its own spec, and only
that alias changes. Note that `conn_max_age=None` on a spec means *persist forever* — saying nothing
is the default, and the two are different.

## Postgres session options

The same shape, for parameters set on the connection itself:

```python
DATABASES, DATABASE_ROUTERS = configure(
    DATABASES, INSTALLED_APPS, GAME_DIR, os.environ,
    default_session_options={"statement_timeout": "5s"},
)
```

Empty by default, because no session parameter is universal. They render to `-c name=value` pairs and
are **appended** to whatever the URL already put in `OPTIONS` — so a `?sslmode=require` survives a
library setting a parameter of its own. Skipped entirely on SQLite, where `OPTIONS` means something
else and a libpq string breaks the connection.

A library sets its own on its spec, and that replaces the game-wide value for that alias.
`evennia-ai-memory` is the case: a filtered pgvector search asks the HNSW index for candidates before
applying the filter, so it returns however few survive — FCM measured 1 row returned of 5 requested,
across 100k rows. `hnsw.iterative_scan` keeps pulling until the filter yields enough, and it belongs
to whichever library stores the vectors rather than to the deployment.

## What is not checked for you

- **That the library is in `INSTALLED_APPS`.** Leave it out and `AppConfig.ready()` never runs, so
  the boot check never happens. This is the one gap nothing can close: a library that is not
  installed cannot notice that it is not installed.
- **That `configure()` is called after your `INSTALLED_APPS` edits.** A spec added below the call is
  invisible to it. The boot check catches the *consequence* — an app with a spec whose alias is
  missing from `DATABASES` — and names the app, but it cannot see the ordering that caused it.
- **That your own game's `db_spec` exists.** A library that depends on this one and ships no spec is
  caught at boot, by reading its distribution's requirements. A gamedir is not a distribution, so
  there is nothing to read and nothing to check.
- **That `DATABASE_URL_<ALIAS>` points where you meant.** The environment is the declaration; the
  library reads it and does not second-guess it. A URL naming the wrong host resolves cleanly and
  fails at first connection.
- **That two instances sharing a database run the same library versions.** One can apply a migration
  the other does not know about. True of any shared database, and not visible from inside one
  instance.
- **That a library's spec says what its author intended.** A spec claiming the wrong alias, or
  allowing the shared rung for a library whose tables collide with Evennia's, is valid as far as this
  library can tell.

## What you see when something is wrong

**This library writes no log file.** Not at boot, not during a migration, not ever. `cascade.log`
will be created and stay empty; do not go looking in it.

Every failure raises instead, and every failure is fatal — a bad spec or a refused alias stops the
settings module, the boot check stops `django.setup()`, and a failed migration stops the command. So
the exception and its traceback are the record, and they are already in front of you.

Why there is no log: Evennia writes log files through the Twisted reactor, and everything this
library does happens before one exists.
