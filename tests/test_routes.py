"""The route table is the single security and dispatch contract for every endpoint."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from tests.isolation import IsolatedTestCase
from hoard import server
from hoard.api import ROUTES, find
from hoard.api.routing import Registry, Route


class Routes(IsolatedTestCase):
    def test_reference_matches_the_registered_contracts(self):
        from scripts.build_api_docs import ROOT, generated
        self.assertEqual((ROOT / "docs/API.md").read_text("utf-8"), generated())

    def test_every_change_is_a_post_with_the_key(self):
        for route in ROUTES:
            with self.subTest(path=route.path):
                if route.changes:
                    self.assertEqual((route.method, route.auth), ("POST", "key"))
                if route.path.startswith("/api/"):
                    self.assertNotEqual(route.auth, "public")
                self.assertIs(find(route.method, route.path.replace("*", "sample")), route)
        self.assertEqual(set(server.ACTIONS), {r.path for r in ROUTES if r.method == "POST"})
        self.assertEqual(set(server.KEYLESS_ACTIONS), {"/api/enter", "/api/show"})

    def test_unsafe_and_duplicate_registrations_fail_at_startup(self):
        handler = lambda *args: None
        for kwargs in ({"changes": True}, {"changes": True, "auth": "public"}):
            with self.assertRaises(ValueError):
                Route("GET", "/api/unsafe", handler, **kwargs)
        route = Route("POST", "/api/example", handler, changes=True)
        with self.assertRaises(ValueError):
            Registry([route, route])
        self.assertIsNone(Registry([route]).find("GET", route.path))

    def test_request_fields_used_by_handlers_are_described(self):
        for route in ROUTES:
            if route.method != "POST":
                continue
            described = dict(route.request)
            source = ast.parse(inspect.getsource(route.handler))
            for node in ast.walk(source):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "body"
                        and node.func.attr == "get" and node.args and isinstance(node.args[0], ast.Constant)):
                    self.assertIn(node.args[0].value, described, route.path)

    def test_http_boundary_has_no_endpoint_dispatch_branches(self):
        tree = ast.parse(Path(server.__file__).read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name):
                self.assertNotEqual(node.left.id, "path", f"server.py:{node.lineno}")
