# SPDX-License-Identifier: BSD-3-Clause
"""Every module-level constant the library declares.

One file holds them all, so anyone about to declare a constant checks here
first and finds the existing name rather than minting a second one for the
same value.

**This module is on the settings path, so it imports nothing from Django.**
See ``discovery.py`` for the full statement of that constraint. It also holds
no settings accessors, because the library reads no Django settings — nothing
can, at the point it runs. What a consumer configures arrives as arguments to
``configure()`` or as environment variables.
"""

import re
from importlib.metadata import packages_distributions, requires

# The prefix on the variable naming a database of one alias's own. The alias,
# upper-cased, completes it.
ALIAS_URL_PREFIX = "DATABASE_URL_"

# The default name of the variable naming the database every alias shares.
# A default rather than a fixed value: it is one value for a whole deployment,
# so a game using a different name passes it to configure() once.
DEFAULT_COMMON_URL_VAR = "DATABASE_URL"

# Every database file Evennia creates lands under <game_dir>/server/, so an
# alias falling back to SQLite joins them rather than inventing a location.
SQLITE_SUBDIRECTORY = "server"

SQLITE_ENGINE = "django.db.backends.sqlite3"

# "This spec said nothing; use the game-wide value."
#
# A sentinel rather than None, because None is a real Django value for
# CONN_MAX_AGE — keep the connection forever. If None meant both "inherit" and
# "persist unlimited", a spec asking for the second would silently get the
# first.
UNSET = object()

# How long a connection is kept before being closed, unless a spec or the
# consumer says otherwise. Zero closes it at the end of each unit of work,
# which is the safe end of the scale: an Evennia deployment dispatches its
# database work to short-lived Twisted worker threads, and a persistent
# connection there is never reconsidered and never handed back. FullCircleMUD
# reached its Postgres connection limit before setting this, and the game
# locked up because nothing new could connect.
DEFAULT_CONN_MAX_AGE = 0

# Postgres session parameters applied to every alias whose spec declares none
# of its own. Empty, because no session parameter is universal — the one
# FullCircleMUD needs, hnsw.iterative_scan, belongs to whichever library
# stores vectors. Never mutated: every entry is rendered into a fresh string.
DEFAULT_SESSION_OPTIONS = {}

# What a shell can export. An alias is upper-cased onto ALIAS_URL_PREFIX to
# name a variable, so an alias failing this is one nobody can deploy.
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The module a library ships to declare its alias, found under its app.
SPEC_MODULE_NAME = "db_spec"

# The name the spec is declared under inside that module.
SPEC_ATTRIBUTE = "SPEC"

# This library's own distribution name, as a dependent library would declare
# it. The boot check reads other distributions' requirements looking for it.
DISTRIBUTION_NAME = "evennia-database-cascade"

# The only setting this library reads. It names the variable holding the
# database every alias shares when it has none of its own — the value a
# consumer also passes to configure(). It exists as a setting because the
# value has to be known in two processes: configure() runs in the settings
# module, and the migrate helper runs later, in another process entirely,
# with no way to see what that call was given.
SETTING_COMMON_URL_VAR = "CASCADE_COMMON_URL_VAR"


def get_common_url_var():
    """Return ``CASCADE_COMMON_URL_VAR``, defaulting to ``DATABASE_URL``.

    Read through an accessor rather than directly, so a consumer who declared
    nothing — the ordinary case — gets the default instead of an
    ``AttributeError``.

    Returns:
        str: the variable naming the shared database.
    """
    from django.conf import settings

    return getattr(settings, SETTING_COMMON_URL_VAR, DEFAULT_COMMON_URL_VAR)


def get_installed_apps():
    """Return ``settings.INSTALLED_APPS``.

    Django's own, always defined, so no fallback. The accessor exists so
    every settings read in the library sits in this one file, and so callers
    outside a settings module do not each import ``django.conf``.

    Returns:
        list: the installed app names.
    """
    from django.conf import settings

    return settings.INSTALLED_APPS


def get_databases():
    """Return ``settings.DATABASES``.

    Django's own, always defined. Read back rather than remembered: the boot
    check wants what the settings module actually ended up with.

    Returns:
        dict: the configured databases.
    """
    from django.conf import settings

    return settings.DATABASES


def check_settings(installed_apps=None, databases=None):
    """Refuse to start where the cascade did not do what it was meant to.

    Runs from ``AppConfig.ready()``, the first point at which Django is up
    and ``settings.DATABASES`` can be read back. Two questions:

    **Did a library that depends on us forget to declare anything?** A
    distribution requiring this library and shipping no ``db_spec`` never
    gets an alias configured, so its models fall through to ``default`` and
    the game runs with its tables in the database they exist to stay out of.
    The message names the library, because whoever reads it is not whoever
    can fix it.

    **Did every declared alias reach ``DATABASES``?** What it catches is
    ``configure()`` being called before the consumer's ``INSTALLED_APPS``
    edits, or not called at all.

    Every problem in one raise, so a consumer gets the list rather than one
    restart per mistake.

    Args:
        installed_apps (Iterable[str]): defaults to
            ``settings.INSTALLED_APPS``. An argument so a test can name one
            without ``override_settings``, which reloads the app registry.
        databases (Mapping): defaults to ``settings.DATABASES``.

    Returns:
        None.

    Raises:
        ImproperlyConfigured: one or more of the above, all of them named.
    """
    from django.core.exceptions import ImproperlyConfigured

    from .discovery import discover_specs

    if installed_apps is None:
        installed_apps = get_installed_apps()
    if databases is None:
        databases = get_databases()

    problems = []

    for app in installed_apps:
        if _depends_on_us(app) and not _has_a_spec(app):
            problems.append(
                f"{app} depends on {DISTRIBUTION_NAME} and ships no "
                f"{SPEC_MODULE_NAME} module, so it never declared an alias. "
                f"Its tables will be created in the game database. This is "
                f"that library's own packaging fault — report it there."
            )

    specs = discover_specs(installed_apps)
    for spec in specs:
        if spec.alias not in databases:
            problems.append(
                f"{spec.app_label} declares the alias {spec.alias!r}, which "
                f"is not in DATABASES. Either configure() was not called, or "
                f"it ran above the INSTALLED_APPS entry for that app."
            )

    if problems:
        raise ImproperlyConfigured(" ".join(problems))


def _depends_on_us(app):
    """Does the distribution shipping this app require this library?

    Requirements carrying an ``extra ==`` marker are skipped: an optional
    dependency is not a promise to declare an alias.

    An app with no distribution behind it — a module in a consumer's gamedir
    — has nothing to read, and is not a dependent.
    """
    top_level = app.split(".")[0]
    for distribution in set(packages_distributions().get(top_level, [])):
        for requirement in requires(distribution) or []:
            if "extra ==" in requirement:
                continue
            if _requirement_name(requirement) == DISTRIBUTION_NAME:
                return True
    return False


def _requirement_name(requirement):
    """The distribution name at the front of a requirement string.

    ``evennia-database-cascade>=0.1`` and ``evennia_database_cascade`` both
    reduce to the same name, per PEP 503's normalisation.
    """
    name = requirement.split(";")[0].strip()
    for separator in ("[", "(", "<", ">", "=", "!", "~", " "):
        name = name.split(separator)[0]
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _has_a_spec(app):
    """Does this app ship a ``db_spec`` module?

    Asked with ``find_spec`` rather than by importing, because ``ready()``
    runs for every installed app and a failure here belongs to
    ``discover_specs``, which reports it properly.
    """
    from importlib.util import find_spec

    try:
        return find_spec(f"{app}.{SPEC_MODULE_NAME}") is not None
    except (ImportError, ValueError):
        return False
