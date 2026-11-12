#!/usr/bin/env python3
"""strain.py: the relative strain index (no server)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from datetime import datetime, timedelta

import strain as sx
from strain import Moment


def dt(h, m=0, day=11):   # 2026-11-11 is a Wednesday
    return datetime(2026, 11, day, h, m)


def spread(n, start, end, minutes=12):
    """n exams of `minutes`, evenly from start to end."""
    step = (end - start) / n
    return [(start + i * step, start + i * step + timedelta(minutes=minutes)) for i in range(n)]


ON = dt(8, day=10)   # the duty block that holds Wednesday 04:00 began Tuesday 08:00


class TestClock(unittest.TestCase):
    def test_circadian_deepest_at_night(self):
        self.assertEqual(sx.circadian(dt(4)), 1.0)
        self.assertGreater(sx.circadian(dt(3)), sx.circadian(dt(10)))
        self.assertGreater(sx.circadian(dt(14, 30)), sx.circadian(dt(11)))   # after-lunch dip
        self.assertAlmostEqual(sx.circadian(dt(23, 59)), sx.circadian(dt(0)), places=1)

    def test_duty_runs_08_to_08_every_day(self):
        self.assertEqual(sx.duty_start(dt(10)), dt(8))
        self.assertEqual(sx.duty_start(dt(20)), dt(8))                  # on call: since the morning
        self.assertEqual(sx.duty_start(dt(3)), dt(8, day=10))
        self.assertEqual(sx.duty_start(dt(20, day=14)), dt(8, day=14))  # Saturday
        self.assertEqual(sx.duty_hours(dt(4)), 20.0)


class TestAccumulated(unittest.TestCase):
    def test_work_adds_up_and_short_gaps_are_not_rest(self):
        # 3 h of 12-min exams with 8-min gaps: 1.8 h of work, nothing lost
        busy = [(dt(9, 0) + timedelta(minutes=20 * i), dt(9, 12) + timedelta(minutes=20 * i)) for i in range(9)]
        self.assertAlmostEqual(sx.accumulated_hours(busy, dt(12)), 1.8, places=6)
        # a 29-minute pause after it: still nothing lost
        self.assertAlmostEqual(sx.accumulated_hours(busy, dt(12, 9)), 1.8, places=6)

    def test_rest_of_30_min_or_more_decays_for_its_whole_length(self):
        busy = [(dt(9), dt(11))]
        h = sx.ACCUM_HALF_LIFE_H
        self.assertAlmostEqual(sx.accumulated_hours(busy, dt(11, 30)), 2 * 2 ** (-0.5 / h), places=6)
        self.assertAlmostEqual(sx.accumulated_hours(busy, dt(19)), 1.0, places=6)          # 8 h: half
        # a rest between two blocks decays only what came before it
        two = [(dt(9), dt(10)), (dt(18), dt(19))]
        self.assertAlmostEqual(sx.accumulated_hours(two, dt(19)), 1.5, places=6)

    def test_the_junior_s_work_adds_up_and_the_senior_s_gaps_are_rest(self):
        h = sx.ACCUM_HALF_LIFE_H
        senior = [(dt(20), dt(22))]
        junior = [(dt(22), dt(23))]
        work = senior + junior
        # at 00:00 the senior has rested 2 h: their 2 h decayed by 2 h, the
        # junior's hour by the hour of rest since it ended
        expect = 2 * 2 ** (-2 / h) + 1 * 2 ** (-1 / h)
        self.assertAlmostEqual(sx.accumulated_hours(work, dt(0, day=12), own=senior), expect, places=6)
        # alone (own = all the work): only the hour after 23:00 is rest
        self.assertAlmostEqual(sx.accumulated_hours(work, dt(0, day=12)), 3 * 2 ** (-1 / h), places=6)
        # before the senior's first exam nothing is rest: the team's work stands for their other duties
        self.assertAlmostEqual(sx.accumulated_hours([(dt(15), dt(17))], dt(19, 30), own=[(dt(19), dt(19, 30))]),
                               2.0, places=6)

    def test_the_block_starts_at_08(self):
        self.assertEqual(sx.accumulated_hours([(dt(6), dt(7, 30))], dt(9)), 0.0)
        self.assertAlmostEqual(sx.accumulated_hours([(dt(7), dt(9))], dt(9)), 1.0, places=6)

    def test_merge(self):
        self.assertEqual(sx.merge([(dt(9), dt(10)), (dt(9, 30), dt(10, 30)), (dt(11), dt(12))]),
                         [(dt(9), dt(10, 30)), (dt(11), dt(12))])


class TestNow(unittest.TestCase):
    def test_shorter_compares_with_the_region(self):
        self.assertEqual(sx.shorter([0.5, 0.5]), 0.0)          # too few
        self.assertEqual(sx.shorter([0.5, 0.5, 0.5]), 1.0)     # half the usual
        self.assertEqual(sx.shorter([1.0, 1.1, 1.2]), 0.0)
        self.assertEqual(sx.shorter([0.75, 0.75, 0.75]), 0.5)

    def test_rushing_needs_short_exams_and_idle_while_waiting(self):
        short = [0.5, 0.5, 0.5]
        r = lambda rel, idle: sx.score(Moment(dt(10), relative=rel, idle_waiting=idle))['c']['rushing']
        self.assertEqual(r(short, 0.25), 100)
        self.assertEqual(r(short, 0.0), 0)        # fast and flowing: efficiency
        self.assertEqual(r([], 0.25), 0)          # idle alone: may be other work

    def test_pressure_takes_the_worst_of_count_mean_and_longest_wait(self):
        p = lambda **kw: sx.score(Moment(dt(10), **kw))['c']['pressure']
        self.assertEqual(p(queue=1.5), 50)
        self.assertEqual(p(wait=45), 100)
        self.assertEqual(p(oldest=45), 50)        # full at twice the wait reference
        self.assertEqual(sx.score(Moment(dt(10), queue=3), sx.Refs(queue=6, wait=90))['c']['pressure'], 50)


class TestBurst(unittest.TestCase):
    def test_a_burst_beyond_capacity(self):
        # 6 requests in 20 minutes, the room clears 2 in half an hour: 4 beyond, over 3 -> full
        arr = [dt(10, 3 * i) for i in range(6)]
        self.assertEqual(sx.burst(arr, dt(10, 20), 4.0), 1.0)
        # within capacity: nothing
        self.assertEqual(sx.burst(arr[:2], dt(10, 20), 4.0), 0.0)
        # 4 in the window, 2 cleared: 2 beyond, over 3
        self.assertAlmostEqual(sx.burst(arr[:4], dt(10, 20), 4.0), 2 / 3, places=6)

    def test_felt_for_an_hour_then_fading_by_two(self):
        arr = [dt(10, 3 * i) for i in range(6)]          # the window ends at 10:15
        self.assertEqual(sx.burst(arr, dt(11, 15), 4.0), 1.0)
        self.assertAlmostEqual(sx.burst(arr, dt(11, 45), 4.0), 0.5, places=6)
        self.assertEqual(sx.burst(arr, dt(12, 15), 4.0), 0.0)

    def test_spread_arrivals_are_no_burst(self):
        arr = [dt(8) + timedelta(minutes=15 * i) for i in range(12)]   # 4/h, steady
        self.assertEqual(sx.burst(arr, dt(11), 4.0), 0.0)

    def test_unknown_capacity_uses_the_default(self):
        arr = [dt(10, 3 * i) for i in range(6)]
        self.assertEqual(sx.burst(arr, dt(10, 20), None), sx.burst(arr, dt(10, 20), sx.CAPACITY_DEFAULT_H))


class TestIndex(unittest.TestCase):
    def test_parts_and_weights(self):
        r = sx.score(Moment(dt(10)))
        self.assertEqual(set(r['c']), set(sx.NOW_WEIGHTS) | {'accumulated', 'sleepiness', 'now', 'fatigue'})
        self.assertAlmostEqual(sum(sx.NOW_WEIGHTS.values()), 1.0)

    def test_nothing_done_nobody_waiting_is_zero_at_any_hour(self):
        self.assertEqual(sx.score(Moment(dt(4)))['index'], 0)
        self.assertEqual(sx.score(Moment(dt(10)))['index'], 0)

    def test_combination(self):
        r = sx.score(Moment(dt(10), rho=1.0, queue=3.0))
        self.assertEqual(r['c']['fatigue'], 0)
        self.assertEqual(r['index'], round(100 * (sx.NOW_WEIGHTS['load'] + sx.NOW_WEIGHTS['pressure'])))

    def test_owner_04h_after_45_exams_is_high_even_with_a_short_queue(self):
        work = spread(45, ON, dt(4))
        idle = sx.score(Moment(dt(4), busy=work))
        short_q = sx.score(Moment(dt(4), rho=0.5, queue=2.0, wait=20, busy=work))
        self.assertGreaterEqual(idle['index'], 70)
        self.assertGreaterEqual(short_q['index'], 80)
        self.assertGreater(short_q['index'], idle['index'])
        # the same work done by 18:00 reads lower: less sleepy
        day = spread(45, ON, dt(18, day=10))
        self.assertLess(sx.score(Moment(dt(18, day=10), rho=0.5, queue=2.0, wait=20, busy=day))['index'],
                        short_q['index'])

    def test_a_break_does_not_reset_the_strain(self):
        work = spread(45, ON, dt(3, 15))
        self.assertGreaterEqual(sx.score(Moment(dt(4), busy=work))['index'], 65)

    def test_accumulated_saturates_softly(self):
        half = [(dt(8), dt(10, 30))]
        self.assertEqual(sx.score(Moment(dt(10, 30), busy=half))['c']['accumulated'], 50)
        five = [(dt(8), dt(13))]
        self.assertEqual(sx.score(Moment(dt(13), busy=five))['c']['accumulated'], 75)


if __name__ == '__main__':
    unittest.main()
