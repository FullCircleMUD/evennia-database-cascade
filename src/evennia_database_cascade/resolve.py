# SPDX-License-Identifier: BSD-3-Clause
"""Turning one spec and an environment into one database connection.

**This module is on the settings path, so it imports nothing from Django.**
See ``discovery.py`` for the full statement of that constraint.

Resolution and discovery are separate jobs and separate files: discovery
answers *which libraries declared an alias*, and this answers *where one
alias's data lives*. Neither needs the other.

What this module deliberately does not answer is whether an alias is
**split** — on a different database from the game's. ``is_split`` reads the
same environment and answers that separately, because the migrate helper runs
in another process where no ``DATABASES`` entry has been built and the
question still has to be answerable.
"""

import os

# The parser, not a validator: it turns a URL into a Django DATABASES entry
# and neither tests the connection nor checks the URL is complete.
import dj_database_url

from .config import (
    ALIAS_URL_PREFIX,
    DEFAULT_COMMON_URL_VAR,
    DEFAULT_CONN_MAX_AGE,
    DEFAULT_SESSION_OPTIONS,
    SQLITE_ENGINE,
    SQLITE_SUBDIRECTORY,
    UNSET,
)


class SharedDatabaseRefused(ValueError):
    """A spec that may not share the common database was offered it.

    Raised where the alias has no URL of its own, the common URL is set, and
    the spec declares ``allow_sharing_common_db=False``. Refusing rather than
    falling through to SQLite, because falling through would put a production
    database in a local file on a deployment that is otherwise not using one,
    with nothing to say so.
    """


def alias_url_variable(alias):
    """The environment variable naming a database of this alias's own.

    Args:
        alias (str): the alias.

    Returns:
        str: ``DATABASE_URL_<ALIAS>``, upper-cased.
    """
    return f"{ALIAS_URL_PREFIX}{alias.upper()}"


def parse_url(url):
    """Parse a database URL into a ``DATABASES`` entry.

    A named wrapper so ``configure()`` can place ``default`` the same way an
    alias is placed, rather than reaching for the parser itself.

    Args:
        url (str): the URL.

    Returns:
        dict: a Django ``DATABASES`` entry, without connection settings.
    """
    return dj_database_url.parse(url)


def apply_connection_settings(entry, conn_max_age, session_options):
    """Put the connection settings on an entry, whatever produced it.

    Shared so ``default`` gets exactly what an alias gets — a game database
    with a different connection lifetime from the libraries sharing it would
    be a surprise nobody asked for.

    Args:
        entry (dict): a ``DATABASES`` entry, modified in place.
        conn_max_age (int or None): the lifetime to set.
        session_options (Mapping): Postgres session parameters, possibly empty.
    """
    entry["CONN_MAX_AGE"] = conn_max_age
    _apply_session_options(entry, session_options)


def resolve_database(
    spec,
    game_dir,
    env,
    common_url_var=DEFAULT_COMMON_URL_VAR,
    default_conn_max_age=DEFAULT_CONN_MAX_AGE,
    default_session_options=DEFAULT_SESSION_OPTIONS,
):
    """Build the ``DATABASES`` entry for one spec.

    Three rungs, first match wins:

      1. ``DATABASE_URL_<ALIAS>`` — a database of this alias's own
      2. ``common_url_var`` — the database every alias shares
      3. a SQLite file under ``<game_dir>/server/``

    A variable set to an empty string counts as unset. An exported-but-empty
    variable is an ordinary deployment state, and treating it as set would
    hand the parser an empty string.

    Args:
        spec (AliasSpec): the alias to resolve.
        game_dir (str): the Evennia game directory.
        env (Mapping): environment variables to read. Nothing is taken from
            the real environment, so a caller can name one without touching
            it.
        common_url_var (str): the variable naming the shared database. An
            argument rather than a constant, because it is one value for a
            whole deployment rather than something each library declares.
        default_conn_max_age (int or None): the connection lifetime for
            this alias unless its spec declares one of its own. The consumer
            owns this value — a spec belongs to the library that wrote it, so
            without it a consumer would have no lever over an alias they do
            not own.
        default_session_options (Mapping): Postgres session parameters for
            this alias unless its spec declares its own. Postgres only.

    Returns:
        dict: a Django ``DATABASES`` entry.

    Raises:
        SharedDatabaseRefused: the alias landed on the common database and
            its spec does not allow that.
    """
    own_variable = alias_url_variable(spec.alias)

    # `or None` rather than a membership test: an exported-but-empty variable
    # is an ordinary deployment state and means the same as an absent one.
    own_url = env.get(own_variable) or None
    if own_url:
        entry = parse_url(own_url)
    else:
        common_url = env.get(common_url_var) or None
        if common_url:
            if not spec.allow_sharing_common_db:
                message = (
                    f"{common_url_var} is set and {spec.alias!r} may not "
                    f"share it. Its tables would not be a second set of its "
                    f"own — they are the ones already in that database. Give "
                    f"it a database of its own by setting {own_variable}, or "
                    f"leave both unset and it falls back to its own SQLite "
                    f"file."
                )
                from .log import cascade_log

                cascade_log(message, level="ERROR")
                raise SharedDatabaseRefused(message)
            entry = parse_url(common_url)
        else:
            entry = {
                "ENGINE": SQLITE_ENGINE,
                "NAME": os.path.join(
                    game_dir, SQLITE_SUBDIRECTORY, spec.sqlite_filename
                ),
            }

    # On every rung, engine included. The spec wins where it said anything at
    # all — and `None` is something, so the test is against the sentinel
    # rather than for truthiness.
    apply_connection_settings(
        entry,
        default_conn_max_age if spec.conn_max_age is UNSET else spec.conn_max_age,
        default_session_options
        if spec.session_options is UNSET
        else spec.session_options,
    )
    return entry


def _apply_session_options(entry, options):
    """Render session parameters into a Postgres entry's ``OPTIONS``.

    Appended rather than assigned: ``dj_database_url`` already puts a URL's
    query parameters there — ``?sslmode=require`` lands in ``OPTIONS`` — so
    replacing the dict would drop them without a word.

    Skipped on anything that is not Postgres. Unlike ``CONN_MAX_AGE``, this
    one genuinely needs the branch: ``OPTIONS`` on SQLite means something else
    entirely, and a libpq string handed to it breaks the connection outright.

    Args:
        entry (dict): the ``DATABASES`` entry, modified in place.
        options (Mapping): ``{parameter: value}``, possibly empty.
    """
    if not options or "postgresql" not in entry.get("ENGINE", ""):
        return

    rendered = " ".join(f"-c {name}={value}" for name, value in options.items())
    existing = str(entry.setdefault("OPTIONS", {}).get("options", "")).strip()
    entry["OPTIONS"]["options"] = f"{existing} {rendered}".strip()


def is_split(alias, env, common_url_var=DEFAULT_COMMON_URL_VAR):
    """Is this alias on a different database from ``default``?

    Two callers need this and must agree: ``configure()``, deciding which
    routers to activate, and the migrate helper, deciding which aliases need
    ``migrate --database <alias>``. When those two disagree the failure is
    silent — a router refuses an alias's tables while Django records its
    migrations as applied, leaving a database that looks migrated and holds
    nothing.

    The rule is the alias's own URL being set, **or no common URL existing at
    all**. The second half reads oddly and is the ordinary case: with nothing
    configured, every alias falls to a SQLite file of its own, all of them
    different from the game's. Absence declares a split as much as presence
    does.

    Takes the alias rather than the spec, because no field on a spec can
    change the answer: one refusing the shared rung reaches only rung 1 or
    rung 3, and both are split already.

    Args:
        alias (str): the alias.
        env (Mapping): environment variables to read.
        common_url_var (str): the variable naming the shared database.

    Returns:
        bool: True where the alias is on a database of its own.
    """
    if env.get(alias_url_variable(alias)) or None:
        return True
    return not (env.get(common_url_var) or None)


def split_aliases(specs, env, common_url_var=DEFAULT_COMMON_URL_VAR):
    """The aliases that are on a database of their own.

    A named function rather than a comprehension at each call site: its two
    callers run in different processes, and the point is that they cannot
    reach different answers.

    Args:
        specs (list): the specs to consider.
        env (Mapping): environment variables to read.
        common_url_var (str): the variable naming the shared database.

    Returns:
        list: the split aliases, in the order the specs were given.
    """
    return [
        spec.alias
        for spec in specs
        if is_split(spec.alias, env, common_url_var)
    ]
