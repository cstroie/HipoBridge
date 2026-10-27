"""Offline tests of tools/upu_us_stats.py: shifts, intervals, statistics, report."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import upu_us_stats as u  # noqa: E402


def dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


class TestShiftOf(unittest.TestCase):
    # 2026-10-05 is a Monday
    def cls(self, s, holidays=frozenset()):
        c, d = u.shift_of(dt(s), holidays)
        return c, d.isoformat()

    def test_working_day_hours(self):
        self.assertEqual(self.cls("2026-10-05 08:00"), ("day", "2026-10-05"))
        self.assertEqual(self.cls("2026-10-05 13:59"), ("day", "2026-10-05"))

    def test_weeknight_boundaries(self):
        self.assertEqual(self.cls("2026-10-05 14:00"), ("weeknight", "2026-10-05"))
        self.assertEqual(self.cls("2026-10-06 07:59"), ("weeknight", "2026-10-05"))
        self.assertEqual(self.cls("2026-10-06 08:00"), ("day", "2026-10-06"))

    def test_friday_night_ends_saturday_morning(self):
        self.assertEqual(self.cls("2026-10-09 20:00"), ("weeknight", "2026-10-09"))
        self.assertEqual(self.cls("2026-10-10 07:59"), ("weeknight", "2026-10-09"))
        self.assertEqual(self.cls("2026-10-10 08:00"), ("weekend", "2026-10-10"))

    def test_weekend_runs_until_monday_08(self):
        self.assertEqual(self.cls("2026-10-11 23:00"), ("weekend", "2026-10-11"))
        self.assertEqual(self.cls("2026-10-12 07:59"), ("weekend", "2026-10-11"))
        self.assertEqual(self.cls("2026-10-12 08:00"), ("day", "2026-10-12"))

    def test_holiday_is_a_weekend(self):
        h = frozenset({date(2026, 10, 7)})
        self.assertEqual(self.cls("2026-10-07 15:00", h), ("weekend", "2026-10-07"))
        self.assertEqual(self.cls("2026-10-08 07:00", h), ("weekend", "2026-10-07"))

    def test_bounds(self):
        s, e = u.shift_bounds("weeknight", date(2026, 10, 5))
        self.assertEqual((s, e), (dt("2026-10-05 14:00"), dt("2026-10-06 08:00")))
        s, e = u.shift_bounds("weekend", date(2026, 10, 10))
        self.assertEqual((s, e), (dt("2026-10-10 08:00"), dt("2026-10-11 08:00")))


class TestParse(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(u.parse_dt("2026-10-05 14:05"), dt("2026-10-05 14:05"))
        self.assertEqual(u.parse_dt("2026-10-05T14:05:00"), dt("2026-10-05 14:05"))
        self.assertEqual(u.parse_dt("05/10/2026 14:05"), dt("2026-10-05 14:05"))
        self.assertEqual(u.parse_dt("2026-10-05T14:05:00+03:00"), dt("2026-10-05 14:05"))

    def test_empty(self):
        self.assertIsNone(u.parse_dt(""))
        self.assertIsNone(u.parse_dt(None))
        self.assertIsNone(u.parse_dt("not a date"))


class TestStats(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(u.percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(u.percentile([5], 95), 5)
        self.assertIsNone(u.percentile([], 50))

    def test_summarize(self):
        s = u.summarize([10, 20, 30])
        self.assertEqual((s["n"], s["median"], s["mean"], s["max"]), (3, 20, 20, 30))
        self.assertEqual(u.summarize([]), {"n": 0})

    def test_midranks_ties(self):
        self.assertEqual(u.midranks([3, 1, 3, 2]), [3.5, 1.0, 3.5, 2.0])

    def test_mann_whitney(self):
        low, high = list(range(1, 21)), list(range(21, 41))
        t = u.mann_whitney(high, low)
        self.assertEqual(t["prob_a_gt_b"], 1.0)
        self.assertLess(t["p"], 0.001)
        same = u.mann_whitney(list(range(20)), list(range(20)))
        self.assertAlmostEqual(same["prob_a_gt_b"], 0.5)
        self.assertGreater(same["p"], 0.9)
        self.assertIsNone(u.mann_whitney([1, 2], [3, 4, 5]))

    def test_spearman(self):
        self.assertAlmostEqual(u.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])["rho"], 1.0)
        self.assertAlmostEqual(u.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])["rho"], -1.0)
        self.assertIsNone(u.spearman([1, 1, 1, 1], [1, 2, 3, 4]))

    def test_dispersion(self):
        d = u.dispersion([4, 4, 4, 4])
        self.assertEqual(d["index"], 0)
        self.assertGreater(u.dispersion([0, 10, 0, 10])["index"], 1)

    def test_median_ci_is_repeatable(self):
        vals = list(range(1, 60))
        lo, hi = u.median_ci(vals)
        self.assertEqual((lo, hi), u.median_ci(vals))
        self.assertLess(lo, 30)
        self.assertGreater(hi, 30)
        self.assertIsNone(u.median_ci([1, 2]))


class TestIntervals(unittest.TestCase):
    def test_clean_drops_bad_values(self):
        ok, neg, big = u.clean([5, None, -3, u.MAX_MINUTES + 1, 0])
        self.assertEqual((ok, neg, big), ([5, 0], 1, 1))

    def test_minutes(self):
        self.assertEqual(u.minutes(dt("2026-10-05 14:00"), dt("2026-10-05 14:45")), 45)
        self.assertIsNone(u.minutes(None, dt("2026-10-05 14:45")))


class TestOutcome(unittest.TestCase):
    def rec(self, req, perf=None, sign=None, cancelled=False):
        return {"t_req": dt(req), "t_perf": perf and dt(perf), "t_sign": sign and dt(sign),
                "cancelled": cancelled}

    def test_outcomes(self):
        now = dt("2026-10-06 00:00")
        self.assertEqual(u.outcome(self.rec("2026-10-05 10:00", sign="2026-10-05 11:00"), now), "signed")
        self.assertEqual(u.outcome(self.rec("2026-10-05 10:00", "2026-10-05 10:30"), now), "performed_unsigned")
        self.assertEqual(u.outcome(self.rec("2026-10-05 10:00", cancelled=True), now), "cancelled")
        self.assertEqual(u.outcome(self.rec("2026-10-05 10:00"), now), "left")
        self.assertEqual(u.outcome(self.rec("2026-10-05 11:59"), now), "left")
        self.assertEqual(u.outcome(self.rec("2026-10-05 12:01"), now), "pending")

    def test_two_proportions(self):
        t = u.two_proportions(30, 100, 10, 100)
        self.assertLess(t["p"], 0.001)
        self.assertGreater(u.two_proportions(10, 100, 11, 100)["p"], 0.5)
        self.assertIsNone(u.two_proportions(0, 0, 1, 10))


class TestVisit(unittest.TestCase):
    def test_pres_time(self):
        self.assertEqual(u.pres_time("08/10/2026 20:06"), dt("2026-10-08 20:06"))
        self.assertIsNone(u.pres_time("26/12/2023"))
        self.assertIsNone(u.pres_time(None))

    def test_decision_kind(self):
        k = u.decision_kind
        self.assertEqual(k("Plecat fara aviz"), "left_unadvised")
        self.assertEqual(k("Plecat din UPU la domiciliu"), "home")
        self.assertEqual(k("Internare"), "admitted")
        self.assertEqual(k("Alta unitate sanitara"), "transfer")
        self.assertEqual(k(""), "unknown")

    def test_match_presentation(self):
        chain = [(dt("2026-10-08 20:06"), "new"), (dt("2023-12-26 18:28"), "old")]
        self.assertEqual(u.match_presentation(dt("2026-10-08 21:26"), chain)[1], "new")
        # arrival after the request: the older one is tried, and it is too old
        self.assertIsNone(u.match_presentation(dt("2026-10-08 19:00"), chain))
        # more than 48 h after arrival: no match
        self.assertIsNone(u.match_presentation(dt("2026-10-11 20:06"), chain))
        self.assertIsNone(u.match_presentation(dt("2026-10-08 21:26"), [(None, "x")]))

    def test_apply_visit(self):
        rec = u.new_record({"request_id": 1})
        u.apply_visit(rec, dt("2026-10-08 20:06"), {
            "presentation": {"triage": "Urgent", "triage_time": "08/10/2026 20:06",
                             "decision": "Internare"},
            "admission": {"date_time": "08/10/2026 23:00"}})
        self.assertEqual((rec["v_arrival"], rec["v_admission"], rec["v_triage"]),
                         ("2026-10-08 20:06", "2026-10-08 23:00", "Urgent"))
        self.assertTrue(rec["v_done"])


class TestVisitStats(unittest.TestCase):
    def test_visit_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = {}
            spec = [  # id, arrival, requested, signed, decision, admission
                ("1", "2026-10-05 14:00", "2026-10-05 14:40", "2026-10-05 15:30", "Internare", "2026-10-05 17:00"),
                ("2", "2026-10-05 15:00", "2026-10-05 15:20", "2026-10-05 16:00", "Plecat din UPU la domiciliu", ""),
                ("3", "2026-10-05 16:00", "2026-10-05 16:30", "2026-10-05 17:10", "Plecat fara aviz", ""),
                ("4", "2026-10-05 17:00", "2026-10-05 17:10", "", "Plecat fara aviz", ""),
                ("5", "2026-10-05 18:00", "2026-10-05 18:10", "2026-10-05 18:50", "", ""),
            ]
            for i, arr, req, sig, dec, adm in spec:
                rec = u.new_record({"request_id": i, "date_time": req, "status": "ended",
                                    "performed_at": req})
                rec.update(signed=sig, studied=True, n_studies=1, n_validated=1 if sig else 0)
                if dec:
                    rec.update(v_done=True, v_arrival=arr, v_triage_time=arr, v_triage="Urgent",
                               v_decision=dec, v_admission=adm)
                cache[i] = rec
            u.export_csv(tmp, cache)
            recs = u.load_requests(tmp, frozenset())
            ra = u.analyze_data(recs, date(2026, 10, 5), date(2026, 10, 6), as_of=dt("2026-10-07 12:00"))
            v = ra["visits"]
            self.assertEqual((v["matched"], v["total"]), (4, 5))
            self.assertEqual(v["kinds"], {"admitted": 1, "home": 1, "left_unadvised": 2})
            self.assertEqual(v["intervals"]["all"]["i_ar"]["median"], 25)
            a = v["admitted"]
            self.assertEqual((a["n"], a["complete"]), (1, 1))
            self.assertEqual(a["i_sa"]["median"], 90)           # signed 15:30 -> admitted 17:00
            self.assertAlmostEqual(a["shares"]["request_to_signed"], 50 / 180)
            lu = v["left_unadvised"]
            self.assertEqual(lu["n"], 2)
            self.assertEqual(lu["outcomes"], {"signed": 1, "performed_unsigned": 1})
            report = u.render(ra, {"ward": "UPU"})
            self.assertIn("left without notice", report)


class TestStudy(unittest.TestCase):
    def test_latest_validation_wins(self):
        rec = u.new_record({"request_id": 7, "date_time": "2026-10-05 14:00"})
        ok = u.apply_study(rec, {"status": "success", "studies": [
            {"validation_date": "2026-10-05T15:00:00", "validator": "Dr A"},
            {"validation_date": "2026-10-05T16:30:00", "validator": "Dr B"},
            {"validation_date": None, "validator": ""}]})
        self.assertTrue(ok)
        self.assertEqual((rec["signed"], rec["validator"]), ("2026-10-05 16:30", "Dr B"))
        self.assertEqual((rec["n_studies"], rec["n_validated"]), (3, 2))

    def test_failed_answer(self):
        rec = u.new_record({"request_id": 7})
        self.assertFalse(u.apply_study(rec, None))
        self.assertFalse(u.apply_study(rec, {"status": "error"}))
        self.assertFalse(rec["studied"])

    def test_needs_study(self):
        rec = u.new_record({"request_id": 1, "status": "completed"})
        self.assertTrue(u.needs_study(rec, resume=True))
        rec.update(studied=True, n_studies=1, n_validated=0)
        self.assertTrue(u.needs_study(rec, resume=False))
        self.assertFalse(u.needs_study(rec, resume=True))
        rec.update(n_validated=1)
        self.assertFalse(u.needs_study(rec, resume=False))
        cancelled = u.new_record({"request_id": 2, "status": "revoked"})
        self.assertFalse(u.needs_study(cancelled, resume=False))

    def test_ward_filter_is_exact(self):
        self.assertTrue(u.is_ward({"section": " upu "}, "UPU"))
        self.assertFalse(u.is_ward({"section": "UPU Pediatrie"}, "UPU"))


class TestEndToEnd(unittest.TestCase):
    """A small synthetic month through export, load, analysis and report."""

    def make(self, tmp):
        cache = {}
        spec = [  # id, requested, performed, signed, status, priority, signer
            ("1", "2026-10-05 09:00", "2026-10-05 09:20", "2026-10-05 10:00", "ended", "routine", "Dr X"),
            ("2", "2026-10-05 15:00", "2026-10-05 15:40", "2026-10-06 07:00", "ended", "urgent", "Dr Y"),
            ("3", "2026-10-06 03:00", "2026-10-06 03:10", "2026-10-06 09:00", "ended", "urgent", "Dr Y"),
            ("4", "2026-10-10 10:00", "2026-10-10 10:30", "", "active", "urgent", ""),
            ("5", "2026-10-11 22:00", "", "", "revoked", "routine", ""),
            ("6", "2026-10-12 06:00", "2026-10-12 05:00", "2026-10-12 12:00", "ended", "urgent", "Dr X"),
        ]
        for i, req, perf, sig, st, pr, v in spec:
            rec = u.new_record({"request_id": i, "date_time": req, "performed_at": perf,
                                "status": st, "priority": pr, "payment_type": "emergency"})
            rec.update(signed=sig, validator=v, studied=True,
                       n_studies=1, n_validated=1 if sig else 0)
            cache[i] = rec
        return u.export_csv(tmp, cache)

    def test_csv_has_no_raw_ids_or_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, n = self.make(tmp)
            self.assertEqual(n, 6)
            with open(path) as f:
                text = f.read()
            self.assertNotIn("Dr X", text)
            self.assertNotIn("Dr Y", text)
            self.assertNotIn(",1,2026", text.replace("\n", "\n,"))
            self.assertEqual(text.splitlines()[0], ",".join(u.CSV_FIELDS))

    def test_analysis_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make(tmp)
            recs = u.load_requests(tmp, frozenset())
            ra = u.analyze_data(recs, date(2026, 10, 1), date(2026, 10, 14), as_of=dt("2026-10-14 12:00"))
            self.assertEqual((ra["requests"], ra["cancelled"], ra["active"]), (6, 1, 6))
            self.assertEqual(sum(ra["by_class"].values()), 6)
            self.assertEqual(ra["by_class"], {"day": 1, "weeknight": 2, "weekend": 3})
            self.assertEqual(sum(ra["by_hour"]), 6)
            self.assertEqual(sum(ra["daily"].values()), 6)
            rp = ra["intervals"]["all"]["i_rp"]
            self.assertEqual(rp["missing"], 0)
            self.assertEqual(rp["negative"], 1)       # request 6 was performed before it was requested
            self.assertEqual(rp["n"], 4)
            rs = ra["intervals"]["all"]["i_rs"]
            self.assertEqual((rs["n"], rs["missing"]), (4, 1))
            self.assertEqual(ra["closing"]["weeknight"], {"n": 2, "signed_by_end": 1, "signed_ever": 2})
            self.assertEqual(len(ra["signers"]), 2)
            self.assertEqual(ra["visits"]["matched"], 0)
            oc = ra["outcomes"]["counts"]      # as of 2026-10-14 nothing is pending
            self.assertEqual((oc["signed"], oc["performed_unsigned"], oc["cancelled"]), (4, 1, 1))
            self.assertEqual(ra["outcomes"]["left"], 1)
            report = u.render(ra, {"ward": "UPU"})
            self.assertIn("# UPU ultrasound requests, 2026-10-01 to 2026-10-14", report)
            self.assertNotIn("Dr X", report)

    def test_partial_shifts_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make(tmp)
            recs = u.load_requests(tmp, frozenset())
            ra = u.analyze_data(recs, date(2026, 10, 5), date(2026, 10, 12))
            # the night of 2026-10-12 ends after the period; the one of 10-04 starts before it
            self.assertIn("2026-10-12 weeknight", ra["shifts"]["partial"])
            self.assertNotIn("2026-10-05 weeknight", ra["shifts"]["partial"])


if __name__ == "__main__":
    unittest.main()
