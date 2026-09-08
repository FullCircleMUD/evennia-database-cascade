# SPDX-License-Identifier: BSD-3-Clause
"""The one call a consumer makes, from their settings module.

Everything else in the library is a step of this: discovery finds the specs
the installed apps declare, validation judges the set, resolution places each
alias, and the router list follows from which of them ended up on a database
of their own.

**This module is on the settings path, so it imports nothing from Django and
never logs.** The shim reaches ``settings.LOG_DIR``, which raises before
``django.setup()``. Failures here raise, and the traceback is the record —
the server does not start, so there is no run to read a log file from. See
principle 8 in this repo's ``CLAUDE.md``.
"""

import os

from .config import DEFAULT_COMMON_URL_VAR, SQLITE_ENGINE
from .discovery import discover_specs, validate_specs
from .resolve import resolve_database, split_aliases
from .router import CascadeRouter


class GameDatabaseCollision(ValueError):
    """An alias's SQLite file is the game's own database file.

    Neither the spec nor the environment is wrong on its own — it is the
    combination, which is why this is not a ``SpecValidationError``. The
    alias would share every table with the game rather than having a set of
    its own, and a world rebuild would take both.
    """


def configure(
    databases,
    installed_apps,
    game_dir,
    env,
    common_url_var=DEFAULT_COMMON_URL_VAR,
):
    """Resolve every declared alias, and choose the routers to match.

    Called from a consumer's ``settings.py``, after their ``INSTALLED_APPS``
    edits and with both settings in scope:

        DATABASES, DATABASE_ROUTERS = configure(
            DATABASES, INSTALLED_APPS, GAME_DIR, os.environ
        )

    The databases dict is **copied** rather than edited. Both read the same
    at the call site, where the consumer reassigns; a function that silently
    changes its argument is worse to test and worse to reason about.

    ``default`` is not touched. It is the one entry Evennia already provides,
    and owning it would mean owning an edge case that is not this library's.

    Args:
        databases (dict): the consumer's ``DATABASES``, with ``default`` in
            it.
        installed_apps (Iterable[str]): their ``INSTALLED_APPS``.
        game_dir (str): the Evennia game directory.
        env (Mapping): environment variables to read.
        common_url_var (str): the variable naming the database every alias
            shares when it has none of its own.

    Returns:
        tuple: the new ``DATABASES``, and the ``DATABASE_ROUTERS`` list —
            ``CascadeRouter`` instances, one per split alias, in spec order.

    Raises:
        MissingAppError: an app in ``installed_apps`` could not be imported.
        SpecImportError: a ``db_spec`` exists and one of its imports failed.
        SpecValidationError: the specs say something unusable.
        SharedDatabaseRefused: an alias landed on the common database and its
            spec does not allow that.
        GameDatabaseCollision: an alias's SQLite file is the game's own.
    """
    specs = discover_specs(installed_apps)
    validate_specs(specs)

    resolved = dict(databases)
    for spec in specs:
        entry = resolve_database(spec, game_dir, env, common_url_var)
        _refuse_the_game_database_file(spec, entry, resolved["default"])
        resolved[spec.alias] = entry

    split = split_aliases(specs, env, common_url_var)
    routers = [CascadeRouter(spec) for spec in specs if spec.alias in split]

    return resolved, routers


def _refuse_the_game_database_file(spec, entry, default_entry):
    """Refuse an alias whose SQLite file is the game's own database.

    Compared against ``default``'s resolved ``NAME`` rather than against the
    literal ``evennia.db3``: that filename is Evennia's default rather than a
    fixed one, so a consumer who changed it would get no protection from a
    hardcoded check.

    Only meaningful where both are SQLite. A Postgres ``default`` has no file
    for an alias to collide with, so there is nothing to compare.

    Args:
        spec (AliasSpec): the alias being placed.
        entry (dict): what it resolved to.
        default_entry (dict): the game's own connection.

    Raises:
        GameDatabaseCollision: the two name one file.
    """
    if SQLITE_ENGINE not in (entry.get("ENGINE"), default_entry.get("ENGINE")):
        return
    if entry.get("ENGINE") != default_entry.get("ENGINE"):
        return

    ours = os.path.normcase(os.path.abspath(entry["NAME"]))
    theirs = os.path.normcase(os.path.abspath(default_entry["NAME"]))
    if ours != theirs:
        return

    raise GameDatabaseCollision(
        f"{spec.alias!r} resolves to {entry['NAME']}, which is the game's own "
        f"database. It would share every table with the game rather than have "
        f"a set of its own, and a world rebuild would take both. Give the "
        f"spec a different sqlite_filename, or a database of its own."
    )
