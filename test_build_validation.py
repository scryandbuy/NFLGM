import tempfile
import unittest
from pathlib import Path
from build_validation import validate_web_sources


class BuildValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        self.html = '<link rel="stylesheet" href="style.css?v=123"><script type="module" src="app.js?v=123"></script>'
        self.write(self.html)

    def write(self, text):
        (self.root / 'docs/index.html').write_text(text, encoding='utf-8')

    def check(self):
        validate_web_sources(self.root, ['docs/index.html'])

    def test_clean_shell(self):
        self.check()

    def test_nested_merge_is_rejected(self):
        self.write('<<<<<<< HEAD\n<<<<<<< HEAD\n' + self.html + '\n=======\n' + self.html + '\n>>>>>>> branch')
        with self.assertRaisesRegex(ValueError, 'unresolved merge conflict'):
            self.check()

    def test_each_marker_in_shipped_source_rejected(self):
        for marker in ('<<<<<<< HEAD', '=======', '>>>>>>> branch', '||||||| base'):
            with self.subTest(marker=marker):
                (self.root / 'engine.py').write_text('first line\n' + marker + '\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'engine.py:2: unresolved'):
                    validate_web_sources(self.root, ['engine.py', 'docs/index.html'])

    def test_duplicate_script_rejected_even_with_different_stamp(self):
        self.write(self.html + '<script type="module" src="app.js?v=456"></script>')
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.check()

    def test_duplicate_stylesheet_rejected(self):
        self.write(self.html + '<link href="style.css?v=456" rel="stylesheet">')
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.check()

    def test_missing_entrypoint_rejected(self):
        self.write('<html></html>')
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.check()


if __name__ == '__main__': unittest.main()
