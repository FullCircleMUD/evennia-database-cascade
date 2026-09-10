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
# evennia-database-cascade
#
# Two consumers, deliberately:
#   demo_library  an installed distribution declaring us as a dependency
#   demo_app      this gamedir's own app, which is not a distribution
######################################################################

import os

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
