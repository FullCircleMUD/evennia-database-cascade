# SPDX-License-Identifier: BSD-3-Clause
"""Worker-thread dispatch that releases its database connections.

Django holds connections in thread-local storage: one per thread and alias,
opened lazily on first use. Nothing in a Twisted worker thread ever closes
them. The ``request_started``/``request_finished`` signals that drive
``close_old_connections()`` fire for the web request cycle only, so a thread
dispatched with ``deferToThread`` opens its connections and keeps them for the
life of the thread — and the reactor's pool holds its threads indefinitely.

The result is a fixed pool of idle connections per process, one for every alias
each pooled thread has ever touched, multiplied by the number of game
processes. Measured against a ``max_connections`` of 50: 47 idle, across four
databases, with shop commands and the web server both refused.

**This library's concern because this library multiplies the aliases.** The
count is per thread *per alias*, and giving a library an alias of its own is
what ``configure()`` is for. It is the ``CONN_MAX_AGE = 0`` decision from the
other side: that one is the connection a request holds, this is the connection
a worker thread holds.

**The close has to happen on the worker thread.** The call site, the callback
and the errback all run on the reactor, and closing there would walk the
reactor's own connections rather than the worker's. Wrapping the target
function is the only place a ``finally`` runs on the right side of the boundary.

``close_all()`` on a thread that opened nothing is a no-op, so this is used for
every dispatch rather than only the ones known to touch the ORM. A function
that does not query today is one edit away from doing so, and the call site is
not where that would be noticed.

**The imports are inside the function.** This module is re-exported from the
package root, which a consumer's ``settings.py`` opens while it is still
executing — so the module body stays a bare ``def`` and nothing Django is
imported until something calls it, long after ``django.setup()``.
"""


def defer_to_db_thread(fn, *args, **kwargs):
    """Run ``fn`` on a worker thread, closing its connections afterwards.

    A drop-in replacement for ``twisted.internet.threads.deferToThread`` —
    same argument forwarding, same Deferred, so callbacks and errbacks are
    unchanged.

    The connections close in a ``finally``, so the failure path releases them
    too. That is the path that matters: an exhausted pool makes every
    subsequent query raise, and a trailing close would leak a connection on
    each one.

    Args:
        fn (callable): the blocking work, run on a worker thread.
        *args: positional arguments for ``fn``.
        **kwargs: keyword arguments for ``fn``.

    Returns:
        Deferred: fires with ``fn``'s return value, or its failure.
    """
    from django.db import connections
    from twisted.internet import threads

    def run():
        try:
            return fn(*args, **kwargs)
        finally:
            connections.close_all()

    return threads.deferToThread(run)
