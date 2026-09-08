# SPDX-License-Identifier: BSD-3-Clause
"""Test runner for evennia-database-cascade.

Runs the library's unit tests against tests/test_settings.py — no gamedir
required. Invoke from the library root:

    python runtests.py
"""
import os
import sys

import django

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")
    django.setup()

    # Evennia uses lazy ``evennia.Command``/``CmdSet`` exports that are
    # populated by ``evennia._init()``. Real-runtime entry points (server.py,
    # portal.py, evennia_launcher) call this AFTER ``django.setup()`` has
    # already triggered our app's ``ready()``. The test runner calls it
    # explicitly here so the deferred work has somewhere to run.
    import evennia
    evennia._init()

    from django.conf import settings
    from django.test.utils import get_runner

    runner = get_runner(settings)()
    failures = runner.run_tests(["evennia_database_cascade"])
    sys.exit(bool(failures))
