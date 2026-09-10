# SPDX-License-Identifier: BSD-3-Clause
"""Finding the alias specs that a game's installed apps declare.

**This module runs before Django is awake, and that constrains how it is
written.** A consumer calls ``configure()`` from their ``settings.py``, so
importing this module happens while that settings file is still executing —
before ``django.setup()``, before the app registry exists, and before
``settings.INSTALLED_APPS`` is finished being built.

Four consequences, all load-bearing:

- **Nothing here imports Django**, at module scope or inside a function, and
  nothing it imports may import Django either. A Django import at this point
  raises before the server has started.
- **``installed_apps`` is an argument, not a read.** The list cannot be taken
  from ``settings``, because the settings module is mid-execution and has not
  finished defining it.
- **The app registry is unavailable.** ``django.apps`` cannot answer which
  modules an app has, so discovery walks the names it was handed and imports
  the candidate module directly.
- **The library's own modules on this path import no Django either.** Where
  one genuinely has to, it stays off the settings path and is reached by
  dotted path rather than imported.

The same rule applies to every module reachable from ``configure()``, and to
the package ``__init__.py``, which is the first file a consumer's
``from evennia_database_cascade import configure`` opens.
"""

import importlib

from .config import (
    ALIAS_URL_PREFIX,
    ENVIRONMENT_NAME,
    SPEC_ATTRIBUTE,
    SPEC_MODULE_NAME,
)


class MissingAppError(ImportError):
    """An app listed in ``INSTALLED_APPS`` could not be imported at all.

    A separate fault from ``SpecImportError`` and a separate message: nothing
    is wrong with a ``db_spec`` here, because there is no app to hold one.
    Django reports this too, at ``django.setup()``. This one fires earlier,
    because discovery reaches the app first.
    """


class SpecImportError(ImportError):
    """A ``db_spec`` module exists but one of its own imports failed.

    Subclasses ``ImportError`` rather than Django's ``ImproperlyConfigured``,
    which this module cannot reach — see the note above about Django not
    being awake yet.
    """


class SpecValidationError(ValueError):
    """A spec, or the set of them together, says something unusable.

    A ``ValueError`` rather than an ``ImportError``: everything imported
    cleanly, and what is wrong is the value declared.
    """


def discover_specs(installed_apps):
    """Return the alias specs declared by the given apps, in the order given.

    An app declares one by shipping a ``db_spec`` module. An app without one
    is skipped. Nothing is validated here and nothing is de-duplicated — two
    apps claiming one alias both come back, which is what lets the collision
    be reported rather than silently resolved.

    **A ``db_spec`` that exists and fails to import is not a skip.** Python
    raises ``ModuleNotFoundError`` both for an app with no ``db_spec`` and for
    a ``db_spec`` whose own imports are broken, so catching that exception
    wholesale would quietly drop a library whose spec file has a typo in it.
    Its alias would never be configured, its models would fall through to
    ``default``, and the game would start and run with its tables in the
    database they exist to stay out of. The two are told apart by the
    ``name`` on the exception.

    **Only ``ModuleNotFoundError`` is intercepted**, because it is the only
    one Python uses for two different situations. A ``db_spec`` that raises
    anything else is unambiguous already, so it propagates untouched and the
    consumer reads their own traceback with nothing of ours in the middle.

    Args:
        installed_apps (Iterable[str]): app names, as they appear in the
            consumer's ``INSTALLED_APPS``. Dotted names resolve like any
            other import path.

    Returns:
        list: the spec objects, as the declaring modules built them.

    Raises:
        MissingAppError: the app itself could not be imported, so there was
            never a ``db_spec`` to look for.
        SpecImportError: a ``db_spec`` module exists and one of its own
            imports failed. The message names the app, the module and the
            import that broke.

        Both chain the original exception, so the consumer's own error stays
        underneath.
    """
    specs = []
    for app in installed_apps:
        package = _app_package(app)
        if package is None:
            _refuse_the_missing_app(app)
        module_name = f"{package}.{SPEC_MODULE_NAME}"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as err:
            # The app simply has no spec — the ordinary case, and a skip.
            if err.name == module_name:
                continue
            # The spec is there and one of its own imports is broken. Left to
            # Python this is indistinguishable from the line above, so the
            # library would drop the app, leave its alias unconfigured, and
            # let its tables fall through to `default` with nothing said.
            raise SpecImportError(
                f"{app} ships a {module_name}, and importing it failed: it "
                f"imports {err.name!r}, which could not be found. Fix that "
                f"import — until it works, {app} has no database alias "
                f"configured and its tables will land in the game database."
            ) from err
        specs.append(getattr(module, SPEC_ATTRIBUTE))
    return specs


def _refuse_the_missing_app(app):
    """Raise for an ``INSTALLED_APPS`` entry with no package behind it.

    The absence is found by asking rather than by failing, so there is no
    exception to chain. One import is attempted here, on a path that is
    already about to raise, purely so the consumer's traceback carries
    Python's own account of what could not be found.

    Args:
        app (str): the entry as written in ``INSTALLED_APPS``.

    Raises:
        MissingAppError: always.
    """
    message = (
        f"{app!r} is listed in INSTALLED_APPS but no package behind it could "
        f"be found. Check the name for a typo, and that the package is "
        f"installed."
    )
    try:
        importlib.import_module(app)
    except ImportError as err:
        raise MissingAppError(message) from err
    raise MissingAppError(message)


def _app_package(app):
    """The importable package behind an ``INSTALLED_APPS`` entry.

    Django accepts two forms, and Evennia's own defaults use both —
    ``evennia.objects`` names a package, while
    ``evennia.web.utils.adminsite.EvenniaAdminApp`` names an ``AppConfig``
    class. Treating the second as a package makes every stock gamedir look
    like a missing app.

    Trailing segments are dropped until a package is reached, which handles
    both the ``<module>.<Class>`` and the ``<package>.apps.<Class>`` shapes
    without needing to import the class or ask Django, neither of which is
    available from a settings module.

    Args:
        app (str): the entry as written in ``INSTALLED_APPS``.

    Returns:
        str or None: the package name, or None where nothing behind it is a
            package — a typo, or something genuinely not installed.
    """
    from importlib.util import find_spec

    candidate = app
    while candidate:
        try:
            found = find_spec(candidate)
        except (ImportError, ValueError):
            found = None
        if found is not None and found.submodule_search_locations is not None:
            return candidate
        if "." not in candidate:
            return None
        candidate = candidate.rsplit(".", 1)[0]
    return None


def validate_specs(specs):
    """Refuse a set of specs that says something unusable.

    Everything checkable once every spec is in hand: the per-field shape the
    dataclass cannot enforce, and the collisions no single spec can see.

    **Every problem in one raise.** A consumer with two things wrong should
    get both, rather than fixing one, restarting, and being told about the
    next.

    The collision between an alias's SQLite file and the game's own database
    is deliberately not checked here — it needs ``game_dir`` to resolve a
    path, so it belongs to ``configure()``.

    Args:
        specs (list): the specs ``discover_specs`` returned.

    Returns:
        None.

    Raises:
        SpecValidationError: one or more specs are unusable. The message
            carries every problem found, not just the first.
    """
    problems = []

    for spec in specs:
        if not spec.alias.strip():
            problems.append(
                f"{spec.app_label or '<no app label>'} declares an empty "
                f"alias. The alias names the DATABASES key, and the "
                f"environment variable that can give it a database of its "
                f"own derives from it."
            )
        elif spec.alias == "default":
            problems.append(
                f"{spec.app_label} claims the alias 'default'. That is "
                f"Django's own connection, so taking it would replace the "
                f"game's database with this library's. Choose an alias of "
                f"its own."
            )
        elif not ENVIRONMENT_NAME.match(spec.alias):
            problems.append(
                f"{spec.app_label} declares the alias {spec.alias!r}, which "
                f"cannot name an environment variable. The alias becomes "
                f"{ALIAS_URL_PREFIX}<ALIAS>, so use letters, digits and "
                f"underscores only, and do not start with a digit."
            )

        if not spec.app_label.strip():
            problems.append(
                f"The spec for alias {spec.alias!r} declares an empty "
                f"app_label. The router matches models on it, so without "
                f"one nothing reaches that alias."
            )

    for alias, held in _sharing(specs, "alias").items():
        labels = ", ".join(sorted(spec.app_label for spec in held))
        problems.append(
            f"{labels} all claim the alias {alias!r}. An alias is one "
            f"database connection and only one app can own it."
        )

    for app_label, held in _sharing(specs, "app_label").items():
        aliases = ", ".join(sorted(spec.alias for spec in held))
        problems.append(
            f"{app_label!r} is declared against more than one alias "
            f"({aliases}). The router matches models on the app label, so it "
            f"cannot tell which connection they belong to."
        )

    if problems:
        raise SpecValidationError(" ".join(problems))


def _sharing(specs, attribute):
    """Specs grouped by a value more than one of them declares.

    Blank values are left out — an empty alias is already its own problem,
    and reporting two of them as a collision would say the wrong thing.

    Args:
        specs (list): the specs to group.
        attribute (str): the field to group on.

    Returns:
        dict: value -> the specs declaring it, for values held more than once.
    """
    groups = {}
    for spec in specs:
        value = getattr(spec, attribute).strip()
        if value:
            groups.setdefault(value, []).append(spec)
    return {value: held for value, held in groups.items() if len(held) > 1}
