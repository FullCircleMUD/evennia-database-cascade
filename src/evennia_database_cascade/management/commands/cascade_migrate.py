# SPDX-License-Identifier: BSD-3-Clause
"""``evennia cascade_migrate`` — migrate every database, split ones included.

A thin wrapper. Everything it knows is in ``migrate_all``, so the command and
a consumer's own deploy script calling that function cannot drift apart.
"""

from django.core.management.base import BaseCommand

from evennia_database_cascade.migrate import migrate_all


class Command(BaseCommand):
    """Run the migrations a bare ``migrate`` cannot reach."""

    help = (
        "Migrate the game database, then every alias on a database of its "
        "own. A split alias is not reached by a bare migrate."
    )

    def handle(self, *args, **options):
        migrated = migrate_all(**options)
        if migrated:
            self.stdout.write(
                "Migrated aliases on their own database: "
                + ", ".join(migrated)
            )
        else:
            self.stdout.write("No alias is on a database of its own.")
