"""Achievement Forge — local workflow orchestration by brunnodev."""

import base64
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
MODES = {
    "quickdraw": ["Create an issue", "Close the issue immediately"],
    "yolo": ["Create branch and journal entry", "Open a pull request", "Merge without requesting review"],
    "pull-shark": ["Create branch and journal entry", "Open a pull request", "Merge the pull request"],
    "pair-extraordinaire": ["Create a commit with a co-author trailer", "Open a pull request", "Merge preserving the co-authored commit"],
}


class ForgeError(Exception):
    pass


class GitHub:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, payload=None):
        request = Request(
            "https://api.github.com" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "achievement-forge",
                     "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as error:
            try:
                message = json.loads(error.read()).get("message", "GitHub request failed")
            except (ValueError, UnicodeError):
                message = "GitHub request failed"
            raise ForgeError(f"GitHub {error.code}: {message}. Check token permissions, repository rules and rate limits.") from None
        except (URLError, TimeoutError):
            raise ForgeError("GitHub connection failed. Check the network and inspect existing artifacts before retrying.") from None


def validate(data):
    repo = data.get("repository", "")
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo):
        raise ForgeError("Use a repository in owner/name format.")
    mode = data.get("mode")
    if mode not in MODES:
        raise ForgeError("Choose a supported workflow.")
    count = data.get("count", 1)
    if type(count) is not int or not 1 <= count <= 8:
        raise ForgeError("Choose between 1 and 8 iterations.")
    if mode in ("quickdraw", "yolo") and count != 1:
        raise ForgeError("Quickdraw and YOLO run once per plan.")
    name, email = data.get("coauthor_name", ""), data.get("coauthor_email", "")
    if mode == "pair-extraordinaire":
        if not isinstance(name, str) or not re.fullmatch(r"[^<>\r\n]{1,80}", name):
            raise ForgeError("Enter the real co-author's name without line breaks or angle brackets.")
        if not isinstance(email, str) or not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", email):
            raise ForgeError("Enter the co-author's GitHub-associated email.")
        if data.get("coauthor_confirmed") is not True:
            raise ForgeError("Confirm the co-author participated and agreed to attribution.")
    return {"repository": repo, "mode": mode, "count": count,
            "coauthor_name": name if mode == "pair-extraordinaire" else "",
            "coauthor_email": email if mode == "pair-extraordinaire" else ""}


class Engine:
    def __init__(self, github=None, audit=None):
        self.github = github
        self.audit = audit
        self.plans = {}
        self.runs = {}
        self.lock = threading.RLock()

    def inspect(self, repo):
        if not self.github:
            return {"default_branch": "main", "permissions": {"push": True}}
        user = self.github.call("GET", "/user")
        info = self.github.call("GET", f"/repos/{repo}")
        if info["owner"]["login"].lower() != user["login"].lower():
            raise ForgeError("Select a repository owned by the authenticated account.")
        if info.get("archived") or info.get("disabled") or not info.get("permissions", {}).get("push"):
            raise ForgeError("Repository must be active and writable.")
        self.github.call("GET", f'/repos/{repo}/git/ref/heads/{quote(info["default_branch"], safe="")}')
        if not info.get("has_issues", True):
            raise ForgeError("Enable issues in the sandbox repository.")
        return info

    def plan(self, data):
        config = validate(data)
        info = self.inspect(config["repository"])
        plan_id = secrets.token_hex(12)
        plan = {**config, "id": plan_id, "base": info["default_branch"],
                "demo": self.github is None, "steps": MODES[config["mode"]],
                "created": time.time(), "used": False}
        with self.lock:
            self.plans = {key: value for key, value in self.plans.items() if time.time() - value["created"] < 900}
            self.plans[plan_id] = plan
        return plan.copy()

    def start(self, plan_id, confirmation):
        with self.lock:
            plan = self.plans.get(plan_id)
            if not plan or plan["used"] or time.time() - plan["created"] > 900:
                raise ForgeError("Plan is missing, expired or already executed. Generate a new preview.")
            if confirmation != plan["repository"]:
                raise ForgeError("Type the exact repository name to execute.")
            if any(run["status"] == "running" for run in self.runs.values()):
                raise ForgeError("Another execution is still running.")
            run = {"id": plan_id, "status": "running", "repository": plan["repository"],
                   "mode": plan["mode"], "demo": plan["demo"], "events": [], "completed": 0,
                   "total": plan["count"], "cancel": False}
            self.runs[plan_id] = run
            plan["used"] = True
        threading.Thread(target=self.execute, args=(plan, run), daemon=True).start()
        return self.snapshot(plan_id)

    def snapshot(self, run_id):
        with self.lock:
            if run_id not in self.runs:
                raise ForgeError("Execution not found.")
            return json.loads(json.dumps(self.runs[run_id]))

    def emit(self, run, message, url=None):
        event = {"time": datetime.now(timezone.utc).isoformat(), "message": message, "url": url}
        with self.lock:
            run["events"].append(event)
            if self.audit:
                self.audit.parent.mkdir(parents=True, exist_ok=True)
                with self.audit.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"run": run["id"], **event}) + "\n")

    def checkpoint(self, run):
        if run["cancel"]:
            raise ForgeError("Stopped. Already-created artifacts remain linked in this log.")

    def execute(self, plan, run):
        try:
            if not plan["demo"]:
                self.inspect(plan["repository"])
            for iteration in range(plan["count"]):
                self.checkpoint(run)
                if plan["demo"]:
                    for step in plan["steps"]:
                        self.checkpoint(run)
                        self.emit(run, "[DEMO] " + step)
                        time.sleep(0.25)
                elif plan["mode"] == "quickdraw":
                    self.quickdraw(plan, run)
                else:
                    self.pull_request(plan, run, iteration)
                with self.lock:
                    run["completed"] += 1
                if not plan["demo"] and iteration + 1 < plan["count"]:
                    time.sleep(2)
            self.emit(run, "Workflow completed. Badge issuance is evaluated by GitHub; check your profile separately.")
            run["status"] = "completed"
        except ForgeError as error:
            self.emit(run, str(error))
            run["status"] = "cancelled" if run["cancel"] else "failed"
        except Exception:
            self.emit(run, "Unexpected failure. Inspect artifacts before making a new plan.")
            run["status"] = "failed"

    def quickdraw(self, plan, run):
        path = f'/repos/{plan["repository"]}/issues'
        issue = self.github.call("POST", path, {"title": "Achievement Forge · issue lifecycle exercise",
            "body": "Sandbox issue created by Achievement Forge for an issue lifecycle exercise."})
        self.emit(run, f'Issue #{issue["number"]} created', issue["html_url"])
        self.checkpoint(run)
        self.github.call("PATCH", f'{path}/{issue["number"]}', {"state": "closed", "state_reason": "completed"})
        self.emit(run, "Issue closed", issue["html_url"])

    def pull_request(self, plan, run, iteration):
        root = f'/repos/{plan["repository"]}'
        suffix = f'{run["id"]}-{iteration + 1}'
        branch = f'forge/{plan["mode"]}/{suffix}'
        base = self.github.call("GET", f'{root}/git/ref/heads/{quote(plan["base"], safe="")}')
        self.checkpoint(run)
        self.github.call("POST", root + "/git/refs", {"ref": "refs/heads/" + branch, "sha": base["object"]["sha"]})
        self.emit(run, "Branch created: " + branch)
        message = f'docs: record {plan["mode"]} exercise {iteration + 1}'
        if plan["mode"] == "pair-extraordinaire":
            message += f'\n\nCo-authored-by: {plan["coauthor_name"]} <{plan["coauthor_email"]}>'
        self.checkpoint(run)
        content = f'# Workflow journal\n\nMode: {plan["mode"]}\nRun: {suffix}\n\nCreated with Achievement Forge by brunnodev.\n'
        commit = self.github.call("PUT", root + f'/contents/.achievement-forge/{suffix}.md', {
            "message": message, "content": base64.b64encode(content.encode()).decode(), "branch": branch})
        self.emit(run, "Journal committed", commit["commit"]["html_url"])
        self.checkpoint(run)
        pr = self.github.call("POST", root + "/pulls", {"title": f'Achievement Forge · {plan["mode"]} exercise',
            "head": branch, "base": plan["base"], "body": "Sandbox workflow exercise. Adds one journal file under `.achievement-forge/`.\n\nCreated by Achievement Forge · brunnodev."})
        self.emit(run, f'PR #{pr["number"]} opened', pr["html_url"])
        self.checkpoint(run)
        current = self.github.call("GET", root + f'/pulls/{pr["number"]}')
        expected = commit["commit"]["sha"]
        if current["head"]["sha"] != expected:
            raise ForgeError("PR head changed. Merge stopped; inspect the pull request.")
        result = self.github.call("PUT", root + f'/pulls/{pr["number"]}/merge', {"sha": expected, "merge_method": "merge"})
        if result.get("merged") is not True:
            raise ForgeError("Merge was not accepted. Inspect required checks and branch rules.")
        self.emit(run, "Pull request merged", pr["html_url"])
        self.emit(run, "Exercise branch retained for inspection: " + branch)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def allowed_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {"error": "Local access only."})
        if self.path == "/api/status":
            return self.reply(200, {"demo": self.server.engine.github is None, "csrf": self.server.csrf})
        if self.path.startswith("/api/runs/"):
            try:
                return self.reply(200, self.server.engine.snapshot(self.path.split("/")[-1]))
            except ForgeError as error:
                return self.reply(404, {"error": str(error)})
        if self.path.startswith("/api/"):
            return self.reply(404, {"error": "Not found."})
        return super().do_GET()

    def do_POST(self):
        expected_origin = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if not self.allowed_host() or self.headers.get("Origin") not in expected_origin or self.headers.get("X-Forge-CSRF") != self.server.csrf:
            return self.reply(403, {"error": "Open the local application and try again."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ForgeError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ForgeError("Expected an object.")
            if self.path == "/api/plan":
                return self.reply(200, self.server.engine.plan(data))
            if self.path == "/api/execute":
                return self.reply(202, self.server.engine.start(data.get("plan_id"), data.get("confirmation")))
            if self.path == "/api/cancel":
                with self.server.engine.lock:
                    run = self.server.engine.runs.get(data.get("run_id"))
                    if not run:
                        raise ForgeError("Execution not found.")
                    run["cancel"] = True
                return self.reply(200, {"ok": True})
            return self.reply(404, {"error": "Not found."})
        except (ForgeError, ValueError) as error:
            return self.reply(400, {"error": str(error)})
        except Exception:
            return self.reply(500, {"error": "Request failed. Inspect the repository before retrying."})


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    port = int(os.environ.get("FORGE_PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.engine = Engine(GitHub(token) if token else None, ROOT / ".local" / "audit.jsonl")
    server.csrf = secrets.token_urlsafe(32)
    print(f'Achievement Forge · {"LIVE" if token else "DEMO"} · http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
