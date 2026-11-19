"""Run with: python -m unittest discover tests  (works on Windows, macOS and Linux)."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from winpurge.apps import App, build_uninstall_command
from winpurge.caches import scan_caches, scan_projects
from winpurge.common import CHECK, SAFE, Item, folder_size, is_protected, normalize
from winpurge.leftovers import find_leftovers, find_orphans
from winpurge.trash import IgnoreList, recycle

MB = 1024 * 1024


def write(path: Path, size=10, age_days=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
        os.utime(path.parent, (t, t))


class FakePC(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.root = r
        self.env = {
            "USERPROFILE": str(r / "Users/me"),
            "APPDATA": str(r / "Users/me/AppData/Roaming"),
            "LOCALAPPDATA": str(r / "Users/me/AppData/Local"),
            "TEMP": str(r / "Users/me/AppData/Local/Temp"),
            "ProgramData": str(r / "ProgramData"),
            "ProgramFiles": str(r / "Program Files"),
            "ProgramFiles(x86)": str(r / "Program Files (x86)"),
            "SystemRoot": str(r / "Windows"),
            "SystemDrive": str(r),
        }
        for v in self.env.values():
            Path(v).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def p(self, var, *parts):
        return Path(self.env[var], *parts)


class TestNormalize(unittest.TestCase):
    def test_strips_versions_and_arch(self):
        self.assertEqual(normalize("Notepad++ (64-bit x64) 8.6.2"), "notepad++")
        self.assertEqual(normalize("Mozilla Firefox (x64 en-US)"), "mozillafirefox")
        from winpurge.leftovers import app_names
        self.assertIn("firefox", app_names(App("ff", "Mozilla Firefox (x64 en-US)", "Mozilla")))
        self.assertEqual(normalize("7-Zip 23.01 (x64)"), "7zip")


class TestUninstallCommand(unittest.TestCase):
    def test_msi_uses_uninstall_not_repair(self):
        a = App(key_name="{12345678-1234-1234-1234-1234567890AB}", name="Thing",
                uninstall_string="MsiExec.exe /I{12345678-1234-1234-1234-1234567890AB}")
        self.assertEqual(build_uninstall_command(a), ["msiexec.exe", "/X", "{12345678-1234-1234-1234-1234567890AB}"])

    def test_exe_kept_as_is(self):
        a = App(key_name="Foo", name="Foo", uninstall_string='"C:\\Program Files\\Foo\\unins000.exe"')
        self.assertEqual(build_uninstall_command(a), '"C:\\Program Files\\Foo\\unins000.exe"')


class TestLeftovers(FakePC):
    def test_finds_appdata_and_publisher_subfolder(self):
        write(self.p("APPDATA", "Obsidian", "settings.json"))
        write(self.p("LOCALAPPDATA", "Obsidian", "cache.bin"))
        write(self.p("ProgramData", "Acme", "Widget Pro", "data.db"))
        write(self.p("ProgramData", "Acme", "Gadget", "keep.db"))   # other Acme app
        write(self.p("APPDATA", "Discord", "x"))                      # unrelated
        obsidian = App("Obsidian", "Obsidian", "Obsidian")
        widget = App("WidgetPro", "Widget Pro 2.1", "Acme")
        gadget = App("Gadget", "Gadget", "Acme")

        found = {Path(i.path) for i in find_leftovers(obsidian, [gadget], self.env)}
        self.assertEqual(found, {self.p("APPDATA", "Obsidian"), self.p("LOCALAPPDATA", "Obsidian")})

        found = {Path(i.path) for i in find_leftovers(widget, [gadget], self.env)}
        self.assertEqual(found, {self.p("ProgramData", "Acme", "Widget Pro")},
                         "must take only the app's subfolder while Gadget (same publisher) is installed")

    def test_whole_publisher_folder_when_nothing_else_from_it(self):
        write(self.p("APPDATA", "Acme", "Widget Pro", "a"))
        widget = App("WidgetPro", "Widget Pro", "Acme")
        found = {Path(i.path) for i in find_leftovers(widget, [], self.env)}
        self.assertEqual(found, {self.p("APPDATA", "Acme")})

    def test_skips_folder_still_used_by_installed_app(self):
        write(self.p("APPDATA", "Code", "x"))
        old = App("VSCodeOld", "Code", "Microsoft")
        new = App("VSCodeNew", "Code", "Microsoft")
        self.assertEqual(find_leftovers(old, [new], self.env), [])

    def test_bad_install_location_is_never_offered(self):
        app = App("Bad", "Bad", install_location=self.env["ProgramFiles"])
        self.assertEqual(find_leftovers(app, [], self.env), [])

    def test_orphans_are_old_unmatched_and_check_first(self):
        write(self.p("APPDATA", "OldTool", "f"), age_days=200)
        write(self.p("APPDATA", "FreshTool", "f"))                     # too recent
        write(self.p("APPDATA", "Obsidian", "f"), age_days=200)       # installed
        write(self.p("APPDATA", "Microsoft", "f"), age_days=200)      # system
        items = find_orphans([App("Obsidian", "Obsidian")], self.env)
        self.assertEqual([Path(i.path).name for i in items], ["OldTool"])
        self.assertEqual(items[0].level, CHECK)
        self.assertFalse(items[0].checked)


class TestCaches(FakePC):
    def test_finds_known_caches_with_profiles(self):
        write(self.p("LOCALAPPDATA", "npm-cache", "_cacache", "big"), 2 * MB)
        write(self.p("LOCALAPPDATA", "Google", "Chrome", "User Data", "Default", "Cache", "f"), 2 * MB)
        write(self.p("LOCALAPPDATA", "Google", "Chrome", "User Data", "Profile 1", "Cache", "f"), 2 * MB)
        write(self.p("LOCALAPPDATA", "Google", "Chrome", "User Data", "Default", "History"), 2 * MB)
        write(self.p("LOCALAPPDATA", "pip", "Cache", "tiny"), 10)  # under 1 MB: skipped
        labels = sorted(i.label for i in scan_caches(self.env))
        self.assertEqual(labels, ["Chrome cache (Default)", "Chrome cache (Profile 1)", "npm cache"])

    def test_temp_pointing_at_profile_is_refused(self):
        env = dict(self.env, TEMP=self.env["USERPROFILE"])
        write(Path(env["USERPROFILE"], "Documents", "thesis.docx"), 2 * MB)
        self.assertNotIn("Temporary files", [i.label for i in scan_caches(env)])

    def test_projects(self):
        proj = self.root / "code" / "oldapp"
        write(proj / "package.json", age_days=90)
        write(proj / "src" / "index.js", age_days=90)
        write(proj / "node_modules" / "react" / "index.js", 3 * MB)
        fresh = self.root / "code" / "newapp"
        write(fresh / "package.json")
        write(fresh / "node_modules" / "x.js", 3 * MB)
        notdotnet = self.root / "code" / "scripts"
        write(notdotnet / ".git" / "HEAD", age_days=90)
        write(notdotnet / "bin" / "deploy.sh", age_days=90)  # 'bin' without a .csproj: real files
        items = scan_projects([str(self.root / "code")], min_age_days=30)
        self.assertEqual([Path(i.path) for i in items], [proj / "node_modules"])
        self.assertEqual(items[0].level, SAFE)


class TestSafety(FakePC):
    def test_protected(self):
        for var in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "ProgramFiles", "ProgramData"):
            self.assertTrue(is_protected(self.env[var], self.env), var)
        self.assertTrue(is_protected(Path(self.env["SystemRoot"], "System32"), self.env))
        self.assertFalse(is_protected(self.p("APPDATA", "Obsidian"), self.env))

    def test_size_does_not_follow_links(self):
        write(self.root / "big" / "f", 5 * MB)
        d = self.p("APPDATA", "Thing")
        write(d / "small", 100)
        os.symlink(self.root / "big", d / "link")
        self.assertEqual(folder_size(d), 100)

    def test_recycle_moves_never_deletes_and_keeps_temp_folder(self):
        trash = self.root / "FakeRecycleBin"
        old_env = dict(os.environ)
        os.environ.update(self.env)
        os.environ["WINPURGE_FAKE_TRASH"] = str(trash)
        try:
            write(self.p("APPDATA", "Obsidian", "a"), 50)
            write(self.p("TEMP", "junk1.tmp"), 50)
            write(self.p("TEMP", "sub", "junk2.tmp"), 50)
            res = recycle([
                Item(path=str(self.p("APPDATA", "Obsidian")), label="", category="", size=50),
                Item(path=self.env["TEMP"], label="", category="", extra={"contents_only": True}),
                Item(path=self.env["APPDATA"], label="", category=""),  # protected
            ])
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        self.assertFalse(self.p("APPDATA", "Obsidian").exists())
        self.assertTrue(Path(self.env["TEMP"]).is_dir())
        self.assertEqual(list(Path(self.env["TEMP"]).iterdir()), [])
        self.assertTrue(Path(self.env["APPDATA"]).is_dir())
        self.assertEqual(len(list(trash.iterdir())), 3)
        self.assertEqual(len(res.failed), 1)
        self.assertIn("Protected", res.failed[0][1])


class TestIgnore(FakePC):
    def test_ignore_and_expiry(self):
        ig = IgnoreList(self.root / "ignored.json")
        ig.add("C:\\X")
        ig.add("C:\\Y", days=-1)  # already expired
        ig2 = IgnoreList(self.root / "ignored.json")
        self.assertTrue(ig2.contains("C:\\X"))
        self.assertFalse(ig2.contains("C:\\Y"))


class TestPermissions(unittest.TestCase):
    def test_nothing_allowed_before_setup(self):
        from winpurge.permissions import PERMISSIONS, allowed, needs_setup
        self.assertTrue(needs_setup({}))
        for p in PERMISSIONS:
            self.assertFalse(allowed({}, p.key))

    def test_choices_saved_and_project_roots_dropped_when_off(self):
        from winpurge.permissions import allowed, complete_setup, needs_setup
        s = complete_setup({}, {"scan_caches": False, "scan_projects": False}, ["C:\\code"])
        self.assertFalse(needs_setup(s))
        self.assertTrue(allowed(s, "read_apps"))       # default on
        self.assertFalse(allowed(s, "scan_caches"))     # turned off
        self.assertFalse(allowed(s, "registry_cleanup"))  # default off
        self.assertEqual(s["project_roots"], [])

    def test_unknown_permission_rejected(self):
        from winpurge.permissions import allowed, complete_setup
        with self.assertRaises(KeyError):
            complete_setup({}, {"internet": True}, [])
        with self.assertRaises(KeyError):
            allowed({}, "internet")


class TestOffline(unittest.TestCase):
    """The setup screen promises WinPurge never goes online. Keep that true."""

    def test_no_network_code(self):
        import re
        banned = re.compile(r"^\s*(import|from)\s+(socket|urllib|http|requests|ftplib|smtplib|asyncio|webbrowser|ssl)\b", re.M)
        src = Path(__file__).resolve().parent.parent / "winpurge"
        for f in src.glob("*.py"):
            self.assertIsNone(banned.search(f.read_text("utf-8")), f"network import in {f.name}")


if __name__ == "__main__":
    unittest.main()
