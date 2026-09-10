# SPDX-License-Identifier: BSD-3-Clause
"""Reaching every alias with a migration, including the split ones.

A bare ``evennia migrate`` does not reach an alias on a database of its own:
its router refuses those tables everywhere but there, so the migration is
recorded as applied and no table is created. Every split alias therefore needs
``migrate --database <alias>``, and this is the thing that knows the list.

**Not on the settings path.** This runs from a management command, after
``django.setup()``, so it may import Django. It does not log — see ``log.py``
for why nothing in this library does.

It re-derives the split set through ``split_aliases`` rather than being handed
one, because ``configure()`` ran in a different process and nothing it
returned still exists. That both of them read the same function is the point:
a router and a migration disagreeing is the silent failure this library was
built to prevent.
"""

import os

from django.core.management import call_command

from .config import get_common_url_var, get_installed_apps
from .discovery import discover_specs
from .resolve import split_aliases


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
    split = split_aliases(specs, env, get_common_url_var())

    # Covers `default` and every alias sharing its database, because no router
    # stands between them.
    call_command("migrate", **options)
    for alias in split:
        call_command("migrate", database=alias, **options)

    return split
