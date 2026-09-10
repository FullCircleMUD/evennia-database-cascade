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

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, reworked in discussion.


## SL — the split rule

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, reworked in discussion.


## SP — `AliasSpec`

**Superseded by [test-plan.md](test-plan.md)** on 2026-09-08. The spec was redesigned in discussion:
`exclusive` became `allow_foreign_tables_in_own_db`, a second permission
`allow_sharing_common_db` was added for the library whose tables share names with Evennia's, and the
dotted-path router field was dropped — `configure()` builds the routers, so a spec names none.
Validation moved to `validate_specs`, which has its own `VS` section in the real plan.

## DS — spec discovery

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, expanded from three cases to seven.

## CF — `configure(databases, game_dir, env)`

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, reworked in discussion.


## RT — the router

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, reworked in discussion.


## MG — the migrate helper

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, reworked in discussion.


## BC — the boot cross-check

**Transferred to [test-plan.md](test-plan.md)** on 2026-09-08, reworked in discussion.


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

- ~~**Is the alias fixed by the declaring library, or overridable by the consumer?**~~ Settled, and
  narrower than it sounded. **A spec is fixed input as far as this library is concerned** — we read
  what the declaring library declared and add no mechanism for anyone else to change it. Whether that
  library lets its own consumers influence what it puts in its spec is that library's business, and
  it needs nothing from us: it can read whatever setting it likes and build its spec from the answer.
  A collision between two libraries is refused loudly — `VS-03` — and stays refused until one of them
  changes.
- ~~**How does a spec say the middle rung does not apply to it?**~~ Settled: `allow_sharing_common_db`,
  refusing that rung rather than falling through to SQLite. Cases `RS-09` to `RS-11`.
- ~~**Does `configure()` also resolve `default`?**~~ Settled: it does not. `default` is the one entry
  Evennia already provides, and owning it would mean owning an edge case that is not this library's.
  Case `CF-02`.
- ~~**Does a spec carry connection knobs?**~~ Settled: both do — `conn_max_age` and
  `session_options`, each defaulting to the `UNSET` sentinel. `configure()` carries the game-wide
  default for aliases whose spec said nothing. Cases `SP-11` to `SP-14`, `RS-13` to `RS-20`,
  `CF-14`, `CF-15`.
- ~~**What happens to a router the consumer added themselves?**~~ Settled: preserved. `configure()`
  takes a `routers` argument and appends ours after theirs, because replacing the list would drop a
  router they wrote and send whatever it routed to `default` silently. Case `CF-16`.
