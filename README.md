# evennia-database-cascade

One settings call. SQLite locally, Postgres in production, a database of its own when you want one —
decided by the environment rather than by editing settings.

## Status

**Three units built, and not yet usable.** `discover_specs` finds the specs the installed apps
declare, `AliasSpec` is what a library declares, and `validate_specs` refuses a set that says
something unusable. 30 tests. The resolver, the router, `configure()` and the migrate helper are all
still to come, so nothing resolves a database yet. Nothing is published. See
[docs/progress.md](docs/progress.md).

## The problem it solves

An Evennia library that owns tables usually wants them somewhere other than the game database —
so they survive a world rebuild, or so more than one instance can read them. Arranging that means a
`DATABASES` entry, a router, and remembering that an alias on its own database needs its own
`migrate` call.

Every library that needs it writes the same resolution code, and every consumer pastes the same two
snippets into their settings. Four copies of it exist across FullCircleMUD today, and three of them
are missing the router half — which fails quietly: the router refuses the tables while Django records
the migrations as applied, leaving a database that looks migrated and holds nothing.

## The approach

A library that owns tables declares a spec — its app label, its alias, and what it will and will not
share. The game calls `configure()` once in its settings. Each alias then lands where the environment
says:

```
DATABASE_URL_<ALIAS>   set  →  a database of its own
DATABASE_URL           set  →  the game's database
neither                     →  a local SQLite file
```

Which routers are active and which aliases need their own `migrate` both follow from that, from one
answer, so they cannot disagree.

Nothing in the game changes between the three shapes. Moving an alias onto its own Postgres instance
is one environment variable and a migrate.

## Is this for you?

Probably, if you run Evennia with libraries that own their own tables, or you run one game in more
than one shape — SQLite on a laptop, one Postgres on a small box, a separate instance for the
database that matters — and would rather that difference lived in the environment than in your
settings file.

Probably not, if your game and every library you run are content in the single game database. There
is nothing here for you.

## Install

Nothing is published yet. Editable install for development against a checkout:

```
git clone https://github.com/FullCircleMUD/evennia-database-cascade.git
cd evennia-database-cascade
python -m venv venv
# Activate the venv (platform-specific)
pip install evennia
pip install -e .
python runtests.py
```

Then follow [docs/installing.md](docs/installing.md) — add the app, declare the specs, make the call.

## Learn more

- [docs/INDEX.md](docs/INDEX.md) — the design wiki.
- [docs/installing.md](docs/installing.md) — everything a consumer does, in order.
- [docs/test-plan.md](docs/test-plan.md) — every behaviour the library commits to, case by case.
- [docs/interoperability.md](docs/interoperability.md) — this library against every sibling.

## License

BSD 3-Clause. See [LICENSE](LICENSE).
