# SPDX-License-Identifier: BSD-3-Clause
"""One database router, built from one spec.

Django ships no router implementation — ``DATABASE_ROUTERS`` holds objects a
project writes, and the framework only calls four methods on them. The five
routers that exist across FullCircleMUD are the same twenty-five lines with
three values changed: which app label is mine, which alias it goes to, and
whether another app's tables may be created in my database. All three are
already on a spec, so this is one instance per spec rather than one subclass
per library.

**This module imports nothing from Django**, which is what lets ``configure()``
build instances and put them straight in ``DATABASE_ROUTERS`` rather than
dealing in dotted paths. Django accepts either. See ``discovery.py`` for the
full statement of the settings-path constraint.

**Routing queries and permitting migrations are separate jobs.** For
``evennia-archive`` this router lets Evennia's own forty-two tables be created
in the archive, and still sends every ``ObjectDB`` query to ``default`` —
routing them to the archive would have the game reading its players out of the
wrong database. Reaching an archived copy is explicit, with
``.using("archive")``, and that is the archive library's code rather than this.
"""


class CascadeRouter:
    """Routes its apps' models to one alias.

    Args:
        spec (AliasSpec): the alias this router serves. Three of its fields
            are read — ``app_labels``, ``alias``, and
            ``allow_foreign_tables_in_own_db``.
    """

    def __init__(self, spec):
        self.spec = spec

    def _is_ours(self, model):
        """Is this a model of one of the apps we own?"""
        return model._meta.app_label in self.spec.app_labels

    def db_for_read(self, model, **hints):
        """The alias for one of our models, and ``None`` for anyone else's.

        Returning a value for a foreign model would silently capture its
        queries: Django consults routers in order and takes the first
        non-``None`` answer, so a consumer running two of our libraries has
        two of these in the list and each must leave the other's models alone.
        """
        return self.spec.alias if self._is_ours(model) else None

    def db_for_write(self, model, **hints):
        """The alias for one of our models, and ``None`` for anyone else's."""
        return self.spec.alias if self._is_ours(model) else None

    def allow_relation(self, obj1, obj2, **hints):
        """``True`` where both models are ours, and no opinion otherwise."""
        if self._is_ours(obj1) and self._is_ours(obj2):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Where our apps' tables may be created, and who may join ours.

        Our own apps belong on our own alias and nowhere else — without the
        refusal a bare ``evennia migrate`` creates our tables in the game
        database too, and the separation exists only on paper.

        For a foreign app against our alias the answer is the spec's
        ``allow_foreign_tables_in_own_db``: ``False`` refuses it, and ``True``
        returns ``None`` so the decision passes to the other routers. Deferring
        rather than approving is what lets this coexist with a consumer's own
        routers instead of overruling them.
        """
        if app_label in self.spec.app_labels:
            return db == self.spec.alias
        if db == self.spec.alias and not self.spec.allow_foreign_tables_in_own_db:
            return False
        return None
