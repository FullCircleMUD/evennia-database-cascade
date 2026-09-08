# Installing

What a game does to run this library, and what a library that owns tables does to be found by it.

**`configure()` is not built yet.** Steps 1, 2, 4 and 5 describe the agreed design so a consumer can
see the shape and a session building it has something to build against — treat those code blocks as a
specification. Step 3, the spec itself, is real and works today.

## 1. Install the package

Nothing is published yet, so install from a checkout:

```
pip install -e path/to/evennia-database-cascade
```

A library that declares a spec depends on this one, so installing that library brings this in.

## 2. Add the app

In your settings:

```python
INSTALLED_APPS += ["evennia_database_cascade"]
```

Alongside every library whose tables you want placed — each of those is an app in its own right and
goes in the same list.

This is what runs the boot cross-check. Without it the library still resolves your aliases, and
nothing checks the result.

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

Two fields are required and three have defaults:

| Field | Default | What it says |
|---|---|---|
| `app_label` | required | The Django app label the router matches models on — `model._meta.app_label` |
| `alias` | required | The `DATABASES` key. `migrate --database <alias>` takes it, and `DATABASE_URL_<ALIAS>` derives from it |
| `sqlite_filename` | `<alias>.db3` | The file this alias falls back to when no URL names a database for it |
| `allow_sharing_common_db` | `True` | May this alias live in the database the common URL names? |
| `allow_foreign_tables_in_own_db` | `False` | May another app's tables be migrated into this alias's database? |

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
from evennia_database_cascade import configure

DATABASES, DATABASE_ROUTERS = configure(DATABASES, GAME_DIR, os.environ)
```

It scans `INSTALLED_APPS` for apps declaring a spec, resolves each one's alias, and returns
`DATABASES` with those entries filled in and `DATABASE_ROUTERS` holding the routers for exactly the
aliases that need one.

`configure()` takes one more argument, `common_url_var`, defaulting to `"DATABASE_URL"` — the
variable naming the database every alias shares when it has none of its own. A game using a different
name for that passes it here, once, rather than repeating it in every spec.

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
evennia migrate
evennia migrate --database <alias>   # once per alias on its own database
```

An alias sharing the game's database is covered by the bare call. An alias on its own is not — its
router refuses those tables everywhere else, so it needs the second form. The library reports which
aliases those are, so the list is read rather than remembered.

## Required settings

**None.** This library reads no Django settings of its own. Everything it needs arrives as arguments
to `configure()` or as the environment variables in step 5 — deliberately, because the settings
module is still executing when this runs, so nothing can read `settings.X` at that point anyway.

## Optional settings

**None**, for the same reason. The two connection knobs that would otherwise be settings —
`CONN_MAX_AGE` and the Postgres session options — are planned as fields on a spec, so they travel
with the library that needs them rather than becoming another thing a consumer has to set.
`[TBD — needs discussion: whether they sit on the spec, and what the defaults are.]`

## What is not checked for you

- **That the library is in `INSTALLED_APPS`.** Leave it out and `AppConfig.ready()` never runs, so
  the boot cross-check never happens. This is the one gap nothing can close: a library that is not
  installed cannot notice that it is not installed.
- **That `configure()` is called after your `INSTALLED_APPS` edits.** A spec added below the call is
  invisible to it. The boot check catches the *consequence* — an app with a spec whose alias is
  missing from `DATABASES` — and names the app, but it cannot see the ordering that caused it.
- **That `DATABASE_URL_<ALIAS>` points where you meant.** The environment is the declaration; the
  library reads it and does not second-guess it. A URL naming the wrong host resolves cleanly and
  fails at first connection.
- **That you ran the per-alias migrations.** The library reports which aliases need one. Skipping it
  leaves that alias with no tables.
- **That a library's `db_spec` says what its author intended.** A spec claiming the wrong alias, or
  declaring `allow_sharing_common_db=True` for a library whose tables collide with Evennia's, is
  valid as far as this library can tell.
