# SPDX-License-Identifier: BSD-3-Clause
"""Reaching every alias with a migration, including the split ones.

A bare ``evennia migrate`` does not reach an alias on a database of its own:
its router refuses those tables everywhere but there, so the migration is
recorded as applied and no table is created. Every split alias therefore needs
``migrate --database <alias>``, and this is the thing that knows the list.

**Not on the settings path.** This runs from a management command, after
``django.setup()``, so it may import Django.

It re-derives the split set through ``split_aliases`` rather than being handed
one, because ``configure()`` ran in a different process and nothing it
returned still exists. That both of them read the same function is the point:
a router and a migration disagreeing is the silent failure this library was
built to prevent.
"""

import os
from collections.abc import Mapping

from django.core.management import call_command

from .config import get_common_url_var, get_databases, get_installed_apps
from .discovery import discover_specs
from .resolve import split_aliases


def installed_extensions(alias):
    """The Postgres extensions already installed on one alias's database.

    Args:
        alias (str): the alias to ask.

    Returns:
        set or None: the extension names, or None where the alias is not
            Postgres and the question does not apply.
    """
    from django.db import connections

    if "postgresql" not in get_databases()[alias].get("ENGINE", ""):
        return None

    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension")
        return {row[0] for row in cursor.fetchall()}


def create_schema(alias, name):
    """Create one schema on one alias's database, if it is Postgres.

    Args:
        alias (str): the alias whose connection runs the statement.
        name (str): the schema to create.

    Returns:
        bool: True where the statement ran, False where the alias is not
            Postgres and has no schemas.
    """
    from django.db import connections

    if "postgresql" not in get_databases()[alias].get("ENGINE", ""):
        return False

    connection = connections[alias]
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE SCHEMA IF NOT EXISTS {connection.ops.quote_name(name)}"
        )
    return True


def _create_schemas(specs):
    """Create the schema each alias's ``search_path`` names, before migrating.

    Neither Django's migrate nor Postgres creates one, so an alias pointed at
    a missing schema has nowhere to put its first table. Unlike an extension
    this needs no superuser — the role owns its database — so it is done
    rather than reported.

    Args:
        specs (list): the discovered specs.

    Raises:
        ImproperlyConfigured: a schema could not be created.
    """
    from django.core.exceptions import ImproperlyConfigured

    for spec in specs:
        if not isinstance(spec.session_options, Mapping):
            continue
        name = spec.session_options.get("search_path")
        if not name:
            continue
        try:
            create_schema(spec.alias, name)
        except Exception as error:
            message = (
                f"{spec.alias!r} puts its tables in the schema {name!r}, "
                f"which could not be created: {error}"
            )
            from .log import cascade_log

            cascade_log(message, level="ERROR")
            raise ImproperlyConfigured(message) from error


def _refuse_missing_extensions(specs):
    """Refuse to migrate against a database missing an extension it needs.

    Only reports. Creating an extension needs superuser and an application
    role deliberately is not one, so the message carries the command for a
    human to run rather than pretending we can fix it.

    Checked across every spec, not only the split ones: an alias sharing the
    game's database needs its extension on that database just the same.

    Raised before any migration runs, because a migration creating a vector
    column against a database without the extension fails halfway rather than
    cleanly.

    Args:
        specs (list): the discovered specs.

    Raises:
        ImproperlyConfigured: one or more extensions are missing, all named.
    """
    from django.core.exceptions import ImproperlyConfigured

    problems = []
    for spec in specs:
        if not spec.required_extensions:
            continue
        present = installed_extensions(spec.alias)
        if present is None:
            continue
        for extension in spec.required_extensions:
            if extension in present:
                continue
            # The psql command wants the database name, not the alias. Fall
            # back to the alias where the entry is not there to read.
            database = get_databases().get(spec.alias, {}).get(
                "NAME", spec.alias
            )
            problems.append(
                f"{spec.alias!r} needs the {extension!r} extension and the "
                f"database behind it does not have one. Its migrations will "
                f"fail partway. Creating an extension needs superuser, so "
                f"run: sudo -u postgres psql -d {database} -c "
                f"'CREATE EXTENSION {extension}'"
            )

    if problems:
        message = " ".join(problems)
        from .log import cascade_log

        cascade_log(message, level="ERROR")
        raise ImproperlyConfigured(message)


def migrate_all(installed_apps=None, env=None, **options):
    """Migrate the game database, then every alias on one of its own.

    Options are forwarded to Django's ``migrate`` untouched, so a caller
    keeps ``verbosity``, ``interactive`` and the rest. ``database`` is the
    exception — the helper decides that per call, and supplying it would be
    fighting the thing the helper is for.

    Args:
        installed_apps (Iterable[str]): defaults to
            ``settings.INSTALLED_APPS``. An argument so a test can name one
            without ``override_settings``, which reloads the app registry.
        env (Mapping): defaults to ``os.environ``.
        **options: forwarded to ``migrate``.

    Returns:
        list: the aliases that were given their own call, in spec order.

    Raises:
        TypeError: ``database`` was passed.
        ImproperlyConfigured: an alias needs a Postgres extension its
            database does not have, or a schema its ``search_path`` names
            could not be created.
    """
    if "database" in options:
        raise TypeError(
            "migrate_all() decides which databases to migrate, so it does "
            "not take a 'database' option. Call Django's migrate directly if "
            "you want one alias on its own."
        )

    if installed_apps is None:
        installed_apps = get_installed_apps()
    if env is None:
        env = os.environ

    specs = discover_specs(installed_apps)
    _refuse_missing_extensions(specs)
    _create_schemas(specs)
    split = split_aliases(specs, env, get_common_url_var())

    # Covers `default` and every alias sharing its database, because no router
    # stands between them.
    call_command("migrate", **options)
    for alias in split:
        call_command("migrate", database=alias, **options)

    from .log import cascade_log

    own = ", ".join(split) or "none"
    cascade_log(f"migrated: the game database, then on their own: {own}")

    return split
