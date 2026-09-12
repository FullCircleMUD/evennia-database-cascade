"""The Django app.

A second app label in the one distribution, so the demo exercises a spec
declaring more than one. Its tables belong in ``demolib`` alongside
``demo_library``'s — one library, one database, two app labels.
"""

from django.apps import AppConfig


class DemoLibraryExtraConfig(AppConfig):
    name = "demo_library.extra"
    label = "demo_library_extra"
    default_auto_field = "django.db.models.AutoField"
