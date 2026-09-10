"""What this library declares about the database it owns.

Imports nothing from Django: the consumer's settings module opens this file
while it is still executing, before django.setup().
"""

from evennia_database_cascade import AliasSpec

SPEC = AliasSpec(
    app_label="demo_library",
    alias="demolib",
)
