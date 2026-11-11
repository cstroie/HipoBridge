#!/usr/bin/env python3
"""queuestats.py: queue-theory metrics over synthetic schedule rows
(no server, no Hipocrate)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from datetime import datetime, timedelta

import queuestats as qs


def row(rid, req, performed='', status='completed', modality='eco', section='UPU'):
    return {'request_id': rid, 'date_time': req, 'performed_at': performed,
            'status': status, 'modality': modality, 'section': section}


AS_OF = datetime(2026, 11, 11, 12, 0)


class TestParsing(unittest.TestCase):
    def test_midnight_performed_is_unknown(self):
        self.assertIsNone(qs.parse_performed('2026-11-11 00:00'))
        self.assertEqual(qs.parse_performed('2026-11-11 00:05'), datetime(2026, 11, 11, 0, 5))

    def test_anchor(self):
        now = datetime(2026, 11, 11, 14, 37, 12)
        self.assertEqual(qs.parse_anchor(None, now), datetime(2026, 11, 11, 14, 30))
        self.assertEqual(qs.parse_anchor('2026-11-10', now), datetime(2026, 11, 11, 0, 0))
        self.assertEqual(qs.parse_anchor('2026-11-12', now), datetime(2026, 11, 11, 14, 30))  # never future
        self.assertEqual(qs.parse_anchor('2026-11-11T09:15', now), datetime(2026, 11, 11, 9, 10))

    def test_latest_validation(self):
        studies = [{'validation_date': '2026-11-11T10:00:00'}, {'validation_date': '2026-11-11T11:30:00'},
                   {'validation_date': None}]
        self.assertEqual(qs.latest_validation(studies), datetime(2026, 11, 11, 11, 30))
        self.assertIsNone(qs.latest_validation([]))

    def test_fupu_arrival(self):
        self.assertEqual(qs.fupu_arrival('11/11/2026', '08:04'), datetime(2026, 11, 11, 8, 4))
        self.assertIsNone(qs.fupu_arrival('11/11/2026', None))

    def test_fupu_box_time(self):
        from bs4 import BeautifulSoup
        from hippoclient import HippoClientFUPU
        html = ('<input type="checkbox" checked> 10-Preluat de: <span class="AliniereDreapta">La ora: '
                '<span class="boxBd">0</span><input type="text" value="08:04" readonly></span><br>'
                '<input type="text" value="X"><input type="checkbox" checked> 11-Ora prim consult medical: '
                '<input type="text" value="00:00" readonly>')
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(HippoClientFUPU._box_time(soup, '10-Preluat de'), '08:04')
        self.assertIsNone(HippoClientFUPU._box_time(soup, '11-Ora prim consult'))
        self.assertIsNone(HippoClientFUPU._box_time(soup, '99-Missing'))

    def test_pick_presentation(self):
        t_req = datetime(2026, 11, 11, 10, 0)
        times = [datetime(2026, 11, 11, 8, 0), datetime(2026, 11, 11, 9, 30),
                 datetime(2026, 11, 11, 10, 30), datetime(2026, 11, 9, 9, 0)]
        self.assertEqual(qs.pick_presentation(times, t_req), datetime(2026, 11, 11, 9, 30))
        self.assertIsNone(qs.pick_presentation([datetime(2026, 11, 9, 9, 0)], t_req))


class TestJobs(unittest.TestCase):
    def test_excluded_rows(self):
        rows = [row('1', '2026-11-11 10:00', status='revoked'),
                row('2', '2026-11-11 10:00', status='entered-in-error'),
                row('3', '2026-11-11 10:00', modality='lab'),
                row('5', '2026-11-11 10:00', '2026-11-11 10:20', modality='radio'),  # UPU, not ultrasound
                row('6', '2026-11-11 10:00', '2026-11-11 10:20', section='PEDIATRIE'),  # ultrasound, not UPU
                row('4', '2026-11-11 10:00', '2026-11-11 10:20')]
        self.assertEqual([j['id'] for j in qs.build_jobs(rows, {}, {})], ['4'])

    def test_completed_without_times_leaves_no_trace(self):
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '', status='completed')], {}, {})
        self.assertIsNone(jobs[0]['exam'])
        self.assertIsNone(jobs[0]['report'])

    def test_completed_without_performed_uses_report_time(self):
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '', status='completed')],
                             {'1': datetime(2026, 11, 11, 11, 0)}, {})
        self.assertEqual(jobs[0]['exam'], (datetime(2026, 11, 11, 10, 0), datetime(2026, 11, 11, 11, 0)))

    def test_open_stages(self):
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '', status='draft'),
                              row('2', '2026-11-11 10:00', '2026-11-11 10:30', status='active')], {}, {})
        self.assertEqual(jobs[0]['exam'], (datetime(2026, 11, 11, 10, 0), None))
        self.assertIsNone(jobs[0]['report'])
        self.assertEqual(jobs[1]['report'], (datetime(2026, 11, 11, 10, 30), None))

    def test_stale_cache_does_not_mean_unreported(self):
        # completed, performed, no cached report time: report stage unknown, not open
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '2026-11-11 10:30')], {}, {})
        self.assertIsNone(jobs[0]['report'])


class TestStats(unittest.TestCase):
    def test_hand_computed_window(self):
        a, b = datetime(2026, 11, 11, 11, 0), AS_OF
        ivs = [(datetime(2026, 11, 11, 10, 30), datetime(2026, 11, 11, 11, 30)),  # 30 min inside, departs
               (datetime(2026, 11, 11, 11, 15), datetime(2026, 11, 11, 11, 45)),  # 30 min, arrives+departs
               (datetime(2026, 11, 11, 11, 30), None)]                            # 30 min open, arrives
        s = qs.stage_stats(ivs, a, b)
        self.assertEqual(s['lam'], 2.0)
        self.assertEqual(s['x'], 2.0)
        self.assertEqual(s['L'], 1.5)
        self.assertEqual(s['W'], 45.0)
        self.assertEqual(s['little'], 1.5)
        self.assertEqual(s['busy'], 1.0)

    def test_little_law_on_steady_stream(self):
        # one arrival every 6 min, each waits 18 min: lam 10/h, W 18 min, L 3
        start = datetime(2026, 11, 10, 0, 0)
        ivs = [(start + timedelta(minutes=6 * i), start + timedelta(minutes=6 * i + 18)) for i in range(600)]
        s = qs.stage_stats(ivs, datetime(2026, 11, 11, 0, 0), datetime(2026, 11, 11, 12, 0))
        self.assertAlmostEqual(s['L'], 3.0, places=2)
        self.assertAlmostEqual(s['little'], s['L'], places=1)

    def test_service_rate_is_demonstrated_capacity(self):
        # 2 exams/h for 10 h, one hour with 6, and a lone batch of 12 at once:
        # the 90th percentile of the rolling hourly departures, not the batch
        a = datetime(2026, 11, 11, 0, 0)
        ivs = [(a, a + timedelta(minutes=30 * i + 15)) for i in range(20)]           # 00:15..09:45
        ivs += [(a, a + timedelta(hours=10, minutes=10 * i + 5)) for i in range(6)]  # 10:05..10:55
        ivs += [(a, a + timedelta(hours=11, minutes=30))] * 12                        # batch at 11:30
        ivs += [(a, a + timedelta(hours=h, minutes=15)) for h in range(12, 24)]      # 1/h after
        mu = qs.service_rate(ivs, a, a + timedelta(hours=24))
        self.assertTrue(2.0 <= mu < 12.0, mu)
        self.assertIsNone(qs.service_rate([(a, None)], a, a + timedelta(hours=4)))

    def test_open_interval_capped(self):
        a = datetime(2026, 11, 9, 0, 0)
        ivs = [(a, None)]
        s = qs.stage_stats(ivs, datetime(2026, 11, 11, 11, 0), AS_OF)
        self.assertEqual(s['L'], 0.0)


class TestCompute(unittest.TestCase):
    def test_shape_and_warmup(self):
        rows = [row('1', '2026-11-10 10:00', '', status='draft'),  # waiting since before the span
                row('2', '2026-11-11 11:10', '2026-11-11 11:40'),
                row('3', '2026-11-11 11:20', '2026-11-11 11:50')]
        out = qs.compute(rows, {'3': datetime(2026, 11, 11, 11, 55)},
                         {'1': datetime(2026, 11, 10, 9, 0)}, AS_OF, hours=12)
        self.assertEqual(len(out['series']), 72)
        self.assertEqual(out['series'][-1]['t'], '2026-11-11T12:00')
        self.assertGreater(out['series'][0]['L'], 0)  # the warm-up job is in the first window
        self.assertEqual(out['scope'], {'modality': 'eco', 'section': 'UPU'})
        self.assertIn('rho', out['current']['exam'])
        self.assertEqual(out['coverage']['report_times'], {'known': 1, 'of': 2})
        self.assertEqual(out['coverage']['upu_arrivals'], {'known': 1, 'of': 3})
        self.assertFalse(out['truncated'])

    def test_stale_open_row_stops_at_its_modality_cap(self):
        # five exams done in 30 min: the cap is the 2 h floor, so a
        # request open for 5 h is stale and no longer in the queue
        done = [row(str(i), f'2026-11-11 0{i}:00', f'2026-11-11 0{i}:30') for i in range(1, 6)]
        stale = row('9', '2026-11-11 07:00', '', status='draft')
        fresh = row('8', '2026-11-11 11:30', '', status='draft')
        out = qs.compute(done + [stale, fresh], {}, {}, AS_OF, hours=12)
        self.assertEqual(out['open_caps_h']['exam:eco'], 2.0)
        self.assertEqual(out['coverage']['stale']['exam'], 1)
        self.assertEqual(out['current']['exam']['L'], 0.5)  # only the fresh one, half the hour
        self.assertLess(out['current']['span']['exam']['busy'], 1.0)

    def test_truncated_flag(self):
        self.assertTrue(qs.compute([], {}, {}, AS_OF, truncated=True)['truncated'])


if __name__ == '__main__':
    unittest.main()
