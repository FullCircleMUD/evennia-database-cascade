# SPDX-License-Identifier: BSD-3-Clause
"""Logging shim for evennia-database-cascade. **Nothing calls it.**

An agreed exception to the logging standard, and the file is kept only so the
library lints as one of the corpus rather than looking like it forgot.

**Why nothing calls it.** Evennia's ``logger.log_file`` writes through
``deferToThread``, which needs a running Twisted reactor. Every piece of this
library does its work before one exists — ``configure()`` runs while the
consumer's settings module is still executing, the boot check runs during
``django.setup()``, and the migrate helper runs as a management command in a
process that starts no reactor at all. Calling this from any of them opens the
file and writes nothing, which was measured rather than assumed: a 0-byte
``cascade.log`` beside a demo gamedir that had just refused a migration.

A mechanism of our own was considered and judged unnecessary. Every failure
here is fatal — the server does not start, or the command dies — so the
exception and its traceback are already in front of whoever needs them, and a
log file is for reading later about a process that kept running.

The one part of this library that does run with a reactor up is
``CascadeRouter``, and it has nothing to report: it compares an app label and
returns an alias.

What follows is the standard shim, verbatim, so that if a reason to log ever
does appear it is already the same shape as every sibling's.
"""

import traceback

_LOG_FILENAME = "cascade.log"
_VALID_LEVELS = ("INFO", "WARN", "ERROR")


def cascade_log(message: str, level: str = "INFO", trace: bool = False) -> None:
    """Emit one line to ``cascade.log``.

    ``level`` is coerced to ``INFO`` if not one of ``INFO``/``WARN``/
    ``ERROR``. A log call must never raise into the caller, so an unknown
    level degrades rather than rejecting.

    ``trace`` appends the active exception's traceback — call it from inside
    an ``except`` block, where ``format_exc()`` has something to report.
    Outside one it is a no-op, not an error.
    """
    try:
        from evennia.utils import logger
    except ImportError:
        return
    if logger is None:  # pragma: no cover - defensive
        return

    if level not in _VALID_LEVELS:
        level = "INFO"

    if trace:
        formatted = traceback.format_exc()
        # format_exc() returns "NoneType: None\n" when no exception is being
        # handled. Appending that would be noise.
        if formatted and not formatted.startswith("NoneType: None"):
            message = f"{message}\n{formatted.rstrip()}"

    logger.log_file(f"[{level}] {message}", filename=_LOG_FILENAME)
