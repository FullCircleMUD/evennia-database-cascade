# Test plan prefilled

**Set aside. Not a commitment.** These cases were drafted in one pass, ahead of any discussion of how
the library decomposes — so they assume units, signatures and behaviour nobody has reviewed. They are
kept as source material: as each unit is worked through, the cases that survive that discussion move
across to [test-plan.md](test-plan.md), which is the real plan.

Nothing here is agreed. Read a case as a proposal, and expect some of them to be wrong about units
that do not end up existing.

Case IDs are provisional too — an ID becomes stable when the case lands in the real plan.

| Prefix | Covers |
|---|---|
| `SM` | The smoke case — install and runner |
| `RS` | `resolve_database` — the three rungs |
| `SL` | The split rule |
| `SP` | `AliasSpec` |
| `DS` | Spec discovery from `INSTALLED_APPS` |
| `CF` | `configure()` |
| `RT` | The router |
| `MG` | The migrate helper |
| `BC` | The boot cross-check |
| `LG` | The logging shim |

## Fixtures

The `RS`, `SL`, `SP` and `CF` cases need no Django and no database — the environment is a plain
mapping passed in as an argument, and the result is a dict compared against an expected one. `DS`,
`RT` and `BC` need a configured Django; `LG` needs Evennia for its positive cases and deliberately
lacks it for `LG-04`.

| Fixture | Purpose |
|---|---|
| `env()` | Builds a plain dict standing in for `os.environ`, so a case names an environment without touching the real one |
| `spec()` | Builds an `AliasSpec` with overridable fields, for the cases that vary one at a time |
| `FakeApp` | An app-shaped object exposing a `db_spec` module, and one that does not |
| `OwnModel` / `ForeignModel` | Model-shaped classes carrying an `_meta.app_label`, for the router cases |
| `RecordingMigrate` | Captures the `call_command` invocations the migrate helper makes, in order |

## SM — smoke

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, unchanged.

## RS — `resolve_database(alias, sqlite_filename, game_dir, env)`

| ID | Case | Test function |
|---|---|---|
| RS-01 | `DATABASE_URL_<ALIAS>` set — the entry is that URL parsed | |
| RS-02 | Only `DATABASE_URL` set — the entry is that URL parsed | |
| RS-03 | Neither set — a SQLite entry at `<game_dir>/server/<sqlite_filename>` | |
| RS-04 | Both set — the alias's own URL wins | |
| RS-05 | The variable read is the alias upper-cased: `ai_memory` reads `DATABASE_URL_AI_MEMORY` | |
| RS-06 | Only the mapping passed in is read; the real environment is never consulted | |

## SL — the split rule

| ID | Case | Test function |
|---|---|---|
| SL-01 | The alias's own URL is set — split | |
| SL-02 | Only `DATABASE_URL` is set — not split | |
| SL-03 | Neither is set — split, because each alias is its own SQLite file | |
| SL-04 | `default` is never in the split set | |

## SP — `AliasSpec`

**Superseded by [test-plan.md](test-plan.md)** on 2026-09-08. The spec was redesigned in discussion:
`exclusive` became `allow_foreign_tables_in_own_db`, a second permission
`allow_sharing_common_db` was added for the library whose tables share names with Evennia's, and the
dotted-path router field was dropped — `configure()` builds the routers, so a spec names none.
Validation moved to `validate_specs`, which has its own `VS` section in the real plan.

## DS — spec discovery

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, expanded from three cases to seven.

## CF — `configure(databases, game_dir, env)`

| ID | Case | Test function |
|---|---|---|
| CF-01 | Returns `DATABASES` carrying an entry per discovered spec | |
| CF-02 | Leaves the `default` entry exactly as the consumer set it | |
| CF-03 | Returns `DATABASE_ROUTERS` holding a router for each split alias and no others | |
| CF-04 | No alias split — the router list is empty | |
| CF-05 | Every alias split — one router each, in spec order | |
| CF-06 | Returns the split alias list, so the migrate step reads it rather than recomputing it | |
| CF-07 | Called with no specs discovered — returns the databases it was given, unchanged, and an empty router list | |

## RT — the router

| ID | Case | Test function |
|---|---|---|
| RT-01 | `db_for_read` returns the alias for a model of its own app | |
| RT-02 | `db_for_read` and `db_for_write` return `None` for a foreign model | |
| RT-03 | `allow_migrate` is `True` for its own app on its own alias | |
| RT-04 | `allow_migrate` is `False` for its own app on any other alias | |
| RT-05 | `exclusive=True` — `allow_migrate` is `False` for a foreign app on its alias | |
| RT-06 | `exclusive=False` — `allow_migrate` returns `None` for a foreign app, so other apps may migrate in | |
| RT-07 | `allow_relation` is `True` only when both models are its own, and `None` otherwise | |
| RT-08 | Two routers built from different specs each answer only for their own app | |

## MG — the migrate helper

| ID | Case | Test function |
|---|---|---|
| MG-01 | Runs a bare `migrate` first | |
| MG-02 | Then one `migrate --database <alias>` per split alias | |
| MG-03 | No split aliases — the bare call and nothing else | |
| MG-04 | The split list is the one `configure()` produced, not a second derivation | |

## BC — the boot cross-check

| ID | Case | Test function |
|---|---|---|
| BC-01 | Every app carrying a `db_spec` has its alias in `settings.DATABASES` — passes silently | |
| BC-02 | An app carrying a `db_spec` whose alias is absent — raises `ImproperlyConfigured` naming the app and the alias | |
| BC-03 | Two such apps — one raise, naming both | |
| BC-04 | An app absent from `INSTALLED_APPS` is invisible to the check — the documented gap, pinned so it is not later read as a bug | |

## LG — the logging shim

| ID | Case | Test function |
|---|---|---|
| LG-01 | A call reaches `logger.log_file` with `cascade.log` as the filename | |
| LG-02 | The level prefixes the message as `[LEVEL] message` | |
| LG-03 | An unknown level coerces to `INFO` rather than raising | |
| LG-04 | Outside an Evennia engine the call is a silent no-op | |
| LG-05 | `trace=True` inside an `except` block appends the traceback | |
| LG-06 | `trace=True` outside one appends nothing | |

## Open decisions

Not attached to a case, because the behaviour has not been agreed. Each becomes cases when it is.

- **Is the alias fixed by the declaring library, or overridable by the consumer?** Fixed keeps the
  environment variable name predictable. Overridable is what two libraries choosing the same alias
  would need — and decides whether a collision is refused, and by whom.
- **How does a spec say the middle rung does not apply to it?** `evennia-archive` clones Evennia's
  schema, so sharing the game's database hands it the live tables rather than a second set of its
  own. Its cascade is two rungs. A spec with no way to declare that would resolve it silently onto
  the game's database.
- **Does `configure()` also resolve `default`?** `CF-02` says it does not, which is the conservative
  reading. FCM's own settings resolves `default` from a bare `DATABASE_URL` before doing anything
  else, so if that moves in here the case changes.
- **Does a spec carry connection knobs?** `CONN_MAX_AGE` and the Postgres session options were agreed
  to be configurable rather than constants, with `fcm-xrpl`'s `XRPL_CONN_MAX_AGE` as the precedent.
  Whether they sit on the spec, and what the defaults are, is not settled.
- **What happens to a router the consumer added themselves?** `configure()` returns a list built from
  the specs. Whether it preserves entries already in `DATABASE_ROUTERS` was not discussed.
