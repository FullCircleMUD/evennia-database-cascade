# SPDX-License-Identifier: BSD-3-Clause
"""The Django app, and the one thing it does at boot.

Unlike most of this library, this module is **not** on the settings path —
Django imports it during ``setup()``, well after the consumer's settings module
has finished. So it may import Django, and ``ready()`` is the first point at
which anything here can read ``settings.DATABASES`` back.
"""

from django.apps import AppConfig


class CascadeConfig(AppConfig):
    """Runs the boot check.

    A consumer who leaves this out of ``INSTALLED_APPS`` still gets their
    aliases resolved — ``configure()`` does that from their settings module —
    but nothing checks the result. That gap is documented rather than
    defended against: a library that is not installed cannot notice that it
    is not installed.
    """

    name = "evennia_database_cascade"
    verbose_name = "Database cascade"

    def ready(self):
        from .config import check_settings

        check_settings()
