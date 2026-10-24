# SPDX-License-Identifier: BSD-3-Clause
"""evennia-database-cascade — resolve database aliases from the environment.

The consumer-facing surface is re-exported here, so a game writes
``from evennia_database_cascade import AliasSpec`` rather than naming a
submodule.

**No module body reached from here may import Django.** This file is the first
one a consumer's ``settings.py`` opens, while that settings module is still
executing — see ``discovery.py`` for the full statement of that constraint.

Running database work off the reactor is ``evennia-db-threads``'
``defer_to_db_thread``, not this library's.

See docs/progress.md for what exists, and docs/test-plan.md for what the
library commits to covering.
"""

from .configure import configure
from .discovery import spec_is_valid
from .spec import AliasSpec

__all__ = ["AliasSpec", "configure", "spec_is_valid"]

__version__ = "0.0.1"
