"""The mock-up skill folder: files, frontmatter, English-only text, no home skill path."""
import re
import subprocess
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "mock-up"
FILES = [
    "SKILL.md", "scripts/capture.sh", "templates/canvas.html",
    "references/effects.md", "references/flow.md", "references/frames.md",
    "references/wireframe.md", "references/doc-slide.md",
    "examples/doc.html", "examples/doc.png", "examples/slide.html", "examples/slide.png",
]
HANGUL = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")
TEXT_SUFFIXES = {".md", ".html", ".sh"}


def text_files():
    return [p for p in sorted(SKILL.rglob("*")) if p.is_file() and p.suffix in TEXT_SUFFIXES]


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


class MockupSkillTest(unittest.TestCase):
    def test_files_exist(self):
        for rel in FILES:
            self.assertTrue((SKILL / rel).is_file(), rel)

    def test_frontmatter(self):
        fm = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertRegex(fm, r"(?m)^name: mock-up$")
        self.assertRegex(fm, r"(?m)^description: \S")
        hint = re.search(r"(?m)^argument-hint: (.*)$", fm)
        self.assertIsNotNone(hint)
        self.assertIn("output file path", hint.group(1))
        self.assertNotIn("disable-model-invocation", fm)

    def test_english_only(self):
        for p in text_files():
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if HANGUL.search(line):
                    # the one Korean word-break example in doc-slide.md stays
                    ok = p.name == "doc-slide.md" and "청/구서" in line
                    self.assertTrue(ok, f"{p.relative_to(SKILL)}:{n}: {line[:80]}")

    def test_no_home_skill_path(self):
        for p in text_files():
            text = p.read_text(encoding="utf-8")
            rel = p.relative_to(SKILL)
            self.assertNotIn("~/.claude/skills", text, str(rel))
            for line in text.splitlines():
                self.assertIsNone(re.search(r"(?<!\.)my-mockup", line), f"{rel}: {line[:80]}")

    def test_default_and_given_output(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("<cwd>/.my-mockup/<yymmdd>-<slug>/index.html", text)
        self.assertIn("output file path", text)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/mock-up", text)

    def test_capture_script_parses(self):
        script = SKILL / "scripts" / "capture.sh"
        r = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = script.read_text(encoding="utf-8")
        for needle in ("mockup-size", "?capture=1", "CHROME_BIN"):
            self.assertIn(needle, body)


if __name__ == "__main__":
    unittest.main()
