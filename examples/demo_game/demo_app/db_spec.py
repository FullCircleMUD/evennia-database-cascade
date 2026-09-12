"""What this game declares about the database it owns."""

from evennia_database_cascade import AliasSpec

SPEC = AliasSpec(
    app_labels="demo_app",
    alias="demogame",
)
