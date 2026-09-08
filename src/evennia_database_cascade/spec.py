# SPDX-License-Identifier: BSD-3-Clause
"""What a library declares about the database alias it owns.

A consumer library ships a ``db_spec`` module holding one of these. It is the
whole of what the library says about itself: the rest — which database the
alias lands on, whether a router is needed, whether an extra migrate call is —
is decided by the deployment and worked out by ``configure()``.

**This module is on the settings path, so it imports nothing from Django.**
A consumer's ``db_spec`` imports ``AliasSpec`` from here while their
``settings.py`` is still executing, before ``django.setup()``. See
``discovery.py`` for the full statement of that constraint.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AliasSpec:
    """One library's declaration of the alias it owns.

    Args:
        app_label (str): the Django app label the router matches models on —
            ``model._meta.app_label``. Required.
        alias (str): the ``DATABASES`` key the alias is known by, what the
            router returns from ``db_for_read``/``db_for_write``, and what
            ``migrate --database <alias>`` takes. The environment variable
            naming a database of its own derives from it:
            ``DATABASE_URL_<ALIAS>``, upper-cased. Required.
        sqlite_filename (str): the file this alias falls back to when no URL
            names a database for it. Defaults to ``<alias>.db3``.
        allow_sharing_common_db (bool): may this alias live in the database
            the common URL names? ``False`` for a library whose tables share
            names with the framework's — pointing its alias at the game's
            database would hand it the live tables rather than a second set of
            its own. Defaults to ``True``.
        allow_foreign_tables_in_own_db (bool): may another app's tables be
            migrated into this alias's database? ``True`` only where that is
            the point, as it is for a schema clone. Defaults to ``False``.

    The two ``allow_`` fields are the inbound and outbound halves of the same
    question — whether this alias may go into someone else's database, and
    whether someone else's tables may come into this one. They are
    independent: a library can want either, both, or neither.

    Frozen because a spec is a declaration rather than state. Nothing should
    alter one after the declaring library wrote it, and ``discover_specs``
    hands back the object it found rather than a copy.
    """

    app_label: str
    alias: str
    sqlite_filename: str = ""
    allow_sharing_common_db: bool = True
    allow_foreign_tables_in_own_db: bool = False

    def __post_init__(self):
        # Derived rather than defaulted in the signature, because the default
        # depends on another field. `object.__setattr__` is how a frozen
        # dataclass fills in a computed value — a plain assignment would hit
        # the freeze this class exists to have.
        if not self.sqlite_filename:
            object.__setattr__(self, "sqlite_filename", f"{self.alias}.db3")
