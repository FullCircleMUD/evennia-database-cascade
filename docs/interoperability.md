# Interoperability

This library against every sibling library in `libraries/`.

**What this library does, for a sibling deciding whether it matters.** It owns no tables, runs no
migrations and issues no ORM writes. All of its work happens inside the consumer's settings module,
before `django.setup()` — it reads the environment, writes `DATABASES` and `DATABASE_ROUTERS`, and
stops. It starts no scripts, dispatches nothing off the reactor thread and does no network work. It
imports Evennia only in its logging shim.

The coupling runs the opposite way from usual: siblings depend on this library, and this library
imports none of them. The dividing line throughout is whether a sibling owns tables — one with no
models has nothing for this library to place.

**Everything is built and nothing is adopted.** No sibling depends on this library yet, so every
statement below about what one *would* do on adopting it is design rather than description, and
should be re-confirmed at the point it actually happens.

Each section names the relationship — **hard dependency**, **optional integration**, or **no
coupling** — followed either by the constraints that apply or by an explicit clearance stating *why*
it is clear in terms of what this library does.

## evennia-ai-memory

**Hard dependency, in the other direction** — ai-memory would depend on this library, not the
reverse.

It owns the `ai_memory` alias and its own router, and its `config.py` implements the three rungs
itself. Adopting this library means deleting that block and its router class in favour of a spec, and
rewriting the `DATABASE_ROUTERS` instructions in its README, which today tell a consumer to append
the router unconditionally.

Its alias is the one carrying vector columns, and its spec is the one that will declare
`required_extensions=("vector",)`. `evennia cascade_migrate` reads that and refuses before migrating
if the database does not have the extension, naming the `CREATE EXTENSION` command to run — creating
one needs superuser, which an application role deliberately is not.

That is what retires the hardcoded `_VECTOR_ALIASES = ("ai_memory",)` in FCM's `deploy_migrate.py`:
once ai-memory declares it, the library that knows it needs the extension is the one that says so.

## evennia-archive

**Hard dependency, in the other direction** — and the sibling that shaped two of the spec's fields.

The archive is a clone of Evennia's schema, so its tables share names with the game's. Pointing its
alias at the game's database does not give it a second set of tables, it hands it the live ones. Its
spec therefore declares:

```python
allow_sharing_common_db=False          # DATABASE_URL alone is refused, not followed
allow_foreign_tables_in_own_db=True    # Evennia's own tables belong in the archive
```

Both fields exist because of this library — the first because the middle rung is not universal, the
second because `ArchiveRouter` is the one router that deliberately lets foreign apps in. The
constraint itself is archive's and is documented in
[its `installing.md`](../../evennia-archive/docs/installing.md).

Archive's `CLAUDE.md` records its missing `archive_database()` helper as a deliberate deferral
pending this library, rather than an oversight — so the helper should not be written there.

## evennia-calendar

**No coupling.** Neither library imports the other. Calendar turns Evennia's game time into a date,
season and time of day — it computes from `gametime` and stores nothing of its own. No `models.py`,
no router, nothing persisted through the ORM, so there is no alias for this library to place.

## evennia-database-cascade

This library.

## evennia-equipment

**No coupling.** Neither library imports the other. Equipment owns no tables — its state is Evennia
attributes on objects the consumer already has — so it has nothing for this library to place.

## evennia-llm-service

**No coupling.** Neither library imports the other. It owns no models, so it has no tables for this
library to place.

## evennia-message-bus

**Hard dependency, in the other direction** — message-bus would depend on this library.

It owns the `messagebus` alias and its own router, and reimplements the three rungs in its own
`config.py`. Adopting this library means a spec in place of both, and the same README rewrite as
ai-memory.

The bus exists to be read by more than one instance, so its alias is the one most likely to be split
in a real deployment. That is a deployment decision expressed in the environment and needs nothing
from either library.

## evennia-mob-spawner

**No coupling.** Neither library imports the other. Mob-spawner owns no models, so it has no tables
for this library to place.

## evennia-portal-multiplex

**No coupling.** Neither library imports the other. It owns no models, and its work is on the Portal
rather than in the ORM.

## evennia-scaling

**No coupling, and settled rather than pending.** Scaling's `Ticket` table is in the consumer's game
database deliberately: a ticket is written and read by one instance seconds apart, and after a wipe
there is no handoff still in flight, so it meets neither test for taking an alias. Its `CLAUDE.md`
rules it out of scope, `TK-05` pins it, and the ruling says plainly not to "fix" it into an alias.

So there is nothing here for this library to place, and a later change of mind would be a change to
scaling's design rather than a gap in this section.

## evennia-shards

**No coupling anticipated.** Shards has models but no router, so its tables sit in the game database
and there is no alias to resolve.

Worth noting for whoever finishes this library: shards documents that off-thread ORM work runs
unscoped. Nothing here dispatches off the reactor — all of this library's work happens in the
consumer's settings module, before there is a reactor — so that constraint does not reach it.

## evennia-survival

**No coupling.** Neither library imports the other. Survival owns no models; it stores its state on
Evennia attributes, which are in the game database by definition.

## evennia-targeting

**No coupling.** Neither library imports the other. Targeting filters candidate lists already in
hand, owns no models and issues no query this library would see.

## evennia-world-builder

**No coupling.** Neither library imports the other. World-builder writes Evennia objects into the
game database and owns no tables of its own.

## evennia-yaml-reader

**No coupling.** Neither library imports the other. yaml-reader depends only on `pyyaml`, has no
Evennia dependency and touches no database.

## fcm-telemetry-spawn

**No coupling anticipated.** It owns no models today and is parked pending `fcm-xrpl`'s shape. If it
takes an alias when it resumes, it becomes a consumer of this library like any other.

## fcm-xrpl

**Hard dependency, in the other direction** — fcm-xrpl would depend on this library.

It owns the `xrpl` alias and its own router, and implements the three rungs in its own `config.py`.
It is also the sibling that already treats `CONN_MAX_AGE` as a setting rather than a constant
(`XRPL_CONN_MAX_AGE`), which is the precedent for that value becoming a spec field here rather than a
constant of this library's.

Its alias holds ownership records, so it is among the likeliest to be split onto separate hardware —
again a deployment decision, expressed in the environment.
