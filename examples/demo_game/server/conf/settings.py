r"""
Evennia settings file.

The available options are found in the default settings file found
here:

https://www.evennia.com/docs/latest/Setup/Settings-Default.html

Remember:

Don't copy more from the default file than you actually intend to
change; this will make sure that you don't overload upstream updates
unnecessarily.

When changing a setting requiring a file system path (like
path/to/actual/file.py), use GAME_DIR and EVENNIA_DIR to reference
your game folder and the Evennia library folders respectively. Python
paths (path.to.module) should be given relative to the game's root
folder (typeclasses.foo) whereas paths within the Evennia library
needs to be given explicitly (evennia.foo).

If you want to share your game dir, including its settings, you can
put secret game- or server-specific settings in secret_settings.py.

"""

# Use the defaults from Evennia unless explicitly overridden
from evennia.settings_default import *

######################################################################
# Evennia base server config
######################################################################

# This is the name of your game. Make it catchy!
SERVERNAME = "demo_game"


######################################################################
# macOS only: use a bundled, non-Apple SQLite build
#
# macOS ships /usr/lib/libsqlite3.dylib, which drives sqlite3_initialize()
# through libdispatch. libdispatch does not survive fork(), so once any
# SQLite connection has been opened, a daemonizing (forking) start deadlocks
# on the child's first SQLite call — silently, with no error or timeout.
# `evennia start` forks on Unix; `--nodaemon` and Windows do not, which is
# why this only bites daemonized starts on macOS.
#
# This has to run before anything opens a database, so it sits above the
# cascade block below. Copied verbatim from the sibling demo gamedirs in
# evennia-scaling, evennia-shards and evennia-portal-multiplex — a difference
# between two copies would be a defect rather than a variation.
######################################################################

import sys

if sys.platform == "darwin":
    try:
        import sqlean
        import sqlean.dbapi2

        class _CascadeConnection(sqlean.dbapi2.Connection):
            def getlimit(self, category):
                # Django uses this only to size bulk_create batches.
                return 999

        _sqlean_connect = sqlean.dbapi2.connect

        def _connect(*args, **kwargs):
            kwargs.setdefault("factory", _CascadeConnection)
            return _sqlean_connect(*args, **kwargs)

        sqlean.dbapi2.connect = _connect
        sqlean.connect = _connect
        sqlean.SQLITE_LIMIT_VARIABLE_NUMBER = 9
        sqlean.dbapi2.SQLITE_LIMIT_VARIABLE_NUMBER = 9

        sys.modules["sqlite3"] = sqlean
        sys.modules["sqlite3.dbapi2"] = sqlean.dbapi2
    except ImportError:
        pass


import os

######################################################################
# Which rung to test — uncomment a block below
#
# The cascade reads the environment, so these are ordinary environment
# variables. Setting them here rather than in a shell is only for
# convenience: it keeps all three states in one file where they can be read
# side by side, and means a test is a comment change and a restart rather
# than something remembered between terminals.
#
# A real deployment sets these in its environment and touches none of this.
#
# After changing which block is live, the databases behind it may not exist
# yet, so:  evennia cascade_migrate
#
# ---------------------------------------------------------------------
# STATE 1 — nothing set (leave everything below commented out)
#
#   Every alias falls to a SQLite file of its own under server/:
#   evennia.db3, demolib.db3, demogame.db3. Every alias is split, so both
#   routers are active and each needs its own migrate.
#
#   This is local development, and the state the gamedir ships in.
#
# ---------------------------------------------------------------------
# STATE 2 — a common database only
#
#   Uncomment the one line below. The common URL names the GAME'S database,
#   so `default` moves there too — the game and both aliases end up in
#   shared.db3, DATABASE_ROUTERS comes back EMPTY, and one bare migrate
#   creates every table in the one file. evennia.db3 is never created.
#
#   The name differing from evennia.db3 is deliberate: it is what proves
#   `default` followed the URL rather than staying put. On Postgres the
#   database is created beforehand and the URL simply names it, whatever it
#   is called.
#
#   The empty router list is the other half. A router left active on a
#   shared database refuses the tables while Django records the migrations
#   as applied — a database that looks migrated and holds nothing.
#
#   os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(GAME_DIR, 'server', 'shared.db3')}"
#
# ---------------------------------------------------------------------
# STATE 3 — a common database, with one alias split off it
#
#   Uncomment BOTH lines below. demolib gets a database of its own while
#   demogame stays on the shared one, so exactly one router is active and
#   exactly one alias needs `migrate --database demolib`.
#
#   This is the shape a real deployment reaches for when one library's data
#   outgrows the rest, and the one the whole library exists to make routine.
#
# os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(GAME_DIR, 'server', 'shared.db3')}"
# os.environ["DATABASE_URL_DEMOLIB"] = f"sqlite:///{os.path.join(GAME_DIR, 'server', 'demolib_own.db3')}"
#
# ---------------------------------------------------------------------
#
# To see what a change produced, without starting the server:
#
#   evennia cascade_migrate     # reports which aliases are on their own
#
######################################################################

######################################################################
# evennia-database-cascade
#
# Two consumers, deliberately:
#   demo_library  an installed distribution declaring us as a dependency
#   demo_app      this gamedir's own app, which is not a distribution
######################################################################

from evennia_database_cascade import configure

INSTALLED_APPS += ["evennia_database_cascade", "demo_library", "demo_app"]

# After the INSTALLED_APPS edits above, and before anything reads DATABASES.
DATABASES, DATABASE_ROUTERS = configure(
    DATABASES, INSTALLED_APPS, GAME_DIR, os.environ
)


######################################################################
# Settings given in secret_settings.py override those in this file.
######################################################################
try:
    from server.conf.secret_settings import *
except ImportError:
    print("secret_settings.py file not found or failed to import.")
