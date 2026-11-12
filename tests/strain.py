#!/usr/bin/env python3
"""strain.py: the relative strain index (no server)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import math
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

    def test_accumulated_is_the_decayed_integral_since_duty_start(self):
        # 1 h of work ending now: H/ln2 * (1 - 2**(-1/H))
        h = sx.ACCUM_HALF_LIFE_H
        one = sx.accumulated_hours([(dt(9), dt(10))], dt(10))
        self.assertAlmostEqual(one, h / math.log(2) * (1 - 2 ** (-1 / h)), places=6)
        # the same hour 8 h back counts half
        self.assertAlmostEqual(sx.accumulated_hours([(dt(15), dt(16))], dt(0, day=12)), one / 2, places=6)
        # work before the duty block began does not count (Wednesday 14:00)
        self.assertEqual(sx.accumulated_hours([(dt(9), dt(10))], dt(20)), 0.0)
        # a break does not reset it
        self.assertAlmostEqual(sx.accumulated_hours([(dt(9), dt(10))], dt(11)),
                               one * 2 ** (-1 / h), places=6)

    def test_shorter_needs_samples_and_a_shorter_median(self):
        self.assertEqual(sx.shorter([4, 4], 8.0), 0.0)            # too few
        self.assertEqual(sx.shorter([4, 4, 4], 8.0), 1.0)         # half the usual
        self.assertEqual(sx.shorter([8, 9, 10], 8.0), 0.0)        # not shorter
        self.assertEqual(sx.shorter([6, 6, 6], 8.0), 0.5)


def night(n=45, end=dt(4), minutes=12):
    """n exams of `minutes` spread evenly from Tuesday 14:00 to `end`."""
    start = dt(14, day=10)
    step = (end - start) / n
    return [(start + i * step, start + i * step + timedelta(minutes=minutes)) for i in range(n)]


class TestIndex(unittest.TestCase):
    def test_parts(self):
        r = sx.strain(dt(10), 0.2, 0.0, 5, [], None)
        self.assertEqual(set(r['c']), set(sx.WEIGHTS) | {'accumulated', 'sleepiness', 'now', 'fatigue'})
        self.assertAlmostEqual(sum(sx.WEIGHTS.values()), 1.0)

    def test_nothing_done_nobody_waiting_is_zero_at_any_hour(self):
        self.assertEqual(sx.strain(dt(4), 0.0, 0.0, None, [], None)['index'], 0)
        self.assertEqual(sx.strain(dt(10), 0.0, 0.0, None, [], None)['index'], 0)

    def test_owner_04h_after_a_long_night_is_high_even_with_a_short_queue(self):
        work = night(45)
        idle = sx.strain(dt(4), 0.0, 0.0, None, [], None, busy=work)
        short_q = sx.strain(dt(4), 0.5, 2.0, 20, [], None, busy=work)
        self.assertGreaterEqual(idle['c']['accumulated'], 80)
        self.assertGreaterEqual(short_q['index'], 75)
        self.assertGreater(short_q['index'], idle['index'])
        # the same night's work, read at 18:00 of a rested day: far lower
        day = [(s + timedelta(hours=14), e + timedelta(hours=14)) for s, e in night(15, end=dt(18, day=10))]
        self.assertLess(sx.strain(dt(18), 0.5, 2.0, 20, [], None, busy=day)['index'], short_q['index'])

    def test_a_break_does_not_reset_the_strain(self):
        work = night(45, end=dt(3, 30))
        self.assertGreaterEqual(sx.strain(dt(4), 0.0, 0.0, None, [], None, busy=work)['index'], 60)

    def test_combination(self):
        r = sx.strain(dt(10), 1.0, 3.0, 45, [], None)
        self.assertEqual(r['c']['fatigue'], 0)
        self.assertEqual(r['index'], round(100 * (sx.WEIGHTS['load'] + sx.WEIGHTS['pressure'])))

    def test_rushing_needs_short_exams_and_idle_while_waiting(self):
        short = [(dt(9, 10 + 15 * i), dt(9, 14 + 15 * i)) for i in range(3)]   # 4 min vs a median of 12
        a = sx.strain(dt(10), 0.5, 2.0, 20, short, 12.0, idle_waiting=0.25)
        b = sx.strain(dt(10), 0.5, 2.0, 20, short, 12.0, idle_waiting=0.0)    # fast and flowing
        c = sx.strain(dt(10), 0.5, 2.0, 20, [], 12.0, idle_waiting=0.25)      # idle, no short exams
        self.assertEqual(a['c']['rushing'], 100)
        self.assertEqual(b['c']['rushing'], 0)
        self.assertEqual(c['c']['rushing'], 0)


if __name__ == '__main__':
    unittest.main()
