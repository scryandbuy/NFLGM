import unittest
import trade_engine as E


class VeteranWindowTests(unittest.TestCase):
    def test_birthday_has_no_jump(self):
        for window in E.WINDOW_AGE_BIAS:
            for age in (29.999, 30, 30.001, 32.999, 33, 33.001):
                delta = abs(E.veteran_window_factor(age + .001, window) -
                            E.veteran_window_factor(age, window))
                self.assertLess(delta, .0002)

    def test_preferences_phase_in_and_remain_bounded(self):
        for window, full in E.WINDOW_AGE_BIAS.items():
            self.assertEqual(E.veteran_window_factor(25, window), 1)
            self.assertEqual(E.veteran_window_factor(30, window), 1)
            self.assertAlmostEqual(E.veteran_window_factor(31.5, window), (1 + full) / 2)
            self.assertAlmostEqual(E.veteran_window_factor(33, window), full)
            self.assertAlmostEqual(E.veteran_window_factor(40, window), full)

    def test_real_pricing_uses_continuous_factor(self):
        for pos in ('QB', 'HB', 'WR', 'SS', 'LEDG'):
            for wins, avg in ((.75, 27), (.25, 29)):
                values = []
                for age in (29.999, 30, 30.001):
                    p = dict(age=age, apy=20, ovr=90, contract_years_left=4,
                             madden_position=pos)
                    value = E.trade_value(p, dict(apy=20))
                    a = dict(kind='player', age=age, trade_value=value, need=False,
                             apy=20, inherit=20)
                    values.append(E.team_price(a, dict(win_pct=wins, avg_age=avg), 100, owns=True))
                self.assertLess(max(values) - min(values), .03)


if __name__ == '__main__':
    unittest.main()
