import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge import Engine, ForgeError, Handler, ThreadingHTTPServer, validate


class FakeGitHub:
    def __init__(self, changed=False, merged=True, owner="alice"):
        self.calls = []
        self.changed, self.merged, self.owner = changed, merged, owner

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/user":
            return {"login": "alice"}
        if path == "/repos/alice/lab":
            return {"owner": {"login": self.owner}, "default_branch": "main", "permissions": {"push": True}}
        if "/git/ref/" in path:
            return {"object": {"sha": "base"}}
        if method == "POST" and path.endswith("/issues"):
            return {"number": 1, "html_url": "https://github.com/alice/lab/issues/1"}
        if method == "PUT" and "/contents/" in path:
            return {"commit": {"sha": "head", "html_url": "https://github.com/alice/lab/commit/head"}}
        if path.endswith("/pulls"):
            return {"number": 2, "html_url": "https://github.com/alice/lab/pull/2"}
        if method == "GET" and path.endswith("/pulls/2"):
            return {"head": {"sha": "changed" if self.changed else "head"}}
        if path.endswith("/merge"):
            return {"merged": self.merged}
        return {}


class EngineTests(unittest.TestCase):
    def make_run(self, github, mode="yolo", **options):
        engine = Engine(github)
        plan = engine.plan({"repository": "alice/lab", "mode": mode, **options})
        run = {"id": plan["id"], "events": [], "completed": 0, "cancel": False}
        engine.execute(plan, run)
        return engine, plan, run

    def test_changed_head_cannot_merge(self):
        github = FakeGitHub(changed=True)
        _, _, run = self.make_run(github)
        self.assertEqual(run["status"], "failed")
        self.assertFalse(any(path.endswith("/merge") for _, path, _ in github.calls))

    def test_unaccepted_merge_is_failure(self):
        _, _, run = self.make_run(FakeGitHub(merged=False))
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["completed"], 0)

    def test_merge_is_pinned_to_sha_and_preserves_commits(self):
        github = FakeGitHub()
        _, _, run = self.make_run(github)
        self.assertEqual(run["status"], "completed")
        merge = next(payload for _, path, payload in github.calls if path.endswith("/merge"))
        self.assertEqual(merge, {"sha": "head", "merge_method": "merge"})

    def test_issue_lifecycle(self):
        github = FakeGitHub()
        _, _, run = self.make_run(github, "quickdraw")
        self.assertEqual(run["status"], "completed")
        self.assertTrue(any(method == "PATCH" and payload["state"] == "closed" for method, _, payload in github.calls))

    def test_coauthor_trailer(self):
        github = FakeGitHub()
        _, _, run = self.make_run(github, "pair-extraordinaire", coauthor_name="Bob", coauthor_email="bob@example.com", coauthor_confirmed=True)
        commit = next(payload for _, path, payload in github.calls if "/contents/" in path)
        self.assertIn("\n\nCo-authored-by: Bob <bob@example.com>", commit["message"])
        self.assertEqual(run["status"], "completed")

    def test_foreign_repository_is_rejected(self):
        with self.assertRaises(ForgeError):
            Engine(FakeGitHub(owner="someone-else")).plan({"repository": "alice/lab", "mode": "yolo"})

    def test_input_limits_and_injection(self):
        for options in ({"count": True}, {"count": 9}, {"repository": "alice/lab/../../bad"}, {"mode": "unknown"}):
            with self.subTest(options=options), self.assertRaises(ForgeError):
                validate({"repository": "alice/lab", "mode": "yolo", **options})
        with self.assertRaises(ForgeError):
            validate({"repository": "alice/lab", "mode": "pair-extraordinaire", "coauthor_name": "Bob\nInjected", "coauthor_email": "bob@example.com", "coauthor_confirmed": True})

    def test_demo_never_uses_network_and_plans_are_single_use(self):
        engine = Engine()
        plan = engine.plan({"repository": "alice/lab", "mode": "quickdraw"})
        with self.assertRaises(ForgeError):
            engine.start(plan["id"], "wrong/lab")
        result = engine.start(plan["id"], "alice/lab")
        self.assertTrue(result["demo"])
        with self.assertRaises(ForgeError):
            engine.start(plan["id"], "alice/lab")

    def test_cancel_before_mutation(self):
        github = FakeGitHub()
        engine = Engine(github)
        plan = engine.plan({"repository": "alice/lab", "mode": "quickdraw"})
        run = {"id": "cancelled", "cancel": True, "events": [], "completed": 0}
        engine.execute(plan, run)
        self.assertEqual(run["status"], "cancelled")
        self.assertFalse(any(method != "GET" for method, _, _ in github.calls))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.engine = Engine()
        cls.server.csrf = "test-csrf"
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_static_and_demo_status(self):
        with urlopen(self.origin) as response:
            self.assertIn(b"Achievement Forge", response.read())
        with urlopen(self.origin + "/api/status") as response:
            self.assertTrue(json.load(response)["demo"])

    def test_cross_origin_rejected_even_with_csrf(self):
        request = Request(self.origin + "/api/plan", method="POST", data=b"{}", headers={"Origin": "https://attacker.example", "X-Forge-CSRF": "test-csrf"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_plan_route(self):
        payload = json.dumps({"repository": "alice/lab", "mode": "quickdraw"}).encode()
        request = Request(self.origin + "/api/plan", method="POST", data=payload, headers={"Origin": self.origin, "X-Forge-CSRF": "test-csrf"})
        with urlopen(request) as response:
            self.assertEqual(json.load(response)["steps"], ["Create an issue", "Close the issue immediately"])


if __name__ == "__main__":
    unittest.main()
