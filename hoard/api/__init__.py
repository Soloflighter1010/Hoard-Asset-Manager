"""Domain routes assembled once after the HTTP server's shared services are ready.

Keep registrations in their domain module. ACTIONS is a compatibility view of
this table, never a second list to maintain. Private helper methods are attached
to the handler during this mechanical extraction to preserve the existing test
seams and avoid changing endpoint behavior alongside the routing change.
"""
from __future__ import annotations

from .routing import Registry

ROUTES = ()
_registry = Registry(())


def install(handler):
    """Assemble all domains and attach their private helpers to the HTTP boundary."""
    global ROUTES, _registry
    from . import downloads, imports, library, local, projects, sets, settings, stores, tasks
    domains = (library, downloads, local, projects, sets, settings, stores, tasks, imports)
    ROUTES = tuple(route for domain in domains for route in domain.ROUTES)
    _registry = Registry(ROUTES)
    for domain in domains:
        for name, implementation in domain.METHODS.items():
            setattr(handler, name, implementation)


def find(method: str, path: str):
    """Find a route without mixing security decisions into domain dispatch."""
    return _registry.find(method, path)
