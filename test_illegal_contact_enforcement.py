import unittest
from types import SimpleNamespace
import game as G


class IllegalContactEnforcement(unittest.TestCase):
    def resolve(self, kind, yards, name="Illegal Contact"):
        drive = SimpleNamespace(down=2, togo=10., yardline=80., first_downs=0)
        flag = dict(penalty=name, yards=5., on_offense=False, auto_first=True)
        result = G._resolve_live_penalty(drive, flag, dict(type=kind, yards=yards), {})
        return result, drive

    def test_reported_scramble_takes_first_down(self):
        result, drive = self.resolve("scramble", 9)
        self.assertEqual(result, "replaced")
        self.assertEqual((drive.down, drive.togo, drive.yardline), (1, 10, 75))

    def test_contact_before_sack_is_enforced(self):
        result, drive = self.resolve("sack", -6)
        self.assertEqual(result, "replaced")
        self.assertEqual((drive.down, drive.yardline), (1, 75))

    def test_better_scramble_kept(self):
        result, drive = self.resolve("scramble", 15)
        self.assertIsNone(result)
        self.assertEqual(drive.yardline, 80)  # caller applies the retained play

    def test_completion_still_takes_first_down(self):
        self.assertEqual(self.resolve("complete", 9)[0], "replaced")

    def test_invalid_roughing_is_not_declined(self):
        self.assertEqual(self.resolve("scramble", 9, "Roughing the Passer")[0], "invalid")

    def test_invalid_ineligible_downfield_is_not_declined(self):
        self.assertEqual(self.resolve("sack", -6, "Ineligible Downfield Pass")[0], "invalid")

if __name__ == "__main__":
    unittest.main()
