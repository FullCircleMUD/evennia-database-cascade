# SPDX-License-Identifier: BSD-3-Clause
"""Unit tests for evennia-database-cascade.

Case IDs come from docs/test-plan.md. Each test carries its case ID as the
first line of its docstring, so the coverage trail reads in both directions.

The DS cases build throwaway app packages on ``sys.path`` rather than faking
``sys.modules``, because discovery has to work the way the real thing does —
importing a module by name, with no app registry to ask. A pre-seeded
``sys.modules`` entry would skip the import machinery that DS-06 exists to
test.
"""

import ast
import dataclasses
import importlib
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from django.core.exceptions import ImproperlyConfigured

import evennia_database_cascade
from evennia_database_cascade import AliasSpec
from evennia_database_cascade import spec as spec_module
from evennia_database_cascade.discovery import (
    MissingAppError,
    SpecImportError,
    SpecValidationError,
    discover_specs,
    validate_specs,
)
from evennia_database_cascade import config as config_module
from evennia_database_cascade import configure
from evennia_database_cascade import router as router_module
from evennia_database_cascade import migrate as migrate_module
from evennia_database_cascade.config import UNSET, check_settings, get_common_url_var
from evennia_database_cascade.log import cascade_log
from evennia_database_cascade.migrate import migrate_all
from evennia_database_cascade.configure import GameDatabaseCollision
from evennia_database_cascade.resolve import (
    SharedDatabaseRefused,
    alias_url_variable,
    is_split,
    resolve_database,
    split_aliases,
)
from evennia_database_cascade.router import CascadeRouter

# A game directory that need not exist — rung 3 builds a path, it does not
# create or open a file.
GAME_DIR = os.path.join("some", "gamedir")

OWN_URL = "postgres://own_user:pw@own.host:5432/own_db"
COMMON_URL = "postgres://common_user:pw@common.host:5432/common_db"


def django_imports(module):
    """Every Django import a module runs at import time.

    Read from the AST rather than by importing: Django is configured inside
    this suite, so an import that would break a consumer's settings module
    succeeds here and proves nothing.

    Function bodies are skipped, because the constraint is about import
    *time*. ``from django.conf import settings`` at module scope runs while
    the consumer's settings module is still executing; the same line inside
    ``check_settings()`` runs at ``ready()``, where Django is up. Class
    bodies and ``try`` blocks are not skipped — those do run on import.
    """
    imported = []

    def collect(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Import):
                imported.extend(alias.name for alias in child.names)
            elif isinstance(child, ast.ImportFrom):
                imported.append(child.module or "")
            collect(child)

    collect(ast.parse(pathlib.Path(module.__file__).read_text()))
    return [name for name in imported if name.split(".")[0] == "django"]


def model(app_label):
    """A model-shaped object carrying an app label, for the router cases."""
    return type(
        "FakeModel",
        (),
        {"_meta": type("FakeMeta", (), {"app_label": app_label})()},
    )()


# A db_spec module as a consumer library would write one. The spec object is
# deliberately a local stand-in rather than the library's own type: discovery
# returns what it finds without inspecting it, so these cases must not depend
# on a spec type that does not exist yet.
SPEC_MODULE = """
class Spec:
    def __init__(self, alias):
        self.alias = alias


SPEC = Spec({alias!r})
"""

def spec_module_source(**fields):
    """The source of a db_spec declaring a real AliasSpec.

    The DS cases use a local stand-in instead, so discovery's cases do not
    depend on the spec type. The CF cases need the real one, because
    resolution reads fields off it.
    """
    arguments = ", ".join(f"{name}={value!r}" for name, value in fields.items())
    return (
        "from evennia_database_cascade import AliasSpec\n"
        f"\nSPEC = AliasSpec({arguments})\n"
    )


# ValueError rather than RuntimeError: NotImplementedError subclasses
# RuntimeError, so a stubbed-out discover_specs would satisfy the assertion
# for the wrong reason and the case would pass before it was implemented.
RAISING_SPEC_MODULE = """
raise ValueError("this db_spec is broken")
"""

# The case the skip logic must not swallow: the module is there, and its own
# import is what fails. Python raises ModuleNotFoundError for this and for an
# app with no db_spec at all.
BROKEN_IMPORT_SPEC_MODULE = """
from definitely_not_a_real_module import ALIAS

SPEC = ALIAS
"""


class SmokeTest(unittest.TestCase):
    """The package is installed and the runner reaches it."""

    def test_package_imports_and_declares_a_version(self):
        """SM-01 — the installed package imports and carries __version__."""
        self.assertEqual(evennia_database_cascade.__version__, "0.0.1")


class AppTree:
    """Builds throwaway app packages on sys.path, and takes them away again.

    Each app is a real package with a real ``db_spec.py``, so the cases
    exercise the import machinery rather than a stand-in for it.
    """

    def __init__(self):
        self.root = tempfile.mkdtemp()
        self.names = []
        sys.path.insert(0, self.root)

    def add(self, name, db_spec_source=None):
        """Create an app package, optionally carrying a ``db_spec`` module.

        A dotted name builds the nested packages it implies, so a case can
        name an app the way a real ``INSTALLED_APPS`` does.
        """
        package = self.root
        for part in name.split("."):
            package = os.path.join(package, part)
            os.makedirs(package, exist_ok=True)
            init = os.path.join(package, "__init__.py")
            if not os.path.exists(init):
                open(init, "w").close()
        if db_spec_source is not None:
            with open(os.path.join(package, "db_spec.py"), "w") as handle:
                handle.write(db_spec_source)
        # The outermost package: teardown purges it and everything under it.
        self.names.append(name.split(".")[0])
        importlib.invalidate_caches()
        return name

    def teardown(self):
        for name in self.names:
            for module in [
                key
                for key in list(sys.modules)
                if key == name or key.startswith(f"{name}.")
            ]:
                del sys.modules[module]
        if self.root in sys.path:
            sys.path.remove(self.root)
        shutil.rmtree(self.root, ignore_errors=True)


class DiscoverSpecsTest(unittest.TestCase):
    """discover_specs — finding the specs the installed apps declare."""

    def setUp(self):
        self.apps = AppTree()
        self.addCleanup(self.apps.teardown)

    def test_an_app_declaring_a_spec_contributes_it(self):
        """DS-01 — an app whose db_spec module exists contributes its spec."""
        self.apps.add("ds01_app", SPEC_MODULE.format(alias="ds01"))

        found = discover_specs(["ds01_app"])

        self.assertEqual([spec.alias for spec in found], ["ds01"])

    def test_an_app_without_a_db_spec_is_skipped(self):
        """DS-02 — an app without one is skipped, and nothing is raised."""
        self.apps.add("ds02_bare")
        self.apps.add("ds02_app", SPEC_MODULE.format(alias="ds02"))

        found = discover_specs(["ds02_bare", "ds02_app"])

        self.assertEqual([spec.alias for spec in found], ["ds02"])

    def test_specs_come_back_in_installed_apps_order(self):
        """DS-03 — several apps declaring one: a list, in INSTALLED_APPS order."""
        self.apps.add("ds03_first", SPEC_MODULE.format(alias="first"))
        self.apps.add("ds03_bare")
        self.apps.add("ds03_second", SPEC_MODULE.format(alias="second"))

        found = discover_specs(["ds03_second", "ds03_bare", "ds03_first"])

        self.assertEqual([spec.alias for spec in found], ["second", "first"])

    def test_no_app_declaring_one_returns_an_empty_list(self):
        """DS-04 — no app declares one: an empty list."""
        self.apps.add("ds04_bare")

        self.assertEqual(discover_specs(["ds04_bare"]), [])

    def test_two_apps_claiming_one_alias_both_come_back(self):
        """DS-05 — two apps declaring the same alias: both are returned."""
        self.apps.add("ds05_one", SPEC_MODULE.format(alias="shared"))
        self.apps.add("ds05_two", SPEC_MODULE.format(alias="shared"))

        found = discover_specs(["ds05_one", "ds05_two"])

        self.assertEqual([spec.alias for spec in found], ["shared", "shared"])

    def test_a_db_spec_that_raises_on_import_surfaces_the_error(self):
        """DS-06 — a db_spec that raises on import: the error surfaces unchanged."""
        self.apps.add("ds06_app", RAISING_SPEC_MODULE)

        with self.assertRaises(ValueError) as caught:
            discover_specs(["ds06_app"])

        self.assertIn("this db_spec is broken", str(caught.exception))

    def test_the_spec_object_is_returned_as_declared(self):
        """DS-07 — specs are returned as declared: not copied, not altered."""
        self.apps.add("ds07_app", SPEC_MODULE.format(alias="ds07"))

        found = discover_specs(["ds07_app"])

        declared = importlib.import_module("ds07_app.db_spec").SPEC
        self.assertIs(found[0], declared)

    def test_a_db_spec_with_a_broken_import_raises_and_says_what_broke(self):
        """DS-08 — a db_spec whose own import fails raises, naming what broke."""
        self.apps.add("ds08_app", BROKEN_IMPORT_SPEC_MODULE)

        with self.assertRaises(SpecImportError) as caught:
            discover_specs(["ds08_app"])

        message = str(caught.exception)
        self.assertIn("ds08_app", message)
        self.assertIn("db_spec", message)
        self.assertIn("definitely_not_a_real_module", message)

    def test_the_broken_import_chains_the_original_exception(self):
        """DS-09 — the raise chains the original rather than replacing it."""
        self.apps.add("ds09_app", BROKEN_IMPORT_SPEC_MODULE)

        with self.assertRaises(SpecImportError) as caught:
            discover_specs(["ds09_app"])

        cause = caught.exception.__cause__
        self.assertIsInstance(cause, ModuleNotFoundError)
        self.assertEqual(cause.name, "definitely_not_a_real_module")

    def test_a_dotted_app_name_resolves_like_a_flat_one(self):
        """DS-10 — a dotted app name works the same as a flat one."""
        self.apps.add("ds10_outer.inner", SPEC_MODULE.format(alias="ds10"))

        found = discover_specs(["ds10_outer.inner"])

        self.assertEqual([spec.alias for spec in found], ["ds10"])

    def test_an_appconfig_path_resolves_to_its_package(self):
        """DS-12 — an entry naming an AppConfig class resolves to its package."""
        self.apps.add("ds12_app", SPEC_MODULE.format(alias="ds12"))

        found = discover_specs(["ds12_app.apps.Ds12Config"])

        self.assertEqual([spec.alias for spec in found], ["ds12"])

    def test_an_app_that_does_not_exist_raises_its_own_error(self):
        """DS-11 — an app that cannot be imported at all raises MissingAppError."""
        with self.assertRaises(MissingAppError) as caught:
            discover_specs(["ds11_no_such_app"])

        message = str(caught.exception)
        self.assertIn("ds11_no_such_app", message)
        self.assertIn("INSTALLED_APPS", message)
        self.assertIsInstance(caught.exception.__cause__, ModuleNotFoundError)


class AliasSpecTest(unittest.TestCase):
    """AliasSpec — what a library declares about its alias."""

    def test_a_spec_carries_the_values_it_was_given(self):
        """SP-01 — a spec carries the five fields, with the values given."""
        spec = AliasSpec(
            app_label="evennia_archive",
            alias="archive",
            sqlite_filename="archive.db3",
            allow_sharing_common_db=False,
            allow_foreign_tables_in_own_db=True,
        )

        self.assertEqual(spec.app_label, "evennia_archive")
        self.assertEqual(spec.alias, "archive")
        self.assertEqual(spec.sqlite_filename, "archive.db3")
        self.assertFalse(spec.allow_sharing_common_db)
        self.assertTrue(spec.allow_foreign_tables_in_own_db)

    def test_sqlite_filename_defaults_to_the_alias(self):
        """SP-02 — sqlite_filename defaults to f"{alias}.db3"."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        self.assertEqual(spec.sqlite_filename, "xrpl.db3")

    def test_an_explicit_sqlite_filename_is_kept(self):
        """SP-03 — an explicit sqlite_filename is not overwritten."""
        spec = AliasSpec(
            app_label="fcm_xrpl", alias="xrpl", sqlite_filename="ledger.db3"
        )

        self.assertEqual(spec.sqlite_filename, "ledger.db3")

    def test_sharing_the_common_db_is_allowed_by_default(self):
        """SP-04 — allow_sharing_common_db defaults to True."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        self.assertTrue(spec.allow_sharing_common_db)

    def test_foreign_tables_are_refused_by_default(self):
        """SP-05 — allow_foreign_tables_in_own_db defaults to False."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        self.assertFalse(spec.allow_foreign_tables_in_own_db)

    def test_app_label_and_alias_are_independent(self):
        """SP-06 — a spec whose app_label and alias differ keeps both."""
        spec = AliasSpec(app_label="evennia_archive", alias="archive")

        self.assertEqual(spec.app_label, "evennia_archive")
        self.assertEqual(spec.alias, "archive")

    def test_app_label_and_alias_are_required(self):
        """SP-07 — omitting either app_label or alias raises."""
        with self.assertRaises(TypeError):
            AliasSpec(alias="xrpl")
        with self.assertRaises(TypeError):
            AliasSpec(app_label="fcm_xrpl")

    def test_a_spec_is_frozen(self):
        """SP-08 — assigning to a field raises."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.alias = "something_else"

    def test_an_unknown_field_raises(self):
        """SP-09 — an unknown field name raises at construction."""
        with self.assertRaises(TypeError):
            AliasSpec(app_label="fcm_xrpl", alias="xrpl", alais="typo")

    def test_spec_module_imports_nothing_from_django(self):
        """SP-10 — spec.py imports nothing from Django."""
        self.assertEqual(django_imports(spec_module), [])

    def test_conn_max_age_says_nothing_by_default(self):
        """SP-11 — conn_max_age defaults to the UNSET sentinel."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        self.assertIs(spec.conn_max_age, UNSET)

    def test_a_spec_keeps_the_conn_max_age_it_was_given(self):
        """SP-12 — a spec that sets it keeps the value, None included."""
        self.assertEqual(
            AliasSpec(app_label="a", alias="a", conn_max_age=60).conn_max_age, 60
        )
        self.assertIsNone(
            AliasSpec(app_label="b", alias="b", conn_max_age=None).conn_max_age
        )

    def test_session_options_say_nothing_by_default(self):
        """SP-13 — session_options defaults to the UNSET sentinel."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        self.assertIs(spec.session_options, UNSET)

    def test_required_extensions_are_empty_by_default(self):
        """SP-15 — required_extensions defaults to empty."""
        spec = AliasSpec(app_label="fcm_xrpl", alias="xrpl")

        self.assertEqual(tuple(spec.required_extensions), ())

    def test_a_spec_keeps_the_extensions_it_declared(self):
        """SP-16 — a spec that declares extensions keeps them."""
        spec = AliasSpec(
            app_label="evennia_ai_memory",
            alias="ai_memory",
            required_extensions=("vector",),
        )

        self.assertEqual(tuple(spec.required_extensions), ("vector",))

    def test_a_spec_keeps_the_session_options_it_was_given(self):
        """SP-14 — a spec that sets them keeps the mapping."""
        options = {"hnsw.iterative_scan": "relaxed_order"}

        spec = AliasSpec(
            app_label="evennia_ai_memory",
            alias="ai_memory",
            session_options=options,
        )

        self.assertEqual(spec.session_options, options)


class ValidateSpecsTest(unittest.TestCase):
    """validate_specs — judging the specs once they are all in hand."""

    def test_a_valid_list_passes(self):
        """VS-01 — a valid list passes and returns nothing."""
        specs = [
            AliasSpec(app_label="fcm_xrpl", alias="xrpl"),
            AliasSpec(app_label="evennia_archive", alias="archive"),
        ]

        self.assertIsNone(validate_specs(specs))

    def test_an_empty_list_passes(self):
        """VS-02 — an empty list passes."""
        self.assertIsNone(validate_specs([]))

    def test_two_specs_claiming_one_alias_raise(self):
        """VS-03 — two specs claiming one alias raise, naming both app labels."""
        specs = [
            AliasSpec(app_label="library_one", alias="shared"),
            AliasSpec(app_label="library_two", alias="shared"),
        ]

        with self.assertRaises(SpecValidationError) as caught:
            validate_specs(specs)

        message = str(caught.exception)
        self.assertIn("shared", message)
        self.assertIn("library_one", message)
        self.assertIn("library_two", message)

    def test_two_specs_claiming_one_app_label_raise(self):
        """VS-04 — two specs claiming one app_label raise, naming both aliases."""
        specs = [
            AliasSpec(app_label="one_library", alias="alias_one"),
            AliasSpec(app_label="one_library", alias="alias_two"),
        ]

        with self.assertRaises(SpecValidationError) as caught:
            validate_specs(specs)

        message = str(caught.exception)
        self.assertIn("one_library", message)
        self.assertIn("alias_one", message)
        self.assertIn("alias_two", message)

    def test_an_empty_alias_raises(self):
        """VS-05 — an empty or whitespace-only alias raises."""
        with self.assertRaises(SpecValidationError):
            validate_specs([AliasSpec(app_label="fcm_xrpl", alias="")])
        with self.assertRaises(SpecValidationError):
            validate_specs([AliasSpec(app_label="fcm_xrpl", alias="   ")])

    def test_an_empty_app_label_raises(self):
        """VS-06 — an empty or whitespace-only app_label raises."""
        with self.assertRaises(SpecValidationError):
            validate_specs([AliasSpec(app_label="", alias="xrpl")])
        with self.assertRaises(SpecValidationError):
            validate_specs([AliasSpec(app_label="   ", alias="xrpl")])

    def test_an_alias_of_default_raises(self):
        """VS-07 — an alias of "default" raises."""
        specs = [AliasSpec(app_label="fcm_xrpl", alias="default")]

        with self.assertRaises(SpecValidationError) as caught:
            validate_specs(specs)

        self.assertIn("default", str(caught.exception))
        self.assertIn("fcm_xrpl", str(caught.exception))

    def test_an_alias_that_cannot_be_an_environment_variable_raises(self):
        """VS-09 — an alias that is not a valid environment-variable name."""
        for alias in ("my-alias", "my alias", "2fast", "alias!"):
            with self.assertRaises(SpecValidationError, msg=alias):
                validate_specs([AliasSpec(app_label="app", alias=alias)])

        for alias in ("ai_memory", "xrpl", "messagebus2"):
            self.assertIsNone(
                validate_specs([AliasSpec(app_label="app", alias=alias)]), alias
            )

    def test_every_problem_is_reported_in_one_raise(self):
        """VS-08 — several problems at once produce one raise, naming all."""
        specs = [
            AliasSpec(app_label="library_one", alias="shared"),
            AliasSpec(app_label="library_two", alias="shared"),
            AliasSpec(app_label="", alias="nameless_app"),
            AliasSpec(app_label="library_four", alias="default"),
        ]

        with self.assertRaises(SpecValidationError) as caught:
            validate_specs(specs)

        message = str(caught.exception)
        self.assertIn("shared", message)
        self.assertIn("nameless_app", message)
        self.assertIn("library_four", message)


class ResolveDatabaseTest(unittest.TestCase):
    """resolve_database — the three rungs, for one spec."""

    def spec(self, **overrides):
        """An AliasSpec, with the fields a case cares about overridden."""
        fields = {"app_label": "fcm_xrpl", "alias": "xrpl"}
        fields.update(overrides)
        return AliasSpec(**fields)

    def test_the_alias_own_url_is_used_when_set(self):
        """RS-01 — DATABASE_URL_<ALIAS> set: the entry is that URL parsed."""
        env = {"DATABASE_URL_XRPL": OWN_URL}

        entry = resolve_database(self.spec(), GAME_DIR, env)

        self.assertEqual(entry["HOST"], "own.host")
        self.assertEqual(entry["NAME"], "own_db")
        self.assertIn("postgresql", entry["ENGINE"])

    def test_the_common_url_is_used_when_the_alias_has_none(self):
        """RS-02 — only the common URL set: the entry is that URL parsed."""
        env = {"DATABASE_URL": COMMON_URL}

        entry = resolve_database(self.spec(), GAME_DIR, env)

        self.assertEqual(entry["HOST"], "common.host")
        self.assertEqual(entry["NAME"], "common_db")

    def test_no_url_falls_back_to_a_sqlite_file(self):
        """RS-03 — neither set: SQLite at <game_dir>/server/<sqlite_filename>."""
        entry = resolve_database(self.spec(), GAME_DIR, {})

        self.assertEqual(entry["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(
            entry["NAME"], os.path.join(GAME_DIR, "server", "xrpl.db3")
        )

    def test_the_alias_own_url_wins_over_the_common_one(self):
        """RS-04 — both set: the alias's own URL wins."""
        env = {"DATABASE_URL_XRPL": OWN_URL, "DATABASE_URL": COMMON_URL}

        entry = resolve_database(self.spec(), GAME_DIR, env)

        self.assertEqual(entry["HOST"], "own.host")

    def test_the_variable_read_is_the_alias_upper_cased(self):
        """RS-05 — ai_memory reads DATABASE_URL_AI_MEMORY."""
        self.assertEqual(alias_url_variable("ai_memory"), "DATABASE_URL_AI_MEMORY")

        env = {"DATABASE_URL_AI_MEMORY": OWN_URL}
        entry = resolve_database(
            self.spec(app_label="evennia_ai_memory", alias="ai_memory"),
            GAME_DIR,
            env,
        )

        self.assertEqual(entry["HOST"], "own.host")

    def test_the_common_variable_name_comes_from_the_argument(self):
        """RS-06 — a caller naming a different common variable is honoured."""
        env = {"GAME_DATABASE_URL": COMMON_URL, "DATABASE_URL": OWN_URL}

        entry = resolve_database(
            self.spec(), GAME_DIR, env, common_url_var="GAME_DATABASE_URL"
        )

        self.assertEqual(entry["HOST"], "common.host")

    def test_the_real_environment_is_never_consulted(self):
        """RS-07 — only the mapping passed in is read."""
        os.environ["DATABASE_URL_XRPL"] = OWN_URL
        self.addCleanup(os.environ.pop, "DATABASE_URL_XRPL", None)

        entry = resolve_database(self.spec(), GAME_DIR, {})

        self.assertEqual(entry["ENGINE"], "django.db.backends.sqlite3")

    def test_an_empty_variable_counts_as_unset(self):
        """RS-08 — a variable set to an empty string falls through."""
        env = {"DATABASE_URL_XRPL": "", "DATABASE_URL": COMMON_URL}

        entry = resolve_database(self.spec(), GAME_DIR, env)

        self.assertEqual(entry["HOST"], "common.host")

        entry = resolve_database(self.spec(), GAME_DIR, {"DATABASE_URL": ""})

        self.assertEqual(entry["ENGINE"], "django.db.backends.sqlite3")

    def test_a_spec_refusing_the_common_db_raises_on_that_rung(self):
        """RS-09 — allow_sharing_common_db=False and only the common URL set."""
        env = {"DATABASE_URL": COMMON_URL}

        with self.assertRaises(SharedDatabaseRefused) as caught:
            resolve_database(
                self.spec(alias="archive", allow_sharing_common_db=False),
                GAME_DIR,
                env,
            )

        message = str(caught.exception)
        self.assertIn("archive", message)
        self.assertIn("DATABASE_URL_ARCHIVE", message)

    def test_a_spec_refusing_the_common_db_accepts_its_own_url(self):
        """RS-10 — allow_sharing_common_db=False with its own URL resolves."""
        env = {"DATABASE_URL_ARCHIVE": OWN_URL, "DATABASE_URL": COMMON_URL}

        entry = resolve_database(
            self.spec(alias="archive", allow_sharing_common_db=False),
            GAME_DIR,
            env,
        )

        self.assertEqual(entry["HOST"], "own.host")

    def test_a_spec_refusing_the_common_db_still_falls_back_to_sqlite(self):
        """RS-11 — allow_sharing_common_db=False with neither set is fine."""
        entry = resolve_database(
            self.spec(alias="archive", allow_sharing_common_db=False),
            GAME_DIR,
            {},
        )

        self.assertEqual(
            entry["NAME"], os.path.join(GAME_DIR, "server", "archive.db3")
        )

    def test_the_sqlite_entry_uses_the_declared_filename(self):
        """RS-12 — an explicit sqlite_filename is the file used."""
        entry = resolve_database(
            self.spec(sqlite_filename="ledger.db3"), GAME_DIR, {}
        )

        self.assertEqual(
            entry["NAME"], os.path.join(GAME_DIR, "server", "ledger.db3")
        )

    def test_the_entry_carries_the_conn_max_age_it_was_given(self):
        """RS-13 — the game-wide value lands on the entry."""
        env = {"DATABASE_URL_XRPL": OWN_URL}

        entry = resolve_database(self.spec(), GAME_DIR, env, default_conn_max_age=120)

        self.assertEqual(entry["CONN_MAX_AGE"], 120)

    def test_a_spec_overrides_the_game_wide_conn_max_age(self):
        """RS-14 — a spec's own value wins, for that alias only."""
        env = {"DATABASE_URL_XRPL": OWN_URL}

        entry = resolve_database(
            self.spec(conn_max_age=600), GAME_DIR, env, default_conn_max_age=0
        )

        self.assertEqual(entry["CONN_MAX_AGE"], 600)

    def test_none_on_a_spec_is_a_value_not_an_absence(self):
        """RS-15 — conn_max_age=None means persist forever, not "unset"."""
        env = {"DATABASE_URL_XRPL": OWN_URL}

        entry = resolve_database(
            self.spec(conn_max_age=None), GAME_DIR, env, default_conn_max_age=0
        )

        self.assertIsNone(entry["CONN_MAX_AGE"])

    def test_conn_max_age_is_applied_on_every_rung(self):
        """RS-16 — including SQLite; no branch on engine."""
        for env in (
            {"DATABASE_URL_XRPL": OWN_URL},
            {"DATABASE_URL": COMMON_URL},
            {},
        ):
            entry = resolve_database(self.spec(), GAME_DIR, env, default_conn_max_age=45)
            self.assertEqual(entry["CONN_MAX_AGE"], 45, msg=f"env={env}")

    def test_session_options_are_rendered_into_the_entry(self):
        """RS-17 — rendered as -c name=value pairs into OPTIONS["options"]."""
        env = {"DATABASE_URL_XRPL": OWN_URL}

        entry = resolve_database(
            self.spec(),
            GAME_DIR,
            env,
            default_session_options={"statement_timeout": "5s"},
        )

        self.assertIn("-c statement_timeout=5s", entry["OPTIONS"]["options"])

    def test_a_spec_overrides_the_game_wide_session_options(self):
        """RS-18 — a spec's own mapping wins, for that alias only."""
        env = {"DATABASE_URL_XRPL": OWN_URL}

        entry = resolve_database(
            self.spec(session_options={"hnsw.iterative_scan": "relaxed_order"}),
            GAME_DIR,
            env,
            default_session_options={"statement_timeout": "5s"},
        )

        rendered = entry["OPTIONS"]["options"]
        self.assertIn("-c hnsw.iterative_scan=relaxed_order", rendered)
        self.assertNotIn("statement_timeout", rendered)

    def test_session_options_are_appended_to_what_the_url_produced(self):
        """RS-19 — a ?sslmode=require in the URL survives."""
        env = {"DATABASE_URL_XRPL": OWN_URL + "?sslmode=require"}

        entry = resolve_database(
            self.spec(),
            GAME_DIR,
            env,
            default_session_options={"statement_timeout": "5s"},
        )

        self.assertEqual(entry["OPTIONS"]["sslmode"], "require")
        self.assertIn("-c statement_timeout=5s", entry["OPTIONS"]["options"])

    def test_session_options_are_skipped_on_sqlite(self):
        """RS-20 — a libpq string would break a SQLite connection."""
        entry = resolve_database(
            self.spec(session_options={"statement_timeout": "5s"}),
            GAME_DIR,
            {},
        )

        self.assertNotIn("OPTIONS", entry)


class IsSplitTest(unittest.TestCase):
    """is_split and split_aliases — which aliases are on a database of their own."""

    def test_an_alias_with_its_own_url_is_split(self):
        """SL-01 — the alias's own URL is set: split."""
        self.assertTrue(is_split("xrpl", {"DATABASE_URL_XRPL": OWN_URL}))

    def test_an_alias_on_only_the_common_url_is_not_split(self):
        """SL-02 — only the common URL is set: not split."""
        self.assertFalse(is_split("xrpl", {"DATABASE_URL": COMMON_URL}))

    def test_an_alias_with_no_urls_at_all_is_split(self):
        """SL-03 — neither set: split, because each alias is its own file."""
        self.assertTrue(is_split("xrpl", {}))

    def test_an_alias_with_both_urls_is_split(self):
        """SL-04 — both set: split."""
        env = {"DATABASE_URL_XRPL": OWN_URL, "DATABASE_URL": COMMON_URL}

        self.assertTrue(is_split("xrpl", env))

    def test_the_common_variable_name_comes_from_the_argument(self):
        """SL-05 — a caller naming a different common variable is honoured."""
        env = {"GAME_DATABASE_URL": COMMON_URL}

        self.assertFalse(is_split("xrpl", env, common_url_var="GAME_DATABASE_URL"))
        self.assertTrue(is_split("xrpl", env))

    def test_an_empty_variable_counts_as_unset(self):
        """SL-06 — an empty string counts as unset, in either position."""
        self.assertTrue(is_split("xrpl", {"DATABASE_URL": ""}))
        self.assertFalse(
            is_split("xrpl", {"DATABASE_URL_XRPL": "", "DATABASE_URL": COMMON_URL})
        )

    def test_the_real_environment_is_never_consulted(self):
        """SL-07 — only the mapping passed in is read."""
        os.environ["DATABASE_URL"] = COMMON_URL
        self.addCleanup(os.environ.pop, "DATABASE_URL", None)

        self.assertTrue(is_split("xrpl", {}))

    def test_split_aliases_returns_the_split_subset_in_order(self):
        """SL-08 — split_aliases returns the split aliases, in spec order."""
        specs = [
            AliasSpec(app_label="fcm_xrpl", alias="xrpl"),
            AliasSpec(app_label="evennia_ai_memory", alias="ai_memory"),
            AliasSpec(app_label="evennia_archive", alias="archive"),
        ]
        env = {
            "DATABASE_URL": COMMON_URL,
            "DATABASE_URL_ARCHIVE": OWN_URL,
            "DATABASE_URL_XRPL": OWN_URL,
        }

        self.assertEqual(split_aliases(specs, env), ["xrpl", "archive"])

    def test_split_aliases_returns_nothing_when_all_share(self):
        """SL-09 — no spec split: an empty list."""
        specs = [
            AliasSpec(app_label="fcm_xrpl", alias="xrpl"),
            AliasSpec(app_label="evennia_ai_memory", alias="ai_memory"),
        ]

        self.assertEqual(split_aliases(specs, {"DATABASE_URL": COMMON_URL}), [])

    def test_split_aliases_returns_all_of_them_on_sqlite(self):
        """SL-10 — every spec split: every alias, none omitted."""
        specs = [
            AliasSpec(app_label="fcm_xrpl", alias="xrpl"),
            AliasSpec(app_label="evennia_ai_memory", alias="ai_memory"),
        ]

        self.assertEqual(split_aliases(specs, {}), ["xrpl", "ai_memory"])


class CascadeRouterTest(unittest.TestCase):
    """CascadeRouter — one parameterised router, built from a spec."""

    def router(self, **overrides):
        """A router over an AliasSpec, with the fields a case cares about set."""
        fields = {"app_label": "fcm_xrpl", "alias": "xrpl"}
        fields.update(overrides)
        return CascadeRouter(AliasSpec(**fields))

    def test_reads_of_our_models_go_to_our_alias(self):
        """RT-01 — db_for_read returns the alias for a model of its own app."""
        self.assertEqual(self.router().db_for_read(model("fcm_xrpl")), "xrpl")

    def test_writes_of_our_models_go_to_our_alias(self):
        """RT-02 — db_for_write returns the alias for a model of its own app."""
        self.assertEqual(self.router().db_for_write(model("fcm_xrpl")), "xrpl")

    def test_a_foreign_model_gets_no_answer(self):
        """RT-03 — both return None for a foreign model."""
        router = self.router()
        foreign = model("evennia_archive")

        self.assertIsNone(router.db_for_read(foreign))
        self.assertIsNone(router.db_for_write(foreign))

    def test_our_app_may_migrate_onto_our_alias(self):
        """RT-04 — allow_migrate is True for its own app on its own alias."""
        self.assertIs(self.router().allow_migrate("xrpl", "fcm_xrpl"), True)

    def test_our_app_may_not_migrate_anywhere_else(self):
        """RT-05 — allow_migrate is False for its own app on any other alias."""
        router = self.router()

        self.assertIs(router.allow_migrate("default", "fcm_xrpl"), False)
        self.assertIs(router.allow_migrate("archive", "fcm_xrpl"), False)

    def test_a_foreign_app_is_refused_our_alias_by_default(self):
        """RT-06 — allow_foreign_tables_in_own_db=False refuses a foreign app."""
        router = self.router()

        self.assertIs(router.allow_migrate("xrpl", "evennia_archive"), False)

    def test_a_foreign_app_may_join_us_when_the_spec_allows_it(self):
        """RT-07 — allow_foreign_tables_in_own_db=True defers instead."""
        router = self.router(
            app_label="evennia_archive",
            alias="archive",
            allow_foreign_tables_in_own_db=True,
        )

        self.assertIsNone(router.allow_migrate("archive", "objects"))

    def test_a_foreign_app_on_a_foreign_alias_gets_no_opinion(self):
        """RT-08 — allow_migrate is None for a foreign app on a foreign alias."""
        self.assertIsNone(self.router().allow_migrate("archive", "evennia_archive"))

    def test_a_relation_between_two_of_ours_is_allowed(self):
        """RT-09 — allow_relation is True when both models are its own."""
        router = self.router()

        self.assertIs(
            router.allow_relation(model("fcm_xrpl"), model("fcm_xrpl")), True
        )

    def test_a_relation_touching_a_foreign_model_gets_no_opinion(self):
        """RT-10 — allow_relation is None whether one or both are foreign."""
        router = self.router()
        ours = model("fcm_xrpl")
        theirs = model("evennia_archive")

        self.assertIsNone(router.allow_relation(ours, theirs))
        self.assertIsNone(router.allow_relation(theirs, ours))
        self.assertIsNone(router.allow_relation(theirs, theirs))

    def test_two_routers_each_answer_only_for_their_own_app(self):
        """RT-11 — the co-installed case: neither captures the other's models."""
        xrpl = self.router()
        archive = self.router(app_label="evennia_archive", alias="archive")

        self.assertEqual(xrpl.db_for_read(model("fcm_xrpl")), "xrpl")
        self.assertIsNone(archive.db_for_read(model("fcm_xrpl")))
        self.assertEqual(archive.db_for_read(model("evennia_archive")), "archive")
        self.assertIsNone(xrpl.db_for_read(model("evennia_archive")))

    def test_the_app_label_and_the_alias_are_read_separately(self):
        """RT-12 — routes on the app label, returns the alias."""
        router = self.router(app_label="evennia_archive", alias="archive")

        self.assertEqual(router.db_for_read(model("evennia_archive")), "archive")
        self.assertIsNone(router.db_for_read(model("archive")))

    def test_router_module_imports_nothing_from_django(self):
        """RT-13 — router.py imports nothing from Django."""
        self.assertEqual(django_imports(router_module), [])


class ConfigureTest(unittest.TestCase):
    """configure — the one call a consumer makes."""

    def setUp(self):
        self.apps = AppTree()
        self.addCleanup(self.apps.teardown)

    def game_databases(self, name="evennia.db3"):
        """A consumer's DATABASES, with the game on SQLite.

        Not called ``databases``: Django's test runner reads a
        ``databases`` attribute off every TestCase to decide which databases
        to set up, and a method there breaks collection for the whole suite.
        """
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": os.path.join(GAME_DIR, "server", name),
            }
        }

    def app(self, name, **fields):
        """An app declaring a real AliasSpec."""
        return self.apps.add(name, spec_module_source(**fields))

    def test_every_discovered_spec_gets_an_entry(self):
        """CF-01 — returns DATABASES carrying an entry per discovered spec."""
        apps = [
            self.app("cf01_xrpl", app_label="cf01_xrpl", alias="xrpl"),
            self.app("cf01_bus", app_label="cf01_bus", alias="messagebus"),
        ]

        databases, _ = configure(self.game_databases(), apps, GAME_DIR, {})

        self.assertIn("xrpl", databases)
        self.assertIn("messagebus", databases)

    def test_the_default_entry_is_left_alone(self):
        """CF-02 — the default entry is exactly as it was given."""
        given = self.game_databases()
        apps = [self.app("cf02_app", app_label="cf02_app", alias="xrpl")]

        databases, _ = configure(given, apps, GAME_DIR, {})

        self.assertEqual(databases["default"], given["default"])

    def test_routers_are_built_for_exactly_the_split_aliases(self):
        """CF-03 — routers for the split aliases, and none for the rest."""
        apps = [
            self.app("cf03_xrpl", app_label="cf03_xrpl", alias="xrpl"),
            self.app("cf03_bus", app_label="cf03_bus", alias="messagebus"),
        ]
        env = {"DATABASE_URL": COMMON_URL, "DATABASE_URL_XRPL": OWN_URL}

        _, routers = configure(self.game_databases(), apps, GAME_DIR, env)

        self.assertEqual([router.spec.alias for router in routers], ["xrpl"])

    def test_nothing_split_means_no_routers(self):
        """CF-04 — no alias split: an empty router list."""
        apps = [self.app("cf04_app", app_label="cf04_app", alias="xrpl")]

        _, routers = configure(
            self.game_databases(), apps, GAME_DIR, {"DATABASE_URL": COMMON_URL}
        )

        self.assertEqual(routers, [])

    def test_everything_split_means_a_router_each_in_spec_order(self):
        """CF-05 — every alias split: one router each, in spec order."""
        apps = [
            self.app("cf05_bus", app_label="cf05_bus", alias="messagebus"),
            self.app("cf05_xrpl", app_label="cf05_xrpl", alias="xrpl"),
        ]

        _, routers = configure(self.game_databases(), apps, GAME_DIR, {})

        self.assertEqual(
            [router.spec.alias for router in routers], ["messagebus", "xrpl"]
        )

    def test_no_specs_changes_nothing(self):
        """CF-06 — no specs discovered: databases unchanged, no routers."""
        self.apps.add("cf06_bare")
        given = self.game_databases()

        databases, routers = configure(given, ["cf06_bare"], GAME_DIR, {})

        self.assertEqual(databases, given)
        self.assertEqual(routers, [])

    def test_the_databases_argument_is_not_mutated(self):
        """CF-07 — the dict it was handed is not mutated."""
        given = self.game_databases()
        apps = [self.app("cf07_app", app_label="cf07_app", alias="xrpl")]

        configure(given, apps, GAME_DIR, {})

        self.assertEqual(list(given), ["default"])

    def test_the_routers_are_instances_carrying_their_spec(self):
        """CF-08 — routers are CascadeRouter instances, not dotted paths."""
        apps = [self.app("cf08_app", app_label="cf08_app", alias="xrpl")]

        _, routers = configure(self.game_databases(), apps, GAME_DIR, {})

        self.assertIsInstance(routers[0], CascadeRouter)
        self.assertEqual(routers[0].spec.app_label, "cf08_app")

    def test_an_invalid_spec_set_is_refused(self):
        """CF-09 — validate_specs is reached rather than skipped."""
        apps = [
            self.app("cf09_one", app_label="cf09_one", alias="shared"),
            self.app("cf09_two", app_label="cf09_two", alias="shared"),
        ]

        with self.assertRaises(SpecValidationError):
            configure(self.game_databases(), apps, GAME_DIR, {})

    def test_a_broken_db_spec_propagates(self):
        """CF-10 — discover_specs' errors propagate unchanged."""
        self.apps.add("cf10_app", BROKEN_IMPORT_SPEC_MODULE)

        with self.assertRaises(SpecImportError):
            configure(self.game_databases(), ["cf10_app"], GAME_DIR, {})

    def test_the_common_variable_name_reaches_both_steps(self):
        """CF-11 — common_url_var reaches resolution and the split decision."""
        apps = [self.app("cf11_app", app_label="cf11_app", alias="xrpl")]
        env = {"GAME_DATABASE_URL": COMMON_URL}

        databases, routers = configure(
            self.game_databases(),
            apps,
            GAME_DIR,
            env,
            common_url_var="GAME_DATABASE_URL",
        )

        self.assertEqual(databases["xrpl"]["HOST"], "common.host")
        self.assertEqual(routers, [])

    def test_an_alias_landing_on_the_game_database_file_is_refused(self):
        """CF-12 — a SQLite path matching default's NAME raises."""
        apps = [
            self.app(
                "cf12_app",
                app_label="cf12_app",
                alias="xrpl",
                sqlite_filename="evennia.db3",
            )
        ]

        with self.assertRaises(GameDatabaseCollision) as caught:
            configure(self.game_databases(), apps, GAME_DIR, {})

        message = str(caught.exception)
        self.assertIn("xrpl", message)
        self.assertIn("evennia.db3", message)

    def test_a_postgres_default_alongside_sqlite_is_not_a_collision(self):
        """CF-13 — the check fires only where default is SQLite."""
        given = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "evennia.db3",
                "HOST": "common.host",
            }
        }
        apps = [
            self.app(
                "cf13_app",
                app_label="cf13_app",
                alias="xrpl",
                sqlite_filename="evennia.db3",
            )
        ]

        databases, _ = configure(given, apps, GAME_DIR, {})

        self.assertEqual(databases["xrpl"]["ENGINE"], "django.db.backends.sqlite3")

    def test_conn_max_age_defaults_to_zero_and_reaches_every_entry(self):
        """CF-14 — the game-wide default is 0, applied to every alias."""
        apps = [
            self.app("cf14_one", app_label="cf14_one", alias="one"),
            self.app("cf14_two", app_label="cf14_two", alias="two"),
        ]

        databases, _ = configure(self.game_databases(), apps, GAME_DIR, {})

        self.assertEqual(databases["one"]["CONN_MAX_AGE"], 0)
        self.assertEqual(databases["two"]["CONN_MAX_AGE"], 0)

        databases, _ = configure(
            self.game_databases(), apps, GAME_DIR, {}, default_conn_max_age=300
        )

        self.assertEqual(databases["one"]["CONN_MAX_AGE"], 300)

    def test_a_consumers_own_routers_are_kept(self):
        """CF-16 — theirs are preserved, ours appended after."""
        apps = [self.app("cf16_app", app_label="cf16_app", alias="xrpl")]
        theirs = ["world.routers.MyRouter"]

        _, routers = configure(
            self.game_databases(), apps, GAME_DIR, {}, routers=theirs
        )

        self.assertEqual(routers[0], "world.routers.MyRouter")
        self.assertIsInstance(routers[1], CascadeRouter)
        self.assertEqual(theirs, ["world.routers.MyRouter"])

    def test_session_options_default_to_empty_and_reach_every_entry(self):
        """CF-15 — default_session_options defaults to empty."""
        apps = [
            self.app("cf15_one", app_label="cf15_one", alias="one"),
            self.app("cf15_two", app_label="cf15_two", alias="two"),
        ]

        databases, _ = configure(self.game_databases(), apps, GAME_DIR, {})

        self.assertNotIn("OPTIONS", databases["one"])

        env = {"DATABASE_URL": COMMON_URL}
        databases, _ = configure(
            self.game_databases(),
            apps,
            GAME_DIR,
            env,
            default_session_options={"statement_timeout": "5s"},
        )

        for alias in ("one", "two"):
            self.assertIn(
                "-c statement_timeout=5s", databases[alias]["OPTIONS"]["options"]
            )


class CheckSettingsTest(unittest.TestCase):
    """check_settings — the boot check, in AppConfig.ready()."""

    def setUp(self):
        self.apps = AppTree()
        self.addCleanup(self.apps.teardown)
        self.distributions = {}
        self.requirements = {}

        patches = [
            mock.patch.object(
                config_module,
                "packages_distributions",
                lambda: dict(self.distributions),
            ),
            mock.patch.object(
                config_module,
                "requires",
                lambda name: self.requirements.get(name),
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def app(self, name, requires_us=None, **spec_fields):
        """An app, optionally shipping a spec and declaring a dependency.

        ``requires_us`` is the requirement string its distribution declares,
        or None for a distribution that does not depend on this library.
        """
        source = spec_module_source(**spec_fields) if spec_fields else None
        self.apps.add(name, source)
        if requires_us is not None:
            distribution = name.replace("_", "-")
            self.distributions[name.split(".")[0]] = [distribution]
            self.requirements[distribution] = [requires_us]
        return name

    def databases_with(self, *aliases):
        """A DATABASES dict carrying default and the named aliases."""
        entry = {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        return {alias: dict(entry) for alias in ("default",) + aliases}

    def test_a_dependent_app_declaring_a_spec_passes(self):
        """BC-01 — requires the library and has a db_spec: passes."""
        app = self.app(
            "bc01_app",
            requires_us="evennia-database-cascade",
            app_label="bc01_app",
            alias="xrpl",
        )

        self.assertIsNone(check_settings([app], self.databases_with("xrpl")))

    def test_a_dependent_app_with_no_spec_is_refused(self):
        """BC-02 — requires the library and has no db_spec: raises."""
        app = self.app("bc02_app", requires_us="evennia-database-cascade")

        with self.assertRaises(ImproperlyConfigured) as caught:
            check_settings([app], self.databases_with())

        message = str(caught.exception)
        self.assertIn("bc02_app", message)
        self.assertIn("db_spec", message)

    def test_an_optional_dependency_is_skipped(self):
        """BC-03 — a requirement carrying an extra marker is skipped."""
        app = self.app(
            "bc03_app",
            requires_us='evennia-database-cascade; extra == "postgres"',
        )

        self.assertIsNone(check_settings([app], self.databases_with()))

    def test_an_app_not_depending_on_us_is_ignored(self):
        """BC-04 — a distribution that does not require us is ignored."""
        app = self.app("bc04_app", requires_us="some-other-library>=2")

        self.assertIsNone(check_settings([app], self.databases_with()))

    def test_an_app_with_no_distribution_is_ignored(self):
        """BC-05 — a gamedir module has no metadata to read."""
        app = self.app("bc05_world")

        self.assertIsNone(check_settings([app], self.databases_with()))

    def test_a_declared_alias_present_in_databases_passes(self):
        """BC-06 — every app with a db_spec has its alias in DATABASES."""
        app = self.app("bc06_app", app_label="bc06_app", alias="xrpl")

        self.assertIsNone(check_settings([app], self.databases_with("xrpl")))

    def test_a_declared_alias_missing_from_databases_is_refused(self):
        """BC-07 — an alias absent from DATABASES raises, naming both."""
        app = self.app("bc07_app", app_label="bc07_app", alias="xrpl")

        with self.assertRaises(ImproperlyConfigured) as caught:
            check_settings([app], self.databases_with())

        message = str(caught.exception)
        self.assertIn("bc07_app", message)
        self.assertIn("xrpl", message)

    def test_two_missing_aliases_are_reported_together(self):
        """BC-08 — two such apps: one raise, naming both."""
        apps = [
            self.app("bc08_one", app_label="bc08_one", alias="xrpl"),
            self.app("bc08_two", app_label="bc08_two", alias="messagebus"),
        ]

        with self.assertRaises(ImproperlyConfigured) as caught:
            check_settings(apps, self.databases_with())

        message = str(caught.exception)
        self.assertIn("xrpl", message)
        self.assertIn("messagebus", message)

    def test_both_kinds_of_problem_are_reported_together(self):
        """BC-09 — both kinds at once: one raise, naming all of them."""
        apps = [
            self.app("bc09_silent", requires_us="evennia-database-cascade"),
            self.app("bc09_absent", app_label="bc09_absent", alias="xrpl"),
        ]

        with self.assertRaises(ImproperlyConfigured) as caught:
            check_settings(apps, self.databases_with())

        message = str(caught.exception)
        self.assertIn("bc09_silent", message)
        self.assertIn("xrpl", message)

    def test_ready_calls_the_check(self):
        """BC-12 — ready() calls check_settings, so it cannot go unrun."""
        from evennia_database_cascade import apps as apps_module

        with mock.patch.object(config_module, "check_settings") as checked:
            apps_module.CascadeConfig.ready(mock.Mock())

        checked.assert_called_once_with()


class MigrateAllTest(unittest.TestCase):
    """migrate_all — reaching every split alias."""

    def setUp(self):
        self.apps = AppTree()
        self.addCleanup(self.apps.teardown)
        self.calls = []
        # alias -> the extensions that database reports as installed.
        self.installed = {}
        # alias -> engine, so a case can make one non-Postgres.
        self.engines = {}

        def record(*args, **options):
            self.calls.append((args, options))

        def installed_extensions(alias):
            if "postgresql" not in self.engines.get(alias, "postgresql"):
                return None
            return set(self.installed.get(alias, ()))

        patches = [
            mock.patch.object(migrate_module, "call_command", record),
            mock.patch.object(
                migrate_module, "installed_extensions", installed_extensions
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def app(self, name, **spec_fields):
        """An app declaring a real AliasSpec."""
        return self.apps.add(name, spec_module_source(**spec_fields))

    def aliases_migrated(self):
        """The alias given to each `migrate --database` call, in order."""
        return [
            options["database"]
            for _, options in self.calls
            if "database" in options
        ]

    def test_the_bare_migrate_runs_first(self):
        """MG-01 — runs a bare migrate before anything else."""
        app = self.app("mg01_app", app_label="mg01_app", alias="xrpl")

        migrate_all([app], {})

        self.assertEqual(self.calls[0], (("migrate",), {}))

    def test_each_split_alias_gets_its_own_call_in_spec_order(self):
        """MG-02 — one migrate --database per split alias, in spec order."""
        apps = [
            self.app("mg02_bus", app_label="mg02_bus", alias="messagebus"),
            self.app("mg02_xrpl", app_label="mg02_xrpl", alias="xrpl"),
        ]

        migrate_all(apps, {})

        self.assertEqual(self.aliases_migrated(), ["messagebus", "xrpl"])

    def test_nothing_split_means_the_bare_call_only(self):
        """MG-03 — no split aliases: the bare call and nothing else."""
        app = self.app("mg03_app", app_label="mg03_app", alias="xrpl")

        migrate_all([app], {"DATABASE_URL": COMMON_URL})

        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.aliases_migrated(), [])

    def test_the_split_set_comes_from_split_aliases(self):
        """MG-04 — the split set is split_aliases' answer, not a second rule."""
        app = self.app("mg04_app", app_label="mg04_app", alias="xrpl")

        with mock.patch.object(
            migrate_module, "split_aliases", return_value=[]
        ) as derived:
            migrate_all([app], {})

        derived.assert_called_once()
        self.assertEqual(self.aliases_migrated(), [])

    def test_an_unsplit_alias_never_gets_its_own_call(self):
        """MG-05 — the bare migrate already covered it."""
        apps = [
            self.app("mg05_shared", app_label="mg05_shared", alias="shared"),
            self.app("mg05_own", app_label="mg05_own", alias="own"),
        ]
        env = {"DATABASE_URL": COMMON_URL, "DATABASE_URL_OWN": OWN_URL}

        migrate_all(apps, env)

        self.assertEqual(self.aliases_migrated(), ["own"])

    def test_a_failing_migrate_propagates(self):
        """MG-06 — a failing migrate reaches the caller rather than being swallowed."""
        app = self.app("mg06_app", app_label="mg06_app", alias="xrpl")

        # ValueError, not RuntimeError: NotImplementedError subclasses
        # RuntimeError, so a stubbed migrate_all would satisfy the assertion
        # for the wrong reason.
        def boom(*args, **options):
            raise ValueError("migrate blew up")

        with mock.patch.object(migrate_module, "call_command", boom):
            with self.assertRaises(ValueError):
                migrate_all([app], {})

    def test_the_common_variable_comes_from_the_setting(self):
        """MG-08 — CASCADE_COMMON_URL_VAR, defaulting to DATABASE_URL."""
        self.assertEqual(get_common_url_var(), "DATABASE_URL")

        with mock.patch.object(
            migrate_module, "get_common_url_var", lambda: "GAME_DATABASE_URL"
        ):
            app = self.app("mg08_app", app_label="mg08_app", alias="xrpl")
            migrate_all([app], {"GAME_DATABASE_URL": COMMON_URL})

        self.assertEqual(self.aliases_migrated(), [])

    def test_migrations_run_when_every_extension_is_present(self):
        """MG-11 — nothing missing, so the migrations run normally."""
        app = self.app(
            "mg11_app",
            app_label="mg11_app",
            alias="ai_memory",
            required_extensions=("vector",),
        )
        self.installed["ai_memory"] = ("vector",)

        migrate_all([app], {})

        self.assertEqual(self.aliases_migrated(), ["ai_memory"])

    def test_a_missing_extension_refuses_before_any_migration(self):
        """MG-12 — raises first, naming the extension and the command."""
        app = self.app(
            "mg12_app",
            app_label="mg12_app",
            alias="ai_memory",
            required_extensions=("vector",),
        )

        with self.assertRaises(ImproperlyConfigured) as caught:
            migrate_all([app], {})

        message = str(caught.exception)
        self.assertIn("vector", message)
        self.assertIn("ai_memory", message)
        self.assertIn("CREATE EXTENSION", message)
        self.assertEqual(self.calls, [])

    def test_every_missing_extension_is_reported_together(self):
        """MG-13 — several missing across aliases: one raise, naming all."""
        apps = [
            self.app(
                "mg13_one",
                app_label="mg13_one",
                alias="one",
                required_extensions=("vector",),
            ),
            self.app(
                "mg13_two",
                app_label="mg13_two",
                alias="two",
                required_extensions=("postgis",),
            ),
        ]

        with self.assertRaises(ImproperlyConfigured) as caught:
            migrate_all(apps, {})

        message = str(caught.exception)
        self.assertIn("vector", message)
        self.assertIn("postgis", message)

    def test_the_check_is_skipped_on_a_non_postgres_alias(self):
        """MG-14 — there are no extensions to have on SQLite."""
        app = self.app(
            "mg14_app",
            app_label="mg14_app",
            alias="xrpl",
            required_extensions=("vector",),
        )
        self.engines["xrpl"] = "django.db.backends.sqlite3"

        migrate_all([app], {})

        self.assertEqual(self.aliases_migrated(), ["xrpl"])

    def test_the_command_calls_migrate_all(self):
        """MG-09 — the management command is a wrapper, not a second path."""
        from evennia_database_cascade.management.commands import cascade_migrate

        with mock.patch.object(
            cascade_migrate, "migrate_all", return_value=["xrpl"]
        ) as called:
            cascade_migrate.Command().handle(verbosity=2)

        called.assert_called_once_with(verbosity=2)

    def test_options_are_forwarded_and_database_is_refused(self):
        """MG-10 — options pass through; a caller-supplied database raises."""
        app = self.app("mg10_app", app_label="mg10_app", alias="xrpl")

        migrate_all([app], {}, verbosity=2, interactive=False)

        self.assertEqual(self.calls[0][1], {"verbosity": 2, "interactive": False})

        with self.assertRaises(TypeError):
            migrate_all([app], {}, database="xrpl")


class LogShimTest(unittest.TestCase):
    """cascade_log — the logging shim.

    The shim is copied verbatim across the libraries, so these cases are the
    same shape as theirs. Evennia's logger is faked through sys.modules
    because the shim imports it lazily, inside the call.
    """

    def capture(self):
        """A fake Evennia logger recording every log_file call."""
        fake = mock.Mock()
        fake.log_file = mock.Mock()
        return fake

    def logging_as(self, fake):
        """Run with our fake standing in for evennia.utils.logger."""
        return mock.patch.dict(
            "sys.modules", {"evennia.utils": mock.Mock(logger=fake)}
        )

    def test_it_writes_to_the_library_log_file(self):
        """LG-01 — the call reaches log_file with cascade.log."""
        fake = self.capture()

        with self.logging_as(fake):
            cascade_log("resolved four aliases")

        fake.log_file.assert_called_once_with(
            "[INFO] resolved four aliases", filename="cascade.log"
        )

    def test_the_level_prefixes_the_message(self):
        """LG-02 — the level is written as [LEVEL] message."""
        fake = self.capture()

        with self.logging_as(fake):
            cascade_log("migrate failed", level="ERROR")

        fake.log_file.assert_called_once_with(
            "[ERROR] migrate failed", filename="cascade.log"
        )

    def test_an_unknown_level_coerces_to_info(self):
        """LG-03 — an unknown level degrades rather than raising."""
        fake = self.capture()

        with self.logging_as(fake):
            cascade_log("something", level="CRITICAL")

        fake.log_file.assert_called_once_with(
            "[INFO] something", filename="cascade.log"
        )

    def test_it_is_a_silent_noop_without_evennia(self):
        """LG-04 — outside an Evennia engine the call does nothing at all."""
        real_import = __import__

        def refuse_evennia(name, *args, **kwargs):
            if name == "evennia.utils":
                raise ImportError("no evennia here")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=refuse_evennia):
            self.assertIsNone(cascade_log("nobody hears this"))

    def test_trace_inside_an_except_block_appends_the_traceback(self):
        """LG-05 — trace=True carries the active exception."""
        fake = self.capture()

        with self.logging_as(fake):
            try:
                raise ValueError("the original problem")
            except ValueError:
                cascade_log("migrate failed", level="ERROR", trace=True)

        written = fake.log_file.call_args[0][0]
        self.assertIn("[ERROR] migrate failed", written)
        self.assertIn("the original problem", written)

    def test_trace_outside_an_except_block_adds_nothing(self):
        """LG-06 — no NoneType: None noise where there is no exception."""
        fake = self.capture()

        with self.logging_as(fake):
            cascade_log("no exception here", trace=True)

        fake.log_file.assert_called_once_with(
            "[INFO] no exception here", filename="cascade.log"
        )
