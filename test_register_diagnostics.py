"""The register must not score a protection clock as QB release time."""

import contextlib
import io
import unittest
from unittest.mock import patch

import calibrate


class RegisterDiagnosticTests(unittest.TestCase):
    def test_protection_time_remains_visible_but_outside_nfl_target_count(self):
        got = {name: real for name, real, _, _ in calibrate.TARGETS}
        got['time_to_throw'] = 2.54
        collector = calibrate.Collector()
        display = io.StringIO()
        with patch.object(collector, 'got', return_value=got), contextlib.redirect_stdout(display):
            collector.report('register diagnostic')
        out = display.getvalue()
        self.assertNotIn('time_to_throw', {row[0] for row in calibrate.TARGETS})
        self.assertIn('time_to_throw', out)
        self.assertIn('protection-time proxy; QB release is not modeled', out)
        self.assertIn(f'{len(calibrate.TARGETS)}/{len(calibrate.TARGETS)} within tolerance', out)


if __name__ == '__main__':
    unittest.main()
