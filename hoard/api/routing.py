"""The HTTP contract for one endpoint, independent of the server implementation.

Authentication and size limits live beside the handler so an endpoint cannot be
added to dispatch while accidentally missing the security policy. Request field
types describe accepted JSON; domain handlers retain their existing validation
and error messages. Binary/static responses state their media type explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

JSON_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object", "any"})


@dataclass(frozen=True)
class Route:
    """One exact path (or trailing-star asset prefix) and its public contract."""

    method: Literal["GET", "POST"]
    path: str
    handler: Callable
    changes: bool = False
    auth: Literal["key", "public", "entry", "instance"] = "key"
    image_key: bool = False
    max_body: int = 1024 * 1024
    request: tuple[tuple[str, str], ...] = ()
    response: str = "object"

    def __post_init__(self):
        """Reject an unsafe or ambiguous registration at startup, before serving requests."""
        if self.method not in {"GET", "POST"} or not self.path.startswith("/") or not callable(self.handler):
            raise ValueError("A route needs a method, absolute path and handler")
        if self.changes and (self.method != "POST" or self.auth != "key"):
            raise ValueError("A changing endpoint must use POST and the access key")
        if self.auth not in {"key", "public", "entry", "instance"} or self.max_body < 1:
            raise ValueError("Invalid route access policy")
        if self.auth == "public" and self.method != "GET":
            raise ValueError("Only static reads may be public")
        if self.image_key and (self.method != "GET" or self.auth != "key"):
            raise ValueError("Address keys are only for authenticated image/file reads")
        if len(dict(self.request)) != len(self.request) or any(t not in JSON_TYPES for _, t in self.request):
            raise ValueError("Invalid request description")
        if self.response not in JSON_TYPES and "/" not in self.response:
            raise ValueError("Response must be a JSON type or media type")


class Registry:
    """An immutable lookup, refusing duplicate endpoints and ambiguous prefixes."""

    def __init__(self, routes):
        self.routes = tuple(routes)
        self.exact, prefixes = {}, []
        for route in self.routes:
            key = (route.method, route.path)
            if key in self.exact:
                raise ValueError(f"Duplicate route: {key}")
            self.exact[key] = route
            if "*" in route.path:
                if route.method != "GET" or not route.path.endswith("/*") or route.path.count("*") != 1:
                    raise ValueError("Only static GET paths may have a trailing wildcard")
                prefixes.append(route)
        self.prefixes = tuple(sorted(prefixes, key=lambda route: -len(route.path)))

    def find(self, method: str, path: str) -> Route | None:
        """Prefer exact endpoints, then the longest registered asset prefix."""
        route = self.exact.get((method, path))
        if route is not None:
            return route
        return next((r for r in self.prefixes if r.method == method and path.startswith(r.path[:-1])), None)
