#!/usr/bin/env python3
"""strain.py: the relative strain index (no server)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from datetime import datetime, timedelta

import strain as sx


def dt(h, m=0, day=11):   # 2026-11-11 is a Wednesday
    return datetime(2026, 11, day, h, m)


class TestParts(unittest.TestCase):
    def test_circadian_deepest_at_night(self):
        self.assertEqual(sx.circadian(dt(4)), 1.0)
        self.assertGreater(sx.circadian(dt(3)), sx.circadian(dt(10)))
        self.assertGreater(sx.circadian(dt(14, 30)), sx.circadian(dt(11)))   # after-lunch dip
        self.assertAlmostEqual(sx.circadian(dt(23, 59)), sx.circadian(dt(0)), places=1)

    def test_duty_start(self):
        self.assertEqual(sx.duty_start(dt(10)), dt(8))                 # weekday day shift
        self.assertEqual(sx.duty_start(dt(20)), dt(14))                # weekday on-call
        self.assertEqual(sx.duty_start(dt(3)), dt(14, day=10))         # night: yesterday 14:00
        self.assertEqual(sx.duty_start(dt(3, day=14)), dt(14, day=13)) # Sat 03:00: Friday's block
        self.assertEqual(sx.duty_start(dt(20, day=14)), dt(8, day=14)) # Saturday: 08:00 block
        self.assertEqual(sx.duty_start(dt(3, day=15)), dt(8, day=14))  # Sunday 03:00: Saturday's
        self.assertEqual(sx.duty_hours(dt(8)), 0.0)

    def test_run_without_break(self):
        s = [(dt(10, 0), dt(10, 20)), (dt(10, 25), dt(10, 45)), (dt(10, 50), dt(11, 10))]
        self.assertEqual(sx.run_without_break(s, dt(11, 12)), timedelta(minutes=70))
        self.assertEqual(sx.run_without_break(s, dt(11, 30)), timedelta(0))      # idle > 10 min
        s2 = [(dt(8, 0), dt(8, 20)), (dt(10, 0), dt(10, 20))]                    # a long break between
        self.assertEqual(sx.run_without_break(s2, dt(10, 25)), timedelta(minutes=20))
        self.assertEqual(sx.run_without_break([], dt(10)), timedelta(0))

    def test_rushing_needs_samples_and_a_shorter_median(self):
        self.assertEqual(sx.rushing([4, 4], 8.0), 0.0)            # too few
        self.assertEqual(sx.rushing([4, 4, 4], 8.0), 1.0)         # half the usual
        self.assertEqual(sx.rushing([8, 9, 10], 8.0), 0.0)        # not shorter
        self.assertEqual(sx.rushing([6, 6, 6], 8.0), 0.5)


class TestIndex(unittest.TestCase):
    def test_bounds_and_calm_vs_bad(self):
        calm = sx.strain(dt(10), 0.2, 0.0, 5, [], None)
        bad = sx.strain(dt(4), 1.2, 5.0, 90,
                        [(dt(0) + timedelta(minutes=12 * i), dt(0) + timedelta(minutes=12 * i + 6)) for i in range(20)], 12.0)
        self.assertTrue(0 <= calm['index'] < bad['index'] <= 100)
        self.assertLess(calm['index'], 25)
        self.assertGreater(bad['index'], 75)
        self.assertEqual(set(calm['c']), set(sx.WEIGHTS))

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(sx.WEIGHTS.values()), 1.0)

    def test_night_is_worse_than_day_at_equal_load(self):
        day = sx.strain(dt(10), 0.7, 1.0, 20, [], None)
        night = sx.strain(dt(4), 0.7, 1.0, 20, [], None)
        self.assertGreater(night['index'], day['index'])


if __name__ == '__main__':
    unittest.main()
