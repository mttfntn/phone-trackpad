"""Project consistency: the version and the supported Python versions agree everywhere they're
written, and the README lists every command-line option."""
import re
import unittest

from helpers import APP_DIR, REPO, fresh_import

PYPROJECT = (REPO / "pyproject.toml").read_text(encoding="utf-8")
SUPPORTED = ["3.10", "3.11", "3.12", "3.13", "3.14"]


@unittest.skipUnless((APP_DIR / "version.py").exists(), "version before desktop/version.py")
class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.version = fresh_import("version")

    def test_version_matches_pyproject(self):
        self.assertEqual(re.search(r'^version = "([^"]+)"', PYPROJECT, re.M).group(1), self.version.VERSION)
        self.assertRegex(self.version.VERSION, r"^\d+\.\d+\.\d+$")

    def test_min_python_matches_pyproject_and_launchers(self):
        major, minor = self.version.MIN_PYTHON
        self.assertIn(f'requires-python = ">={major}.{minor}"', PYPROJECT)
        self.assertEqual(SUPPORTED[0], f"{major}.{minor}")
        for launcher in ("Phone Trackpad.command", "Phone Trackpad.bat"):
            text = (REPO / launcher).read_text(encoding="utf-8")
            self.assertIn(f"sys.version_info < ({major}, {minor})", text, launcher)
            self.assertIn(f"Python {major}.{minor} or newer", text, launcher)

    def test_supported_versions_listed_and_tested(self):
        listed = re.findall(r'"Programming Language :: Python :: (3\.\d+)"', PYPROJECT)
        self.assertEqual(listed, SUPPORTED)
        ci = REPO / ".github" / "workflows" / "ci.yml"
        if ci.exists():
            matrix = re.search(r"python:\s*\[([^\]]+)\]", ci.read_text(encoding="utf-8")).group(1)
            self.assertEqual([v.strip().strip('"') for v in matrix.split(",")], SUPPORTED)

    def test_readme_lists_every_option(self):
        main = (APP_DIR / "main.py").read_text(encoding="utf-8")
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        options = re.findall(r'add_argument\((?:"-\w", )?"(--[\w-]+)"', main)
        self.assertGreaterEqual(len(options), 6)
        for opt in options:
            self.assertIn(f"`{opt}", readme, opt)


if __name__ == "__main__":
    unittest.main()
