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
        tree = ast.parse(pathlib.Path(spec_module.__file__).read_text())

        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")

        self.assertEqual(
            [name for name in imported if name.split(".")[0] == "django"], []
        )


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
