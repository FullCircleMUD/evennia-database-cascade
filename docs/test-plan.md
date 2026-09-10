# Test plan

Every test case the library commits to covering, and the test function that covers it. The library is
built test-first: cases are agreed here, tests are written against them, then the implementation is
written to pass. The **Test function** column is the auditable trail — it is filled in as each test is
written, so an empty cell means the case is agreed but not yet covered.

Case IDs are stable and referenceable. Do not renumber; retire an ID rather than reuse it. Every test
function carries its case ID as its docstring, so the trail reads in both directions.

All test functions live in `src/evennia_database_cascade/tests.py`.

**This plan is built one unit at a time, as each is discussed and agreed.** A case arrives here only
after the behaviour it describes has been reviewed. Cases drafted ahead of that discussion are held
in [test-plan-prefilled.md](test-plan-prefilled.md) and moved across as each unit is worked through —
that file is source material, not a commitment.

| Prefix | Covers |
|---|---|
| `SM` | The smoke case — install and runner |
| `DS` | `discover_specs` — finding the specs the installed apps declare |
| `SP` | `AliasSpec` — what a library declares about its alias |
| `VS` | `validate_specs` — judging the specs once they are all in hand |
| `RS` | `resolve_database` — the three rungs, for one spec |
| `SL` | `is_split` and `split_aliases` — which aliases are on a database of their own |
| `RT` | `CascadeRouter` — one parameterised router, built from a spec |
| `CF` | `configure` — the one call a consumer makes, tying the rest together |
| `BC` | `check_settings` — the boot check, in `AppConfig.ready()` |
| `MG` | `migrate_all` and `evennia cascade_migrate` — reaching every split alias |
| `LG` | `cascade_log` — the logging shim |

## Fixtures

The fake objects the suite needs, named and purposed. Empty beyond the smoke case: fixtures arrive
with the unit that needs them.

| Fixture | Purpose |
|---|---|
| `AppTree` | Builds throwaway app packages on `sys.path` and removes them afterwards. Real packages with real `db_spec.py` files, so the cases exercise the import machinery rather than a stand-in for it |
| `SPEC_MODULE` | The source of a `db_spec` module as a consumer library would write one — a spec object carrying an `alias`. Deliberately a local stand-in, not the library's own spec type, so discovery's cases do not wait on it |
| `RAISING_SPEC_MODULE` | A `db_spec` that raises on import, for DS-06 |
| `BROKEN_IMPORT_SPEC_MODULE` | A `db_spec` whose own import fails, for DS-08 and DS-09 |
| `spec_module_source` | The source of a `db_spec` declaring a **real** `AliasSpec`. The CF cases need it because resolution reads fields off the spec |
| `django_imports` | Every Django import in a module, read off its AST. Importing proves nothing here — Django is configured inside the suite |
| `model` | A model-shaped object carrying an app label, for the router cases |

## SM — smoke

| ID | Case | Test function |
|---|---|---|
| SM-01 | The installed package imports and carries `__version__` | `test_package_imports_and_declares_a_version` |

## DS — `discover_specs(installed_apps)`

| ID | Case | Test function |
|---|---|---|
| DS-01 | An app whose `db_spec` module exists contributes its spec | `test_an_app_declaring_a_spec_contributes_it` |
| DS-02 | An app without one is skipped, and nothing is raised | `test_an_app_without_a_db_spec_is_skipped` |
| DS-03 | Several apps declaring one — a list, in `INSTALLED_APPS` order | `test_specs_come_back_in_installed_apps_order` |
| DS-04 | No app declares one — an empty list | `test_no_app_declaring_one_returns_an_empty_list` |
| DS-05 | Two apps declaring the same alias — both are returned. Discovery does not judge; this is why the return is a list rather than a mapping keyed by alias | `test_two_apps_claiming_one_alias_both_come_back` |
| DS-06 | A `db_spec` module that raises on import — the error surfaces unchanged rather than being swallowed | `test_a_db_spec_that_raises_on_import_surfaces_the_error` |
| DS-07 | Specs are returned as declared — not copied, not altered | `test_the_spec_object_is_returned_as_declared` |
| DS-08 | A `db_spec` whose own import fails raises `SpecImportError` rather than being skipped, and the message names the app, the module and the import that failed | `test_a_db_spec_with_a_broken_import_raises_and_says_what_broke` |
| DS-09 | That `SpecImportError` chains the original exception rather than replacing it, so the consumer's own error is still underneath | `test_the_broken_import_chains_the_original_exception` |
| DS-10 | A dotted app name works the same as a flat one. Free today — the case exists so a later change cannot quietly assume a flat name | `test_a_dotted_app_name_resolves_like_a_flat_one` |
| DS-11 | An app that cannot be imported at all raises `MissingAppError`, not `SpecImportError` — a different fault with a different message, chained to the original | `test_an_app_that_does_not_exist_raises_its_own_error` |
| DS-12 | An `INSTALLED_APPS` entry naming an AppConfig class resolves to its package. Django accepts both forms and Evennia ships `evennia.web.utils.adminsite.EvenniaAdminApp` in its own defaults, so treating one as a missing app kills `django.setup()` on a stock gamedir | `test_an_appconfig_path_resolves_to_its_package` |

## SP — `AliasSpec`

What a library declares about its alias. `allow_sharing_common_db` and
`allow_foreign_tables_in_own_db` are named at length deliberately: they are read by someone
installing a library, not by us, and each is a permission rather than a state.

| ID | Case | Test function |
|---|---|---|
| SP-01 | A spec carries the five fields, with the values it was given | `test_a_spec_carries_the_values_it_was_given` |
| SP-02 | `sqlite_filename` defaults to `f"{alias}.db3"` | `test_sqlite_filename_defaults_to_the_alias` |
| SP-03 | An explicit `sqlite_filename` is kept, not overwritten by the default | `test_an_explicit_sqlite_filename_is_kept` |
| SP-04 | `allow_sharing_common_db` defaults to `True` | `test_sharing_the_common_db_is_allowed_by_default` |
| SP-05 | `allow_foreign_tables_in_own_db` defaults to `False` | `test_foreign_tables_are_refused_by_default` |
| SP-06 | `app_label` and `alias` are independent — a spec whose two differ keeps both | `test_app_label_and_alias_are_independent` |
| SP-07 | `app_label` and `alias` are required; omitting either raises | `test_app_label_and_alias_are_required` |
| SP-08 | The spec is frozen — assigning to a field raises. Free from `frozen=True`; the case exists so a later change cannot quietly remove it | `test_a_spec_is_frozen` |
| SP-09 | An unknown field name raises at construction. This is the "typos fail loudly" property that chose a dataclass over a dict | `test_an_unknown_field_raises` |
| SP-10 | `spec.py` imports nothing from Django. Read off the module's AST — importing it inside the suite proves nothing, because Django is configured there. Likely becomes a cross-cutting case over every module on the settings path | `test_spec_module_imports_nothing_from_django` |
| SP-11 | `conn_max_age` defaults to the `UNSET` sentinel, meaning the spec says nothing and the game-wide value applies | `test_conn_max_age_says_nothing_by_default` |
| SP-12 | A spec that sets `conn_max_age` keeps the value, `None` included. `None` is a real Django value — persist the connection forever — which is why the sentinel cannot be `None` | `test_a_spec_keeps_the_conn_max_age_it_was_given` |
| SP-13 | `session_options` defaults to the `UNSET` sentinel, meaning the spec says nothing | `test_session_options_say_nothing_by_default` |
| SP-14 | A spec that sets `session_options` keeps the mapping it was given | `test_a_spec_keeps_the_session_options_it_was_given` |
| SP-15 | `required_extensions` defaults to empty | `test_required_extensions_are_empty_by_default` |
| SP-16 | A spec that declares extensions keeps them | `test_a_spec_keeps_the_extensions_it_declared` |

## VS — `validate_specs(specs)`

Everything checkable once every spec is in hand. Per-field shape the dataclass cannot enforce, and
the cross-spec collisions no single spec can see. Refusals raise `SpecValidationError`, a `ValueError`
— a wrong value rather than a failed import, so it does not sit under `ImportError` with
`MissingAppError` and `SpecImportError`.

The collision between an alias's SQLite file and the game's own database is **not** here. It needs
`game_dir` to resolve a path, so it belongs to `configure()`, and it only fires where `default` is
SQLite — on Postgres there is no file to collide with.

| ID | Case | Test function |
|---|---|---|
| VS-01 | A valid list passes and returns nothing | `test_a_valid_list_passes` |
| VS-02 | An empty list passes | `test_an_empty_list_passes` |
| VS-03 | Two specs claiming one alias raise, naming both app labels | `test_two_specs_claiming_one_alias_raise` |
| VS-04 | Two specs claiming one `app_label` raise, naming both aliases | `test_two_specs_claiming_one_app_label_raise` |
| VS-05 | An empty or whitespace-only `alias` raises | `test_an_empty_alias_raises` |
| VS-06 | An empty or whitespace-only `app_label` raises | `test_an_empty_app_label_raises` |
| VS-07 | An alias of `"default"` raises. Django's implicit alias cannot be renamed, so the literal string is exact rather than a guess — and a spec claiming it would replace the game's own connection | `test_an_alias_of_default_raises` |
| VS-08 | Several problems at once produce one raise, naming all of them | `test_every_problem_is_reported_in_one_raise` |
| VS-09 | An alias that is not a valid environment-variable name raises — a hyphen, a space, a leading digit. The alias becomes `DATABASE_URL_<ALIAS>`, so one no shell can export is an alias nobody can deploy | `test_an_alias_that_cannot_be_an_environment_variable_raises` |

## RS — `resolve_database(spec, game_dir, env, common_url_var)`

One spec in, one `DATABASES` entry out. It knows about that spec and the environment and nothing
else — not the other aliases, not `DATABASES`, and not whether anything is split, which `is_split`
answers separately from the same environment.

SQLite falls to `<game_dir>/server/`, which is where Evennia puts every database file it creates.

| ID | Case | Test function |
|---|---|---|
| RS-01 | `DATABASE_URL_<ALIAS>` set — the entry is that URL parsed | `test_the_alias_own_url_is_used_when_set` |
| RS-02 | Only the common URL set — the entry is that URL parsed | `test_the_common_url_is_used_when_the_alias_has_none` |
| RS-03 | Neither set — a SQLite entry at `<game_dir>/server/<sqlite_filename>` | `test_no_url_falls_back_to_a_sqlite_file` |
| RS-04 | Both set — the alias's own URL wins | `test_the_alias_own_url_wins_over_the_common_one` |
| RS-05 | The variable read is the alias upper-cased and prefixed: `ai_memory` reads `DATABASE_URL_AI_MEMORY` | `test_the_variable_read_is_the_alias_upper_cased` |
| RS-06 | The common variable name comes from the argument rather than a hardcoded string — a caller naming a different one is honoured | `test_the_common_variable_name_comes_from_the_argument` |
| RS-07 | Only the mapping passed in is read; the real `os.environ` is never consulted | `test_the_real_environment_is_never_consulted` |
| RS-08 | A variable set to an empty string counts as unset and falls through to the next rung. An exported-but-empty variable is a real deployment state, and treating it as set would hand `dj-database-url` an empty string | `test_an_empty_variable_counts_as_unset` |
| RS-09 | `allow_sharing_common_db=False` with only the common URL set raises `SharedDatabaseRefused`, naming the alias and the variable to set instead | `test_a_spec_refusing_the_common_db_raises_on_that_rung` |
| RS-10 | `allow_sharing_common_db=False` with its own URL set resolves normally | `test_a_spec_refusing_the_common_db_accepts_its_own_url` |
| RS-11 | `allow_sharing_common_db=False` with neither set resolves to its own SQLite file. Only the shared rung is refused, not the fallback | `test_a_spec_refusing_the_common_db_still_falls_back_to_sqlite` |
| RS-12 | The SQLite entry uses the spec's `sqlite_filename`, including a non-default one | `test_the_sqlite_entry_uses_the_declared_filename` |
| RS-13 | The entry carries the `conn_max_age` it was given | `test_the_entry_carries_the_conn_max_age_it_was_given` |
| RS-14 | A spec's own `conn_max_age` overrides the game-wide value, for that alias only | `test_a_spec_overrides_the_game_wide_conn_max_age` |
| RS-15 | `conn_max_age=None` on a spec is honoured as a value — persist forever — rather than read as "unset" | `test_none_on_a_spec_is_a_value_not_an_absence` |
| RS-16 | Applied on every rung, SQLite included. No branch on engine: meaningless there rather than harmful, and a uniform rule is one less thing to get wrong | `test_conn_max_age_is_applied_on_every_rung` |
| RS-17 | `session_options` is rendered as `-c name=value` pairs into the entry's `OPTIONS["options"]` | `test_session_options_are_rendered_into_the_entry` |
| RS-18 | A spec's own `session_options` overrides the game-wide default, for that alias only | `test_a_spec_overrides_the_game_wide_session_options` |
| RS-19 | Appended to whatever `OPTIONS` the URL already produced, rather than replacing it — a `?sslmode=require` in the URL survives a library setting a parameter of its own | `test_session_options_are_appended_to_what_the_url_produced` |
| RS-20 | Skipped entirely on a SQLite entry. Unlike `conn_max_age` this one does need a branch on engine: `OPTIONS` means something else there, and a libpq string breaks the connection outright | `test_session_options_are_skipped_on_sqlite` |

## SL — `is_split(alias, env, common_url_var)` and `split_aliases(specs, env, common_url_var)`

Whether an alias is on a database of its own, and the subset of a spec list that is.

`is_split` takes the alias rather than the spec: `allow_sharing_common_db` cannot change the answer,
because a spec refusing the shared rung can only reach rung 1 or rung 3 and both are split already.

`split_aliases` exists as a named function rather than a comprehension at each call site because
`configure()` and the migrate helper run in different processes and must reach the same answer.
Routing and migration disagreeing is the silent failure the library exists to prevent.

`SL-05` to `SL-07` mirror `RS-06` to `RS-08` deliberately: both functions read the same environment,
so both must read it the same way, and the paired cases are what stop one drifting from the other.

| ID | Case | Test function |
|---|---|---|
| SL-01 | The alias's own URL is set — split | `test_an_alias_with_its_own_url_is_split` |
| SL-02 | Only the common URL is set — not split | `test_an_alias_on_only_the_common_url_is_not_split` |
| SL-03 | Neither is set — split, because every alias is then its own SQLite file | `test_an_alias_with_no_urls_at_all_is_split` |
| SL-04 | Both are set — split | `test_an_alias_with_both_urls_is_split` |
| SL-05 | The common variable name comes from the argument rather than a hardcoded string | `test_the_common_variable_name_comes_from_the_argument` |
| SL-06 | A variable set to an empty string counts as unset, in either position | `test_an_empty_variable_counts_as_unset` |
| SL-07 | Only the mapping passed in is read; the real `os.environ` is never consulted | `test_the_real_environment_is_never_consulted` |
| SL-08 | `split_aliases` returns the aliases of the split specs, in spec order | `test_split_aliases_returns_the_split_subset_in_order` |
| SL-09 | No spec split — an empty list | `test_split_aliases_returns_nothing_when_all_share` |
| SL-10 | Every spec split — every alias, none omitted | `test_split_aliases_returns_all_of_them_on_sqlite` |

## RT — `CascadeRouter(spec)`

One parameterised router replacing the five hand-written ones across FCM. Django ships no router
implementation — `DATABASE_ROUTERS` holds objects a project writes — and the five that exist are the
same twenty-five lines with three values changed. Those three are already on the spec, so this is one
instance per spec rather than one subclass per library.

It imports nothing from Django, which is what lets `configure()` build instances and put them
straight in `DATABASE_ROUTERS` rather than dealing in dotted paths.

**It routes queries and permits migrations, and those are separate.** For `evennia-archive` the
router lets Evennia's own forty-two tables be created in the archive, and still sends every
`ObjectDB` query to `default` — routing them to the archive would have the game reading its players
out of the wrong database. Reaching an archived copy is explicit, with `.using("archive")`, and that
is the archive library's code rather than the router's.

| ID | Case | Test function |
|---|---|---|
| RT-01 | `db_for_read` returns the alias for a model of its own app | `test_reads_of_our_models_go_to_our_alias` |
| RT-02 | `db_for_write` returns the alias for a model of its own app | `test_writes_of_our_models_go_to_our_alias` |
| RT-03 | Both return `None` for a foreign model. Django takes the first non-`None` answer, so a router answering for someone else's model silently captures their queries | `test_a_foreign_model_gets_no_answer` |
| RT-04 | `allow_migrate` is `True` for its own app on its own alias | `test_our_app_may_migrate_onto_our_alias` |
| RT-05 | `allow_migrate` is `False` for its own app on any other alias, `default` included. Without this a bare `evennia migrate` creates its tables in the game database as well, and the separation exists only on paper | `test_our_app_may_not_migrate_anywhere_else` |
| RT-06 | `allow_foreign_tables_in_own_db=False` — `allow_migrate` is `False` for a foreign app on its alias | `test_a_foreign_app_is_refused_our_alias_by_default` |
| RT-07 | `allow_foreign_tables_in_own_db=True` — `allow_migrate` is `None` for a foreign app on its alias, so other apps may migrate in. This is the archive taking Evennia's tables | `test_a_foreign_app_may_join_us_when_the_spec_allows_it` |
| RT-08 | `allow_migrate` is `None` for a foreign app on a foreign alias — no opinion at all | `test_a_foreign_app_on_a_foreign_alias_gets_no_opinion` |
| RT-09 | `allow_relation` is `True` when both models are its own | `test_a_relation_between_two_of_ours_is_allowed` |
| RT-10 | `allow_relation` is `None` otherwise, whether one or both are foreign | `test_a_relation_touching_a_foreign_model_gets_no_opinion` |
| RT-11 | Two routers built from different specs each answer only for their own app — the co-installed case | `test_two_routers_each_answer_only_for_their_own_app` |
| RT-12 | A spec whose `app_label` and `alias` differ routes on the app label and returns the alias | `test_the_app_label_and_the_alias_are_read_separately` |
| RT-13 | `router.py` imports nothing from Django | `test_router_module_imports_nothing_from_django` |

## CF — `configure(databases, installed_apps, game_dir, env, common_url_var)`

The one call a consumer makes, from their `settings.py`. It discovers the specs, validates them,
resolves each alias into `DATABASES`, and returns that alongside a router for exactly the split
aliases.

It **copies** the databases dict rather than editing the one it was handed. Both read the same at the
call site, where the consumer reassigns; a function that silently changes its argument is worse to
test and worse to reason about.

**The common URL names the game's database.** So when one is set, `configure()` points `default` at
it along with every alias that has no URL of its own — that is what makes rung 2 mean one database
rather than two. Without it the aliases move and the game does not, which on Postgres leaves the game
quietly on SQLite while its libraries are on the server, and on SQLite creates an empty file nothing
will ever migrate. `CF-18` is the assertion that catches it.

Nothing here logs. Everything in this call runs before `django.setup()`, where the shim raises — see
principle 8 in [CLAUDE.md](../CLAUDE.md). Failures raise, and the traceback is the record.

| ID | Case | Test function |
|---|---|---|
| CF-01 | Returns `DATABASES` carrying an entry per discovered spec | `test_every_discovered_spec_gets_an_entry` |
| CF-02 | With **no common URL set**, the `default` entry is left exactly as it was given | `test_the_default_entry_is_left_alone` |
| CF-03 | Returns routers for exactly the split aliases, and none for the rest | `test_routers_are_built_for_exactly_the_split_aliases` |
| CF-04 | No alias split — an empty router list | `test_nothing_split_means_no_routers` |
| CF-05 | Every alias split — one router each, in spec order | `test_everything_split_means_a_router_each_in_spec_order` |
| CF-06 | No specs discovered — the databases unchanged and an empty router list | `test_no_specs_changes_nothing` |
| CF-07 | The dict it was handed is not mutated | `test_the_databases_argument_is_not_mutated` |
| CF-08 | The routers are `CascadeRouter` instances rather than dotted paths, which is what lets them carry a spec | `test_the_routers_are_instances_carrying_their_spec` |
| CF-09 | An invalid spec set raises — `validate_specs` is reached rather than skipped | `test_an_invalid_spec_set_is_refused` |
| CF-10 | A broken `db_spec` raises — `discover_specs`' errors propagate unchanged | `test_a_broken_db_spec_propagates` |
| CF-11 | `common_url_var` reaches both the resolution and the split decision | `test_the_common_variable_name_reaches_both_steps` |
| CF-12 | A **split** alias whose resolved SQLite path is the game's own database file raises `GameDatabaseCollision`, naming the alias and the file | `test_an_alias_landing_on_the_game_database_file_is_refused` |
| CF-13 | That check fires only where `default` is SQLite. A Postgres `default` alongside an alias on SQLite is not a collision, and there is no file to compare | `test_a_postgres_default_alongside_sqlite_is_not_a_collision` |
| CF-14 | `default_conn_max_age` defaults to `0` and reaches every entry. Zero closes the connection at the end of each unit of work, which is the safe end of the scale and what a Twisted deployment needs — FCM reached its Postgres connection limit before setting it | `test_conn_max_age_defaults_to_zero_and_reaches_every_entry` |
| CF-15 | `default_session_options` defaults to empty and reaches every entry | `test_session_options_default_to_empty_and_reach_every_entry` |
| CF-17 | A common URL is set — `default` resolves to it. The common URL names the game's database, so it owns `default` by definition | `test_a_common_url_moves_the_default_entry` |
| CF-18 | `default` and every alias without a URL of its own name the **same** database, so the router list is empty and "one database" is literally true rather than assumed | `test_the_game_and_every_quiet_alias_name_one_database` |
| CF-19 | An alias with its own URL still splits off it — `default` follows the common URL, that alias does not, and exactly one router is active | `test_an_alias_with_its_own_url_still_splits_off_the_common_one` |
| CF-20 | `default` gets the same connection treatment as the aliases: `default_conn_max_age` and the game-wide session options land on it too | `test_the_moved_default_gets_the_same_connection_treatment` |
| CF-21 | A `default` the consumer wrote themselves is **replaced** when a common URL is set. Deliberate, and pinned so it is not later "fixed" into a merge or a skip-if-present | `test_a_consumer_set_default_is_replaced_by_the_common_url` |
| CF-22 | An alias sharing the game's database **through the common URL** is not a collision — that is the arrangement, not a mistake. The check applies to split aliases only, which is what keeps CF-12 meaningful without refusing rung 2 outright | `test_sharing_the_game_database_through_the_common_url_is_not_a_collision` |
| CF-16 | Routers the consumer already had are kept, with ours appended after. Overwriting the list would drop a router they wrote and send whatever it routed to `default`, silently. Theirs first, because Django takes the first non-`None` answer and an explicit choice of theirs should win over ours | `test_a_consumers_own_routers_are_kept` |

## BC — `check_settings()`, the boot check

Two questions, asked once, at `AppConfig.ready()` — the first point where Django is up and
`settings.DATABASES` can be read back.

**Did a library that depends on us forget to declare anything?** For each app in `INSTALLED_APPS`,
the distribution shipping its top-level package is asked what it requires. A distribution requiring
this library and shipping no `db_spec` is a fault: its alias is never configured, its models fall
through to `default`, and the game runs with its tables in the database they exist to stay out of.
The message names the library, because the person reading it is not the person who can fix it.

**Did every declared alias reach `DATABASES`?** The consequence of `configure()` being called before
the consumer's `INSTALLED_APPS` edits, or not at all.

Named `check_settings` in `config.py` and called from `ready()` because that is the shape every
library here uses, even though what it checks is not settings. `from django.conf import settings`
goes inside the function, so `config.py` stays importable from a settings module.

This is where logging starts — see principle 8 in [CLAUDE.md](../CLAUDE.md). Nothing before it can
write a line.

| ID | Case | Test function |
|---|---|---|
| BC-01 | An app whose distribution requires this library and has a `db_spec` — passes | `test_a_dependent_app_declaring_a_spec_passes` |
| BC-02 | An app whose distribution requires this library and has no `db_spec` — raises, naming the app and the distribution | `test_a_dependent_app_with_no_spec_is_refused` |
| BC-03 | A requirement carrying an `extra ==` marker is skipped. An optional dependency is not a promise to declare an alias | `test_an_optional_dependency_is_skipped` |
| BC-04 | An app whose distribution does not require this library is ignored, `db_spec` or not | `test_an_app_not_depending_on_us_is_ignored` |
| BC-05 | An app with no distribution at all — a gamedir module — is ignored. There is no metadata to read | `test_an_app_with_no_distribution_is_ignored` |
| BC-06 | Every app with a `db_spec` has its alias in `settings.DATABASES` — passes | `test_a_declared_alias_present_in_databases_passes` |
| BC-07 | An app with a `db_spec` whose alias is absent — raises, naming the app and the alias | `test_a_declared_alias_missing_from_databases_is_refused` |
| BC-08 | Two such apps — one raise, naming both | `test_two_missing_aliases_are_reported_together` |
| BC-09 | Both kinds of problem at once — one raise, naming all of them | `test_both_kinds_of_problem_are_reported_together` |
| BC-10 | **Retired.** Asserted a log line on a clean run. Nothing in this library can log — see `log.py` — and the case passed only because the shim was mocked | — |
| BC-11 | **Retired.** Asserted a refusal was logged before being raised. Same reason as BC-10 | — |
| BC-12 | `ready()` calls the check, so it cannot be defined and never run | `test_ready_calls_the_check` |

## MG — `migrate_all()` and `evennia cascade_migrate`

The other half of *routing and migration read one answer*. A split alias is not reached by a bare
`evennia migrate` — its router refuses those tables on every database but its own — so it needs
`migrate --database <alias>`. Miss one and Django records the migrations as applied with no tables
created, which is the failure the library exists to prevent and the one place a human is otherwise
expected to remember a list.

It runs in a different process from `configure()`, so it re-derives the split set through
`split_aliases` rather than being handed one. Django is up by then, so this logs.

Options are forwarded to Django's `migrate` untouched, so a consumer keeps `--verbosity` and
`--noinput`. `database` is the exception: the helper decides that per call, and a caller supplying it
would be fighting the thing the helper is for.

**Required extensions are checked first, across every alias**, including the ones sharing the game's
database — a shared alias's extension lives on the common database and needs checking too. The check
only reports: creating an extension needs superuser and the application role deliberately is not one,
so the raise carries the command for a human to run. It refuses before the bare `migrate`, because a
migration that creates a vector column against a database without the extension fails halfway rather
than cleanly.

`common_url_var` comes from `CASCADE_COMMON_URL_VAR`, this library's only setting — read through an
accessor in `config.py`, defaulting to `DATABASE_URL`. It exists because the value has to be known in
two processes: the consumer passes it to `configure()` from their settings module, and the helper
reads it back from the same place.

| ID | Case | Test function |
|---|---|---|
| MG-01 | Runs a bare `migrate` first | `test_the_bare_migrate_runs_first` |
| MG-02 | Then one `migrate --database <alias>` per split alias, in spec order | `test_each_split_alias_gets_its_own_call_in_spec_order` |
| MG-03 | No split aliases — the bare call and nothing else | `test_nothing_split_means_the_bare_call_only` |
| MG-04 | The split set comes from `split_aliases`, not a second derivation of the same rule | `test_the_split_set_comes_from_split_aliases` |
| MG-05 | An unsplit alias never gets its own call — the bare migrate already covered it | `test_an_unsplit_alias_never_gets_its_own_call` |
| MG-06 | A failing migrate propagates rather than being swallowed | `test_a_failing_migrate_propagates` |
| MG-07 | **Retired.** Asserted a log line naming what was migrated. Nothing in this library can log — see `log.py`. The command's own stdout is the record | — |
| MG-08 | `common_url_var` comes from `CASCADE_COMMON_URL_VAR`, defaulting to `DATABASE_URL` | `test_the_common_variable_comes_from_the_setting` |
| MG-09 | The management command calls `migrate_all`, so the two cannot drift | `test_the_command_calls_migrate_all` |
| MG-10 | Options are forwarded to `migrate` untouched, and a caller-supplied `database` is refused rather than silently overridden | `test_options_are_forwarded_and_database_is_refused` |
| MG-11 | Every required extension present — the migrations run normally | `test_migrations_run_when_every_extension_is_present` |
| MG-12 | One missing raises **before any migration runs**, naming the extension, the database it is missing from, and the `CREATE EXTENSION` command to run | `test_a_missing_extension_refuses_before_any_migration` |
| MG-13 | Several missing, across aliases — one raise naming all of them | `test_every_missing_extension_is_reported_together` |
| MG-14 | Skipped on a non-Postgres alias, where there are no extensions to have | `test_the_check_is_skipped_on_a_non_postgres_alias` |

## LG — `cascade_log`

**Nothing in this library calls the shim**, so these cases prove only that our copy is faithful to
the standard's — not that anything is ever written. Evennia's `log_file` writes through
`deferToThread` and every part of this library runs before a reactor exists, so a call would open the
file and write nothing. Measured, not assumed: a 0-byte `cascade.log` beside a demo gamedir that had
just refused a migration. See `log.py` and principle 8.

| ID | Case | Test function |
|---|---|---|
| LG-01 | A call reaches `logger.log_file` with `cascade.log` as the filename | `test_it_writes_to_the_library_log_file` |
| LG-02 | The level prefixes the message as `[LEVEL] message` | `test_the_level_prefixes_the_message` |
| LG-03 | An unknown level coerces to `INFO` rather than raising. A log call must never raise into its caller | `test_an_unknown_level_coerces_to_info` |
| LG-04 | Outside an Evennia engine the call is a silent no-op — no stderr, no local file | `test_it_is_a_silent_noop_without_evennia` |
| LG-05 | `trace=True` inside an `except` block appends the traceback | `test_trace_inside_an_except_block_appends_the_traceback` |
| LG-06 | `trace=True` outside one appends nothing, rather than logging `NoneType: None` | `test_trace_outside_an_except_block_adds_nothing` |
