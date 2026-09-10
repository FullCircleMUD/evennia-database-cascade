"""The gamedir's own app, owning one alias.

The second consumer shape: a game that owns tables, declaring a spec exactly
as a library does. Unlike demo_library it is not a distribution, so the boot
check's Requires-Dist path cannot see it — which is the documented gap.
"""
