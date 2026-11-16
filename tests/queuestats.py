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

    def test_exam_before_request_leaves_both_stages(self):
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '2026-11-11 09:00')],
                             {'1': datetime(2026, 11, 11, 11, 0)}, {})
        self.assertTrue(jobs[0]['inconsistent'])
        self.assertIsNone(jobs[0]['exam'])
        self.assertIsNone(jobs[0]['report'])

    def test_pacs_start_ends_the_wait_and_performed_starts_the_report(self):
        st = {'1': [{'start': '2026-11-11T10:20:00'}]}
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '2026-11-11 10:50')],
                             {'1': datetime(2026, 11, 11, 11, 30)}, {}, st)
        d = datetime
        self.assertEqual(jobs[0]['exam'], (d(2026, 11, 11, 10, 0), d(2026, 11, 11, 10, 20)))
        self.assertEqual(jobs[0]['report'], (d(2026, 11, 11, 10, 50), d(2026, 11, 11, 11, 30)))

    def test_pacs_start_alone_rescues_a_row_without_performed(self):
        st = {'1': [{'start': '2026-11-11T10:20:00'}]}
        jobs = qs.build_jobs([row('1', '2026-11-11 10:00', '', status='completed')], {}, {}, st)
        self.assertEqual(jobs[0]['exam'], (datetime(2026, 11, 11, 10, 0), datetime(2026, 11, 11, 10, 20)))

    def test_pick_study(self):
        t = datetime(2026, 11, 11, 10, 0)
        old = {'start': '2026-11-11T08:00:00'}          # before the request: another exam
        a = {'start': '2026-11-11T10:20:00'}
        b = {'start': '2026-11-11T13:00:00'}
        self.assertEqual(qs.pick_study([old, b, a], t), datetime(2026, 11, 11, 10, 20))
        self.assertEqual(qs.pick_study([a, b], t, datetime(2026, 11, 11, 13, 5)), datetime(2026, 11, 11, 13, 0))
        self.assertEqual(qs.pick_study([{'start': '2026-11-11T09:50:00'}], t), t)  # clamped
        self.assertIsNone(qs.pick_study([old], t))

    def _svc(self, spec):
        """spec: [(rid, req, start, report)] as 'HH:MM' on 2026-11-11."""
        d = lambda h: f'2026-11-11 {h}' if h else ''
        rows = [row(r, d(req)) for r, req, _, _ in spec]
        st = {r: [{'start': f'2026-11-11T{s}:00'}] for r, _, s, _ in spec}
        rep = {r: qs.parse_ts(d(rp)) for r, _, _, rp in spec if rp}
        return qs.service_samples(qs.build_jobs(rows, rep, {}, st))

    def test_service_ends_with_the_report(self):
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        # idle room (next request after the start): the report still ends the exam
        self.assertEqual(self._svc([('1', '10:00', '10:05', '10:20'), ('2', '11:00', '11:05', '11:30')]),
                         [(t(10, 5), t(10, 20)), (t(11, 5), t(11, 30))])

    def test_next_start_ends_a_late_report(self):
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        # exam 2 was waiting and started at 10:30 before exam 1 was reported
        # (10:50): exam 1 ended at 10:30; exam 2 (no report, nothing after) has none
        self.assertEqual(self._svc([('1', '10:00', '10:05', '10:50'), ('2', '10:02', '10:30', None)]),
                         [(t(10, 5), t(10, 30))])
        # the next request was not waiting: the gap holds idle time, no sample
        self.assertEqual(self._svc([('1', '10:00', '10:05', '10:50'), ('2', '10:20', '10:30', None)]), [])

    def test_no_report_no_next_exam_is_no_sample(self):
        self.assertEqual(self._svc([('1', '10:00', '10:05', None)]), [])
        # nor an "exam" of 3 h
        self.assertEqual(self._svc([('1', '10:00', '10:05', '13:05')]), [])

    def test_late_report_past_the_cap_is_no_sample(self):
        # call to written report is one exam; 75 min holds idle time
        self.assertEqual(self._svc([('1', '10:00', '10:05', '11:20')]), [])
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        self.assertEqual(self._svc([('1', '10:00', '10:05', '10:55')]), [(t(10, 5), t(10, 55))])

    def test_two_requests_one_study_are_one_patient(self):
        rows = [row('1', '2026-11-11 10:00'), row('2', '2026-11-11 10:01')]
        same = [{'uid': 'a', 'start': '2026-11-11T10:20:00'}]
        rep = {'1': datetime(2026, 11, 11, 10, 40), '2': datetime(2026, 11, 11, 10, 40)}
        jobs = qs.build_jobs(rows, rep, {}, {'1': same, '2': same})
        first, second = sorted(jobs, key=lambda j: j['id'])
        self.assertFalse(first['merged'])
        self.assertTrue(second['merged'])
        self.assertIsNone(second['exam'])
        self.assertIsNone(second['report'])
        out = qs.compute(rows, rep, {}, AS_OF, pacs_studies={'1': same, '2': same})
        self.assertEqual(out['coverage']['merged'], 1)
        self.assertEqual(out['coverage']['pacs_start'], {'known': 1, 'of': 1})

    def test_work_intervals_keep_every_exam_done(self):
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        rows = [row('1', '2026-11-11 20:00', performed='2026-11-11 20:20'),   # no PACS start, no report
                row('2', '2026-11-11 20:30'),                                 # no PACS start, a report
                row('3', '2026-11-11 21:00'), row('4', '2026-11-11 21:01')]   # started, no end measured
        st = {'3': [{'uid': 'c', 'start': '2026-11-11T21:05:00'}], '4': [{'uid': 'd', 'start': '2026-11-11T21:09:00'}]}
        jobs = qs.build_jobs(rows, {'2': t(20, 50)}, {}, st)
        work = {j['id']: iv for j, iv in qs.work_intervals(jobs, [], timedelta(minutes=8))}
        self.assertEqual(work['1'], (t(20, 12), t(20, 20)))
        self.assertEqual(work['2'], (t(20, 42), t(20, 50)))
        self.assertEqual(work['3'], (t(21, 5), t(21, 9)))          # cut at the next start
        self.assertEqual(work['4'], (t(21, 9), t(21, 17)))

    def test_senior_is_who_reads_most_between_20_and_02(self):
        t = lambda d, h, m=0: datetime(2026, 11, d, h, m)
        mk = lambda rid, rep, who: {'id': rid, 'validator': who, 't_rep': rep}
        # Wednesday: the junior reads most of the evening and the early morning,
        # the senior takes 20:00-02:00
        jobs = [mk('1', t(11, 15), 'jr'), mk('2', t(11, 16), 'jr'), mk('3', t(11, 17), 'jr'),
                mk('4', t(11, 21), 'sr'), mk('5', t(11, 23), 'sr'), mk('6', t(12, 1), 'jr'),
                mk('7', t(12, 4), 'jr'), mk('8', t(12, 5), 'jr')]
        self.assertEqual(qs.on_call_radiologist(jobs, t(11, 8), t(12, 8)), 'sr')
        # at 18:00 the busy hours have not come: the most since 14:00
        self.assertEqual(qs.on_call_radiologist(jobs, t(11, 8), t(11, 18)), 'jr')
        self.assertIsNone(qs.on_call_radiologist(jobs, t(11, 8), t(11, 12)))   # weekday morning
        self.assertEqual(qs.on_call_from(t(11, 8)), t(11, 14))
        self.assertEqual(qs.on_call_from(t(14, 9)), t(14, 9))                   # Saturday
        self.assertEqual(qs.norm_name('  Bo   POP '), 'bo pop')

    def test_team_work_accumulates_and_the_senior_s_gaps_are_rest(self):
        rows, st, rep, who = [], {}, {}, {}
        base = datetime(2026, 11, 11, 8, 0)
        for i in range(40):   # an exam every 30 min from 08:00, 10 min each
            rid, req = str(i), base + timedelta(minutes=30 * i)
            rows.append(row(rid, req.strftime('%Y-%m-%d %H:%M')))
            st[rid] = [{'uid': f'u{i}', 'start': (req + timedelta(minutes=2)).isoformat()}]
            rep[rid] = req + timedelta(minutes=12)
            # the morning's day staff, then on call: the senior every other exam, the junior between
            who[rid] = 'Day Doc' if i < 12 else ('Senior Doc' if i % 2 else 'Junior Doc')
        as_of = datetime(2026, 11, 12, 4, 0)
        team = qs.compute(rows, rep, {}, as_of, hours=20, pacs_studies=st, validators=who)
        alone = qs.compute(rows, rep, {}, as_of, hours=20, pacs_studies=st)   # no validators: one radiologist
        a = lambda out: out['series'][-1]['strain_c']['accumulated']
        # the same work, but the senior rests 50 min between their exams: lower than alone
        self.assertLess(a(team), a(alone))
        self.assertGreater(a(team), 0)
        self.assertEqual(team['coverage']['on_call'],
                         [{'block': '2026-11-11T08:00', 'known': True, 'team_exams': 28,
                           'senior_exams': 14, 'radiologists': 2}])
        # the morning before 14:00 is the day staff's, not the on-call team's
        noon = [p for p in team['series'] if p['t'] == '2026-11-11T13:00'][0]
        self.assertEqual(noon['strain_c']['accumulated'], 0)
        self.assertNotIn('doc', str(team).casefold())   # no name leaves compute()

    def test_relative_lengths_by_region(self):
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        jobs, samples, regions = [], [], {}
        # abdomen exams take 20 min, hips 10: a 10-min hip is usual, a 10-min abdomen is half
        for i, (reg, mins) in enumerate([('abdomen', 20)] * 3 + [('hip', 10)] * 3 + [('abdomen', 10), ('hip', 10)]):
            start = t(8, 0) + timedelta(minutes=30 * i)
            jobs.append({'id': str(i), 't_start': start})
            samples.append((start, start + timedelta(minutes=mins)))
            regions[str(i)] = [reg]
        rel = dict((iv[0], r) for iv, r in qs.relative_lengths(samples, jobs, regions))
        self.assertEqual(rel[jobs[6]['t_start']], 0.5)
        self.assertEqual(rel[jobs[7]['t_start']], 1.0)
        self.assertEqual(qs.region_key(['pelvis', 'abdomen', 'unknown']), 'abdomen+pelvis')

    def test_oldest_wait(self):
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        ivs = [(t(9, 0), t(9, 50)), (t(9, 30), None, timedelta(hours=2)), (t(8, 0), t(8, 30))]
        self.assertEqual(qs.oldest_wait(ivs, t(9, 40)), 40.0)
        self.assertEqual(qs.oldest_wait(ivs, t(10, 0)), 30.0)
        self.assertIsNone(qs.oldest_wait(ivs, t(12, 0)))

    def test_idle_while_waiting_leaves_out_the_call(self):
        t = lambda h, m: datetime(2026, 11, 11, h, m)
        busy = [(t(9, 0), t(9, 20)), (t(9, 40), t(10, 0))]
        waiting = [(t(9, 10), t(9, 40))]             # someone waited through the gap
        # the gap 9:20-9:40, less 5 min of calling: 15 min of the hour
        self.assertEqual(qs.idle_while_waiting(waiting, busy, t(9, 0), t(10, 0)), 0.25)
        self.assertEqual(qs.idle_while_waiting([], busy, t(9, 0), t(10, 0)), 0.0)
        # a 4-minute gap is all calling
        busy2 = [(t(9, 0), t(9, 20)), (t(9, 24), t(10, 0))]
        self.assertEqual(qs.idle_while_waiting(waiting, busy2, t(9, 0), t(10, 0)), 0.0)

    def test_burst_reaches_the_series(self):
        rows = [row(str(i), f'2026-11-11 10:{3 * i:02d}', status='active') for i in range(6)]
        out = qs.compute(rows, {}, {}, datetime(2026, 11, 11, 12, 0), hours=4)
        at = {p['t']: p['strain_c']['burst'] for p in out['series']}
        self.assertEqual(at['2026-11-11T09:50'], 0)
        self.assertEqual(at['2026-11-11T10:20'], 100)
        self.assertEqual(at['2026-11-11T11:10'], 100)     # still felt an hour on

    def test_measured_rho_and_occupancy(self):
        base = datetime(2026, 11, 11, 6, 0)
        rows, st, rep = [], {}, {}
        for i in range(8):   # an exam every hour, 20 min from start to report
            rid, req = str(i), base + timedelta(hours=i)
            rows.append(row(rid, req.strftime('%Y-%m-%d %H:%M')))
            st[rid] = [{'start': (req + timedelta(minutes=5)).isoformat()}]
            rep[rid] = req + timedelta(minutes=25)
        out = qs.compute(rows, rep, {}, datetime(2026, 11, 11, 14, 0), hours=12, pacs_studies=st)
        svc = out['current']['service']
        self.assertEqual(svc['mean_span'], 20.0)
        self.assertEqual(svc['mu'], 3.0)
        self.assertEqual(svc['rho'], round(out['current']['exam']['lam'] / 3.0, 2))
        self.assertEqual(out['coverage']['pacs_start'], {'known': 8, 'of': 8})
        # every series point carries rho = lam / (the measured mu)
        p = next(p for p in out['series'] if p['lam'])
        self.assertEqual(p['rho'], round(p['lam'] / 3.0, 2))


class TestOnCallShift(unittest.TestCase):
    """The whole shift: reads of every modality, told by who validated them."""

    T = staticmethod(lambda d, h, m=0: datetime(2026, 11, d, h, m))   # 11 Nov 2026 is a Wednesday

    @staticmethod
    def read(mod, perf, rep, who, upu=True, n=1, left=True, rid='r'):
        return {'id': rid, 'modality': mod, 'upu': upu, 'left': left, 't_req': perf, 't_perf': perf,
                't_rep': rep, 'validator': who, 'n': n, 'read': None}

    def test_team_needs_five_reports_or_one_after_the_handover(self):
        t, ev = self.T, lambda rep, who: {'validator': who, 't_rep': rep}
        # the day staff's last reports at 14:00-14:10, then two on call
        events = [ev(t(11, 14, 5 * i), 'day') for i in range(3)]
        events += [ev(t(11, 15, 10 * i), 'sr') for i in range(5)] + [ev(t(11, 20, 10 * i), 'jr') for i in range(6)]
        self.assertEqual(qs.on_call_team(events, t(11, 8), t(12, 8)), {'sr', 'jr'})
        # 14:20: nobody past the grace yet -> nobody; 15:25: the first reports after it
        self.assertEqual(qs.on_call_team(events, t(11, 8), t(11, 14, 20)), set())
        self.assertEqual(qs.on_call_team(events, t(11, 8), t(11, 15, 25)), {'sr'})
        # alone on call
        self.assertEqual(qs.on_call_team(events[:8], t(11, 8), t(12, 8)), {'sr'})
        # the morning is not on call on a weekday
        self.assertEqual(qs.on_call_team([ev(t(11, 9, i), 'day') for i in range(9)], t(11, 8), t(12, 8)), set())

    def test_senior_counts_every_modality_and_only_the_team(self):
        t, ev = self.T, lambda rep, who: {'validator': who, 't_rep': rep}
        events = [ev(t(11, 21, i), 'sr') for i in range(3)] + [ev(t(11, 22, i), 'jr') for i in range(2)]
        events += [ev(t(11, 23, i), 'guest') for i in range(6)]
        self.assertEqual(qs.on_call_radiologist(events, t(11, 8), t(12, 8), {'sr', 'jr'}), 'sr')
        self.assertEqual(qs.on_call_radiologist(events, t(11, 8), t(12, 8)), 'guest')

    def test_build_reads_keeps_what_is_not_in_the_exam_queue(self):
        rows = [row('1', '2026-11-11 20:00', '2026-11-11 20:10'),                                   # UPU ultrasound: the queue
                row('2', '2026-11-11 20:00', '2026-11-11 20:10', modality='radio'),
                row('3', '2026-11-11 20:00', '2026-11-11 20:10', modality='ct', section='ATI'),
                row('4', '2026-11-11 20:00', '2026-11-11 20:10', section='ATI'),                    # ward ultrasound
                row('5', '2026-11-11 20:00', '2026-11-11 20:10', modality='radio', status='revoked'),
                row('6', '2026-11-11 20:00', '2026-11-11 19:00', modality='radio'),                 # performed before asked
                row('7', '2026-11-11 20:00', '2026-11-11 20:10', modality='rads')]
        reads = qs.build_reads(rows, {'2': self.T(11, 20, 30)}, {'2': ' Bo  POP '}, {'2': 2})
        self.assertEqual([r['id'] for r in reads], ['2', '3', '4', '6'])
        self.assertEqual((reads[0]['validator'], reads[0]['n'], reads[0]['upu']), ('bo pop', 2, True))
        self.assertFalse(reads[1]['upu'])
        self.assertIsNone(reads[3]['t_perf'])

    def test_read_work_is_the_gap_since_the_previous_report_capped(self):
        t, typ = self.T, timedelta(minutes=8)
        us = [({'validator': 'a'}, (t(11, 20, 0), t(11, 20, 9)))]            # their ultrasound, ends 20:09
        reads = [self.read('radio', t(11, 19, 0), t(11, 20, 10), 'a', rid='x1'),   # right after it: 1 min
                 self.read('radio', t(11, 19, 0), t(11, 20, 10), 'a', rid='x2'),   # same minute: READ_MIN
                 self.read('radio', t(11, 19, 0), t(11, 20, 30), 'a', rid='x3'),   # after a pause: 3 min
                 self.read('radio', t(11, 19, 0), t(11, 20, 50), 'a', n=2, rid='x4'),      # two studies: 6 min
                 self.read('ct', t(11, 21, 50), t(11, 22, 0), 'a', rid='c1'),      # images 10 min before: 10 min
                 self.read('ct', t(11, 22, 0), t(11, 23, 0), 'a', rid='c2'),       # 25 min cap
                 self.read('eco', t(11, 23, 0), t(11, 23, 40), 'a', upu=False, rid='w1'),  # ward US: the typical exam
                 self.read('radio', t(11, 20, 0), t(11, 20, 10), 'b', rid='y1'),   # another radiologist: own line
                 self.read('radio', t(11, 20, 0), None, 'a', rid='open'),
                 self.read('radio', t(11, 20, 0), t(11, 20, 5), None, rid='anon')]
        out = {rd['id']: (e - s) for rd, (s, e) in qs.read_work(reads, us, typ)}
        m = lambda n: timedelta(minutes=n)
        self.assertEqual(out, {'x1': m(1), 'x2': m(1), 'x3': m(3), 'x4': m(6), 'c1': m(10), 'c2': m(25),
                               'w1': m(8), 'y1': m(3)})

    def test_reading_queue_is_the_upu_s_and_what_the_team_validated(self):
        t = self.T
        team = lambda block: {'sr'} if block == t(11, 8) else set()
        reads = [self.read('radio', t(11, 20, 0), t(11, 20, 30), 'sr', rid='upu'),
                 self.read('radio', t(11, 20, 0), None, None, left=False, rid='waiting'),
                 self.read('radio', t(11, 20, 0), None, None, left=True, rid='uncached'),
                 self.read('ct', t(11, 12, 0), t(11, 21, 0), 'sr', upu=False, rid='ward'),      # done at noon
                 self.read('ct', t(11, 22, 0), t(12, 9, 0), 'day', upu=False, rid='morning'),   # left for the day staff
                 self.read('ct', t(11, 22, 0), t(11, 23, 0), 'other', upu=False, rid='guest'),
                 self.read('radio', None, t(11, 21, 0), 'sr', rid='noperf')]
        qs.reading_queue(reads, team)
        got = {rd['id']: rd['read'] for rd in reads}
        self.assertEqual(got['upu'], (t(11, 20, 0), t(11, 20, 30)))
        self.assertEqual(got['waiting'], (t(11, 20, 0), None))
        self.assertEqual(got['ward'], (t(11, 14, 0), t(11, 21, 0)))   # from the handover at the earliest
        for rid in ('uncached', 'morning', 'guest', 'noperf'):
            self.assertIsNone(got[rid], rid)

    def shift(self, with_reads=True, **kw):
        """A Wednesday on call, one radiologist: an ultrasound every 30 min
        from 14:00 to 02:00 and, with_reads, two X-rays after each plus a CT
        every 3 hours; a ward CT left for the morning."""
        rows, st, rep, who = [], {}, {}, {}
        f = lambda x: x.strftime('%Y-%m-%d %H:%M')
        base = datetime(2026, 11, 11, 14, 0)
        for i in range(24):
            rid, req = f'u{i}', base + timedelta(minutes=30 * i)
            rows.append(row(rid, f(req)))
            st[rid] = [{'uid': rid, 'start': (req + timedelta(minutes=2)).isoformat()}]
            rep[rid], who[rid] = req + timedelta(minutes=10), 'Solo Doc'
            if not with_reads:
                continue
            for k in (0, 1):
                xid = f'x{i}{k}'
                rows.append(row(xid, f(req), f(req + timedelta(minutes=5)), modality='radio'))
                rep[xid], who[xid] = req + timedelta(minutes=12 + 2 * k), 'Solo Doc'
            if i % 6 == 0:
                cid = f'c{i}'
                rows.append(row(cid, f(req), f(req + timedelta(minutes=1)), modality='ct', section='ATI'))
                rep[cid], who[cid] = req + timedelta(minutes=29), 'Solo Doc'
        rows.append(row('late', '2026-11-11 23:00', '2026-11-11 23:30', modality='ct', section='ATI'))
        rep['late'], who['late'] = datetime(2026, 11, 12, 9, 30), 'Day Doc'
        return qs.compute(rows, rep, {}, datetime(2026, 11, 12, 8, 0), hours=24, pacs_studies=st,
                          validators=who, **kw)

    def test_shift_counts_every_modality_and_reads_harder_with_them(self):
        out, bare = self.shift(), self.shift(with_reads=False)
        sh = out['shifts']
        self.assertEqual(len(sh), 1)
        self.assertEqual(sh[0]['reports'], {'us': 24, 'xr': 48, 'ct': 4, 'rf': 0, 'mr': 0})
        self.assertEqual((sh[0]['ward'], sh[0]['radiologists'], sh[0]['complete'], sh[0]['known']), (4, 1, True, True))
        self.assertEqual((sh[0]['from'], sh[0]['to']), ('2026-11-11T14:00', '2026-11-12T08:00'))
        self.assertEqual(bare['shifts'][0]['reports'], {'us': 24, 'xr': 0, 'ct': 0, 'rf': 0, 'mr': 0})
        at = lambda o, hhmm: [p for p in o['series'] if p['t'].endswith(hhmm)][0]
        # the same ultrasounds with X-rays and CT on top: more accumulated, more load, a higher index
        self.assertGreater(at(out, '02:00')['strain_c']['accumulated'], at(bare, '02:00')['strain_c']['accumulated'])
        self.assertGreater(at(out, '20:00')['rho'], at(bare, '20:00')['rho'])
        self.assertGreater(sh[0]['mean'], bare['shifts'][0]['mean'])
        self.assertGreaterEqual(sh[0]['peak'], sh[0]['mean'])
        # the X-rays wait to be read; the ward CT left for the morning never does
        self.assertGreater(at(out, '20:00')['read_L'], 0)
        self.assertEqual(at(out, '06:00')['read_L'], 0)
        self.assertEqual(out['current']['reading']['span']['n_in'], 52)
        self.assertEqual(out['coverage']['read_times'], {'known': 53, 'of': 53})
        self.assertNotIn('doc', str(out).casefold())   # no name leaves compute()

    def test_a_read_never_reported_did_not_wait(self):
        rows = [row(f'x{i}', f'2026-11-11 1{i}:00', f'2026-11-11 1{i}:10', modality='radio') for i in range(6)]
        rep = {f'x{i}': datetime(2026, 11, 11, 10 + i, 30) for i in range(6)}
        rows.append(row('never', '2026-11-11 17:00', '2026-11-11 17:10', status='active', modality='radio'))
        at = lambda o, hhmm: [p for p in o['series'] if p['t'].endswith(hhmm)][0]
        live = qs.compute(rows, rep, {}, datetime(2026, 11, 11, 18, 0), hours=12)
        self.assertGreater(at(live, '18:00')['read_L'], 0)          # seen live, it is waiting
        self.assertEqual(live['current']['reading']['now'], 1)
        later = qs.compute(rows, rep, {}, datetime(2026, 11, 11, 18, 0), hours=12, now=datetime(2026, 11, 13, 9, 0))
        self.assertEqual(at(later, '18:00')['read_L'], 0)           # seen two days on, it never was
        self.assertEqual(later['coverage']['stale']['read'], 1)


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

    def test_service_rate_skips_windows_across_a_shift_change(self):
        # Wednesday: 1/h all day, but 6 just before 08:00 and 6 just after:
        # a window holding both crosses the handover and does not count
        a = datetime(2026, 11, 11, 0, 0)
        ivs = [(a, a + timedelta(hours=h, minutes=30)) for h in range(24) if h not in (7, 8)]
        ivs += [(a, a + timedelta(hours=7, minutes=31 + 4 * i)) for i in range(6)]
        ivs += [(a, a + timedelta(hours=8, minutes=1 + 4 * i)) for i in range(6)]
        mu = qs.service_rate(ivs, a, a + timedelta(hours=24), q=1.0)
        self.assertEqual(mu, 6.0)   # either side of 08:00, never 12

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
        self.assertEqual(out['scope'], {'modality': 'eco', 'section': 'UPU',
                                        'work': ['ct', 'eco', 'fluoro', 'irm', 'radio']})
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

    def test_stale_row_not_counted_as_a_job_of_the_span(self):
        done = [row(str(i), f'2026-11-11 0{i}:00', f'2026-11-11 0{i}:30') for i in range(1, 6)]
        stale = row('9', '2026-11-10 01:00', '', status='draft')  # open ~35 h: long past its cap
        out = qs.compute(done + [stale], {}, {}, AS_OF, hours=12)
        self.assertEqual(out['coverage']['jobs'], 5)

    def test_inconsistent_counted_in_coverage(self):
        out = qs.compute([row('1', '2026-11-11 10:00', '2026-11-11 09:00')], {}, {}, AS_OF, hours=12)
        self.assertEqual(out['coverage']['inconsistent'], 1)

    def test_explicit_span_start_is_reported(self):
        out = qs.compute([], {}, {}, datetime(2026, 11, 11, 8, 0), hours=24)
        self.assertEqual(out['span_start'], '2026-11-10T08:00')
        self.assertEqual(qs.parse_anchor('2026-11-11T08:00', datetime(2026, 11, 12, 12, 0)), datetime(2026, 11, 11, 8, 0))

    def test_truncated_flag(self):
        self.assertTrue(qs.compute([], {}, {}, AS_OF, truncated=True)['truncated'])


if __name__ == '__main__':
    unittest.main()
