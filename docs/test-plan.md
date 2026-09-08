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

## Fixtures

The fake objects the suite needs, named and purposed. Empty beyond the smoke case: fixtures arrive
with the unit that needs them.

| Fixture | Purpose |
|---|---|
| `AppTree` | Builds throwaway app packages on `sys.path` and removes them afterwards. Real packages with real `db_spec.py` files, so the cases exercise the import machinery rather than a stand-in for it |
| `SPEC_MODULE` | The source of a `db_spec` module as a consumer library would write one — a spec object carrying an `alias`. Deliberately a local stand-in, not the library's own spec type, so discovery's cases do not wait on it |
| `RAISING_SPEC_MODULE` | A `db_spec` that raises on import, for DS-06 |

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

## SP — `AliasSpec`

The five fields a library declares about its alias. `allow_sharing_common_db` and
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
