import unittest
import test_checkdown_routes as routes


class DesignedReadAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        routes.CheckdownRoutes.setUpClass()
        cls.harness = routes.CheckdownRoutes()

    def test_downfield_designed_reads_use_normal_accuracy(self):
        for depth, concept in (("medium", "dagger"), ("deep", "four_verts")):
            checked = 0
            for seed in range(30):
                out, rows, _, trace, _ = self.harness.resolve(seed, depth=depth,
                    concept=concept, forced_read="designed", protection="five")
                for throw in trace:
                    if "rmod" in throw and throw["depth"] != "short":
                        self.assertEqual(throw["rmod"], 1.0)
                        checked += 1
            self.assertGreater(checked, 0)

    def test_short_designed_throws_keep_benefit(self):
        checked = 0
        for seed in range(30):
            _, _, _, trace, _ = self.harness.resolve(seed, depth="short",
                concept="screen", forced_read="designed", protection="five")
            for throw in trace:
                if "rmod" in throw:
                    self.assertEqual(throw["rmod"], 1.37)
                    checked += 1
        self.assertGreater(checked, 0)

    def test_actual_seed_twenty_deep_read(self):
        _, _, _, trace, _ = self.harness.resolve(20)
        self.assertTrue(any(t.get("depth") == "deep" and t.get("rmod") == 1.0
                            for t in trace))


if __name__ == "__main__":
    unittest.main()
