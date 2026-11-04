"""Source control with Git for a project (hoard/vpm/git.py, issues #296 to #299), with a real Git in temporary folders:
finding Git, setting a project up with VRChat's ignore rules, its changes, commits and history, remotes, branches,
conflicts and clones. Skipped where Git isn't installed (GitHub Actions has it)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard.vpm import git  # noqa: E402

HAVE_GIT = bool(shutil.which("git"))


def unity_project(folder: Path, packages=("com.vrchat.base", "com.vrchat.avatars", "nadena.dev.modular-avatar")) -> Path:
    """A Unity project as the Creator Companion makes one: its assets and settings, its manifests, VRChat's packages
    and the resolver installed, another VPM package, and Unity's cache."""
    for sub in ("Assets/Scenes", "ProjectSettings", "Library/ScriptAssemblies", "Temp", "Logs", "Packages/com.vrchat.core.vpm-resolver"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / "Assets" / "Scenes" / "Main.unity").write_text("%YAML 1.1\nscene\n")
    (folder / "Assets" / "Scenes" / "Main.unity.meta").write_text("guid: 1234\n")
    (folder / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n")
    (folder / "Library" / "ScriptAssemblies" / "Game.dll").write_bytes(b"MZ\0\0")
    (folder / "Packages" / "manifest.json").write_text(json.dumps({"dependencies": {}}))
    (folder / "Packages" / "vpm-manifest.json").write_text(json.dumps({"dependencies": {}, "locked": {n: {"version": "1.0.0"} for n in packages}}))
    (folder / "Packages" / "com.vrchat.core.vpm-resolver" / "package.json").write_text("{}")
    for n in packages:
        (folder / "Packages" / n).mkdir(exist_ok=True)
        (folder / "Packages" / n / "package.json").write_text(json.dumps({"name": n}))
    return folder


@unittest.skipUnless(HAVE_GIT, "needs Git installed")
class Git(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hoard-git-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # (your own Git settings left out: a Git of nobody's, but for who commits)
        conf = self.tmp / "gitconfig"
        conf.write_text("[user]\n\tname = Kitsu\n\temail = kitsu@example.com\n[init]\n\tdefaultBranch = main\n")
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(conf), "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        git.find(again=True)
        self.project = unity_project(self.tmp / "Unity" / "Rusk Avatar")

    def sh(self, folder, *args) -> str:
        return subprocess.run(["git", *args], cwd=folder, capture_output=True, text=True, check=True).stdout

    def test_git_missing_or_too_old(self):
        with mock.patch.object(git, "_candidates", lambda: []):
            self.assertEqual(git.state(self.project, again=True)["state"], "missing")
            with self.assertRaises(git.GitError) as e:
                git.run(self.project, ["status"])
            self.assertEqual(e.exception.code, "missing")
            self.assertIn("git-scm.com", str(e.exception))
        with mock.patch.object(git, "_version", lambda exe: (2, 20, 1)):
            s = git.state(self.project, again=True)
            self.assertEqual((s["state"], s["git"]["version"]), ("old", "2.20.1"))
        self.assertTrue(git.find(again=True)["ok"])

    def test_set_up_with_vrchats_rules(self):
        """Issue #296: the ignore rules are shown first, then written, then git init: the project's own files are
        kept (the resolver too), Unity's cache and the installed VPM packages left out."""
        self.assertEqual(git.state(self.project)["state"], "none")
        plan = {f["path"]: f for f in git.ignore_plan(self.project)}
        self.assertEqual(set(plan), {".gitignore", "Packages/.gitignore"})
        self.assertIn("/[Ll]ibrary/", plan[".gitignore"]["add"])
        self.assertEqual(plan["Packages/.gitignore"]["add"], ["/com.vrchat.*", "!/com.vrchat.core.*", "/nadena.dev.modular-avatar/"])
        before = git.examples(self.project)
        self.assertIn("Packages/com.vrchat.core.vpm-resolver", before["kept"])
        self.assertIn("Library", before["left_out"])
        done = git.set_up(self.project)
        self.assertEqual(done["written"], [".gitignore", "Packages/.gitignore"])
        self.assertTrue((self.project / ".git").is_dir())
        self.assertIn("Assets/", done["kept"])
        self.assertTrue(any(x.startswith("Library") for x in done["left_out"]), done)
        ignored = lambda rel: subprocess.run(["git", "check-ignore", "-q", rel], cwd=self.project).returncode == 0  # noqa: E731
        self.assertFalse(ignored("Packages/com.vrchat.core.vpm-resolver/package.json"), "the resolver is kept")
        for kept in ("Assets/Scenes/Main.unity", "Assets/Scenes/Main.unity.meta", "ProjectSettings/ProjectVersion.txt",
                     "Packages/manifest.json", "Packages/vpm-manifest.json"):
            self.assertFalse(ignored(kept), kept)
        for left in ("Library/ScriptAssemblies/Game.dll", "Temp/x", "Logs/x", "Packages/com.vrchat.avatars/package.json",
                     "Packages/com.vrchat.base/package.json", "Packages/nadena.dev.modular-avatar/package.json"):
            self.assertTrue(ignored(left), left)
        self.assertEqual(git.ignore_plan(self.project), [], "nothing more to add")
        with self.assertRaises(git.GitError):
            git.set_up(self.project)

    def test_an_ignore_file_thats_there_is_added_to(self):
        (self.project / ".gitignore").write_text("# mine\n/[Ll]ibrary/\n*.blend\n")
        (plan,) = [f for f in git.ignore_plan(self.project) if f["path"] == ".gitignore"]
        self.assertTrue(plan["exists"])
        self.assertNotIn("/[Ll]ibrary/", plan["add"], "a rule it has isn't added again")
        git.set_up(self.project)
        text = (self.project / ".gitignore").read_text()
        self.assertTrue(text.startswith("# mine\n/[Ll]ibrary/\n*.blend\n"), "never replaced")
        self.assertIn(git.ADDED_BY_HOARD, text)
        self.assertEqual(text.count("/[Ll]ibrary/"), 1)
        # a package installed since: its rule is offered, and added
        (self.project / "Packages" / "com.vrcfury.vrcfury").mkdir()
        manifest = json.loads((self.project / "Packages" / "vpm-manifest.json").read_text())
        manifest["locked"]["com.vrcfury.vrcfury"] = {"version": "1.0.0"}
        (self.project / "Packages" / "vpm-manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(git.state(self.project)["ignore_missing"], ["Packages/.gitignore"])
        git.update_ignore(self.project)
        self.assertIn("/com.vrcfury.vrcfury/", (self.project / "Packages" / ".gitignore").read_text())

    def test_inside_another_repository_or_a_worktree(self):
        outer = self.tmp / "Unity"
        self.sh(outer, "init", "-q")
        s = git.state(self.project)
        self.assertEqual((s["state"], s["parent"]), ("none", str(outer)))
        with self.assertRaises(git.GitError) as e:
            git.set_up(self.project)
        self.assertEqual(e.exception.code, "nested")
        self.assertFalse((self.project / ".git").exists())
        git.set_up(self.project, nested=True)
        self.assertTrue(git.where(self.project)["repo"])
        # a linked worktree: its .git is a file
        self.sh(self.project, "add", "-A")
        self.sh(self.project, "commit", "-qm", "First")
        wt = self.tmp / "Unity" / "Rusk Avatar (branch)"
        self.sh(self.project, "worktree", "add", "-q", "-b", "other", str(wt))
        self.assertTrue((wt / ".git").is_file())
        w = git.where(wt)
        self.assertEqual((w["repo"], w["worktree"]), (True, True))

    def test_changes_commits_and_history(self):
        """Issue #297: files with spaces and other languages' letters; staged, unstaged, renamed and new; a binary
        file's diff; a commit needs a message and staged files; the history read back."""
        git.set_up(self.project)
        with self.assertRaises(git.GitError):
            git.commit(self.project, "First")   # (nothing staged)
        names = ["Assets/My Hat.mat", "Assets/テクスチャ 1.png", "Assets/Notes (old).txt"]
        (self.project / names[0]).write_text("color: red\n")
        (self.project / names[1]).write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0data")
        (self.project / names[2]).write_text("one\ntwo\n")
        s = git.state(self.project)
        self.assertEqual(s["state"], "changes")
        self.assertTrue(s["initial"])
        self.assertIn("Assets/", {f["path"] for f in s["files"]}, "a new folder, as one")
        self.assertEqual(git.stage(self.project, ["Assets/", ".gitignore", "Packages/", "ProjectSettings/"]), 4)
        with self.assertRaises(git.GitError):
            git.stage(self.project, ["../outside.txt"])
        staged = {f["path"]: f for f in git.state(self.project)["files"]}
        for n in names:
            self.assertTrue(staged[n]["staged"] and not staged[n]["unstaged"], n)
        d = git.diff(self.project, names[1], staged=True)
        self.assertTrue(d["binary"])
        d = git.diff(self.project, names[2], staged=True)
        self.assertEqual((d["binary"], d["added"], d["removed"]), (False, 2, 0))
        self.assertIn("+two", d["text"])
        self.assertEqual(git.unstage(self.project, [names[2]]), 1)
        self.assertFalse({f["path"]: f for f in git.state(self.project)["files"]}[names[2]]["staged"])
        with self.assertRaises(git.GitError):
            git.commit(self.project, "  ")
        first = git.commit(self.project, "First: the avatar\n\nWith its hat.")
        self.assertEqual(first["subject"], "First: the avatar")
        # changed, renamed, and a new file
        (self.project / names[0]).write_text("color: blue\n")
        self.sh(self.project, "mv", names[1], "Assets/Texture 1.png")
        files = {f["path"]: f for f in git.state(self.project)["files"]}
        self.assertEqual(files["Assets/Texture 1.png"]["from"], names[1])
        self.assertTrue(files["Assets/Texture 1.png"]["staged"])
        self.assertEqual((files[names[0]]["x"], files[names[0]]["y"]), (".", "M"))
        d = git.diff(self.project, names[0])
        self.assertIn("-color: red", d["text"])
        self.assertIn("+color: blue", d["text"])
        git.stage(self.project, [names[0]])
        git.unstage(self.project, ["Assets/Texture 1.png"])
        git.stage(self.project, ["Assets/Texture 1.png", names[1]])
        second = git.commit(self.project, "Blue hat")
        log = git.history(self.project)
        self.assertEqual([c["subject"] for c in log], ["Blue hat", "First: the avatar"])
        self.assertEqual(log[0]["author"], "Kitsu")
        self.assertIn("main", log[0]["refs"])
        changed = {f["path"]: f["status"] for f in git.commit_files(self.project, second["hash"])}
        self.assertEqual(changed[names[0]], "M")
        self.assertEqual(changed["Assets/Texture 1.png"], "R")
        self.assertIn("+color: blue", git.diff(self.project, names[0], ref=second["hash"])["text"])
        with self.assertRaises(git.GitError):
            git.commit_files(self.project, "HEAD; rm -rf /")
        self.assertEqual(git.state(self.project)["state"], "changes", "the one not staged is still there")

    def test_who_commits(self):
        git.set_up(self.project)
        (Path(os.environ["GIT_CONFIG_GLOBAL"])).write_text("")
        git.stage(self.project, ["Assets/"])
        with self.assertRaises(git.GitError) as e:
            git.commit(self.project, "First")
        self.assertEqual(e.exception.code, "identity")
        with self.assertRaises(git.GitError):
            git.set_identity(self.project, "Kitsu", "not an email")
        self.assertEqual(git.set_identity(self.project, "Kitsu", "kitsu@example.com"), {"name": "Kitsu", "email": "kitsu@example.com"})
        self.assertEqual(git.commit(self.project, "First")["author"], "Kitsu")

    def test_remotes_sync_and_branches(self):
        """Issue #298: a remote added (never with a token in its address), pushed to, fetched with ahead and behind
        counted, pulled; branches made, switched to and deleted; a switch refused with changes or Unity open."""
        remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        git.set_up(self.project)
        git.stage(self.project, [f["path"] for f in git.state(self.project)["files"]])
        git.commit(self.project, "First")
        with self.assertRaises(git.GitError):
            git.set_remote(self.project, "add", "origin", "https://kitsu:ghp_abcdefghijklmnopqrstuvwxyz0123@github.com/k/r.git")
        with self.assertRaises(git.GitError):
            git.set_remote(self.project, "add", "origin", "ext::sh -c touch% /tmp/pwned")
        with self.assertRaises(git.GitError):
            git.set_remote(self.project, "add", "--upload-pack=x", str(remote))
        self.assertEqual(git.set_remote(self.project, "add", "origin", str(remote)), [{"name": "origin", "url": str(remote)}])
        seen = []
        self.assertEqual(git.push(self.project, progress=seen.append), "Pushed to origin/main.")
        s = git.state(self.project)
        self.assertEqual((s["upstream"], s["ahead"], s["behind"]), ("origin/main", 0, 0))
        # someone else's commit, there
        other = self.tmp / "other"
        git.clone(str(remote), other)
        (other / "Assets" / "New.txt").write_text("new\n")
        self.sh(other, "add", "-A")
        self.sh(other, "commit", "-qm", "From the other computer")
        self.sh(other, "push", "-q")
        self.assertIn("1 new on origin/main to pull", git.fetch(self.project))
        self.assertEqual(git.state(self.project)["behind"], 1)
        with mock.patch.object(git, "_unity_open", lambda folder: True):
            with self.assertRaises(git.GitError) as e:
                git.pull(self.project)
            self.assertEqual(e.exception.code, "unity")
        git.pull(self.project)
        self.assertTrue((self.project / "Assets" / "New.txt").is_file())
        # branches
        names = lambda: [b["name"] for b in git.branches(self.project)]  # noqa: E731
        git.set_branch(self.project, "new", "outfits")
        self.assertEqual([b["name"] for b in git.branches(self.project) if b["current"]], ["outfits"])
        with self.assertRaises(git.GitError):
            git.set_branch(self.project, "new", "bad name")
        (self.project / "Assets" / "New.txt").write_text("changed\n")
        with self.assertRaises(git.GitError) as e:
            git.set_branch(self.project, "switch", "main")
        self.assertEqual(e.exception.code, "changes")
        self.sh(self.project, "checkout", "--", "Assets/New.txt")
        with mock.patch.object(git, "_unity_open", lambda folder: True):
            with self.assertRaises(git.GitError):
                git.set_branch(self.project, "switch", "main")
        git.set_branch(self.project, "switch", "main")
        git.set_branch(self.project, "delete", "outfits")
        self.assertEqual(names(), ["main"])

    def test_conflicts(self):
        """Issue #299: a pull that can't simply follow on says so; merged, a conflict is found, and the merge can be
        given up, putting your files back."""
        remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        git.set_up(self.project)
        git.stage(self.project, [f["path"] for f in git.state(self.project)["files"]])
        git.commit(self.project, "First")
        git.set_remote(self.project, "add", "origin", str(remote))
        git.push(self.project)
        other = self.tmp / "other"
        git.clone(str(remote), other)
        (other / "Assets" / "Scenes" / "Main.unity").write_text("theirs\n")
        self.sh(other, "commit", "-qam", "Theirs")
        self.sh(other, "push", "-q")
        (self.project / "Assets" / "Scenes" / "Main.unity").write_text("mine\n")
        git.stage(self.project, ["Assets/Scenes/Main.unity"])
        git.commit(self.project, "Mine")
        with self.assertRaises(git.GitError) as e:
            git.pull(self.project)
        self.assertEqual(e.exception.code, "diverged")
        with self.assertRaises(git.GitError):
            git.pull(self.project, merge=True)
        s = git.state(self.project)
        self.assertEqual((s["state"], s["merging"], s["counts"]["conflicts"]), ("conflicts", True, 1))
        git.abort_merge(self.project)
        s = git.state(self.project)
        self.assertEqual((s["state"], s["merging"]), ("clean", False))
        self.assertEqual((self.project / "Assets" / "Scenes" / "Main.unity").read_text(), "mine\n")

    def test_a_bundle_and_a_clone(self):
        git.set_up(self.project)
        self.assertFalse(git.bundle(self.project, self.tmp / "none.bundle"), "nothing committed: no bundle")
        git.stage(self.project, ["Assets/"])
        git.commit(self.project, "First")
        self.assertTrue(git.bundle(self.project, self.tmp / "history.bundle"))
        copy = self.tmp / "copy"
        git.clone(str(self.tmp / "history.bundle"), copy)
        self.assertTrue((copy / "Assets" / "Scenes" / "Main.unity").is_file())
        with self.assertRaises(git.GitError):
            git.clone(str(self.tmp / "history.bundle"), copy)
        self.assertEqual(git.clone_name("https://github.com/kitsu/Rusk-Avatar.git"), "Rusk-Avatar")
        self.assertEqual(git.clone_name("git@github.com:kitsu/rusk.git"), "rusk")


class Addresses(unittest.TestCase):
    """What a remote's address may be, and what's taken out of what Git prints, with or without Git."""

    def test_addresses(self):
        for good in ("https://github.com/kitsu/rusk.git", "ssh://git@github.com/kitsu/rusk.git", "git@github.com:kitsu/rusk.git",
                     "https://kitsu@bitbucket.org/kitsu/rusk.git", os.path.abspath("remote.git")):
            self.assertEqual(git.check_url(good), good)
        for bad in ("", "rusk", "-u", "ext::sh -c id", "fd::3", "https://kitsu:secret@github.com/k/r.git",
                    "https://ghp_abcdefghijklmnopqrstuvwxyz0123@github.com/k/r.git", "ftp://example.com/r.git", "https://", "a b"):
            with self.assertRaises(git.GitError, msg=bad):
                git.check_url(bad)

    def test_whats_taken_out(self):
        self.assertEqual(git.redact("fatal: unable to access 'https://kitsu:hunter2@github.com/k/r.git/'"),
                         "fatal: unable to access 'https://***@github.com/k/r.git/'")
        self.assertEqual(git.redact("token ghp_abcdefghijklmnopqrstuvwxyz0123 refused"), "token [token] refused")


if __name__ == "__main__":
    unittest.main()
