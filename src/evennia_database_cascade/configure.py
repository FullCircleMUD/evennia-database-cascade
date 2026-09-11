# SPDX-License-Identifier: BSD-3-Clause
"""The one call a consumer makes, from their settings module.

Everything else in the library is a step of this: discovery finds the specs
the installed apps declare, validation judges the set, resolution places each
alias, and the router list follows from which of them ended up on a database
of their own.

**This module is on the settings path, so it imports nothing from Django.**
Failures raise, and the traceback is the record, since the server does not
start.
"""

import os

from .config import (
    DEFAULT_COMMON_URL_VAR,
    DEFAULT_CONN_MAX_AGE,
    DEFAULT_SESSION_OPTIONS,
    SQLITE_ENGINE,
)
from .discovery import discover_specs, validate_specs
from .resolve import apply_connection_settings, parse_url, resolve_database, split_aliases
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
    routers=(),
    common_url_var=DEFAULT_COMMON_URL_VAR,
    default_conn_max_age=DEFAULT_CONN_MAX_AGE,
    default_session_options=DEFAULT_SESSION_OPTIONS,
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

    **The common URL names the game's database**, so when one is set,
    ``default`` is pointed at it along with every alias that has no URL of its
    own. That is what makes the shared rung mean *one* database rather than
    two. Without it the aliases move and the game does not: on Postgres the
    game stays quietly on SQLite while its libraries are on the server, and on
    SQLite an empty file appears that nothing will ever migrate.

    With no common URL set, ``default`` is left exactly as it was given —
    there is nothing for it to follow.

    Args:
        databases (dict): the consumer's ``DATABASES``, with ``default`` in
            it.
        installed_apps (Iterable[str]): their ``INSTALLED_APPS``.
        game_dir (str): the Evennia game directory.
        env (Mapping): environment variables to read.
        routers (Iterable): routers the consumer already had in
            ``DATABASE_ROUTERS``. Ours are appended after them. Passed in
            rather than replaced, because a consumer's own router being
            dropped would send whatever it routed to ``default`` with
            nothing said — the failure this library exists to prevent.
            Theirs come first: Django takes the first non-``None`` answer,
            and where both could answer, an explicit choice of theirs should
            win over ours.
        common_url_var (str): the variable naming the database every alias
            shares when it has none of its own.
        default_conn_max_age (int or None): how long a connection is kept
            before being closed, for every alias whose spec does not declare
            one of its own. Defaults to 0 — closed at the end of each unit of
            work, which is what a Twisted deployment needs.

            **Any spec can override this for its own alias**, and one that
            does wins. This value is what applies to everything that stayed
            quiet — which is most of them, and is the consumer's only lever
            over an alias belonging to a library they did not write.
        default_session_options (Mapping): Postgres session parameters for
            every alias whose spec declares none of its own. Empty by
            default — no session parameter is universal. A spec that sets its
            own replaces this for that alias.

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

    common_url = env.get(common_url_var) or None
    if common_url:
        entry = parse_url(common_url)
        apply_connection_settings(
            entry, default_conn_max_age, default_session_options
        )
        resolved["default"] = entry

    # Derived before the loop, because the collision check below is only
    # meaningful for an alias on a database of its own. One sharing the
    # game's database is not colliding with it — that is the arrangement.
    split = split_aliases(specs, env, common_url_var)

    for spec in specs:
        entry = resolve_database(
            spec,
            game_dir,
            env,
            common_url_var,
            default_conn_max_age,
            default_session_options,
        )
        if spec.alias in split:
            _refuse_the_game_database_file(spec, entry, resolved["default"])
        resolved[spec.alias] = entry

    ours = [CascadeRouter(spec) for spec in specs if spec.alias in split]

    return resolved, list(routers) + ours


def _refuse_the_game_database_file(spec, entry, default_entry):
    """Refuse an alias whose SQLite file is the game's own database.

    Compared against ``default``'s resolved ``NAME`` rather than against the
    literal ``evennia.db3``: that filename is Evennia's default rather than a
    fixed one, so a consumer who changed it would get no protection from a
    hardcoded check.

    Only meaningful where both are SQLite. A Postgres ``default`` has no file
    for an alias to collide with, so there is nothing to compare.

    **And only for a split alias.** One sharing the game's database through
    the common URL is meant to be there — that is the arrangement, not a
    mistake — so the caller checks membership of the split set first.

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
