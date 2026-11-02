"""Offline tests of tools/upu_called.py: visit match, names, features, tiers."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import upu_called as c  # noqa: E402


def dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def pres(prid, start):
    return {"kind": "presentation", "presentation_id": prid, "start": start,
            "section_in": "UPU", "medic_in": "DR. UPU UNU"}


def adm(kind, start, end, ward, medic, prid="900"):
    return {"kind": kind, "presentation_id": prid, "start": start, "end": end,
            "section_in": ward, "section_out": ward, "medic_in": medic, "medic_out": medic}


class TestPickPresentation(unittest.TestCase):
    def test_newest_before_request(self):
        h = [pres("1", "01/10/2026 08:00"), pres("2", "05/10/2026 10:00"),
             pres("3", "06/10/2026 10:00")]
        self.assertEqual(c.pick_presentation(dt("2026-10-05 11:00"), h), "2")

    def test_admission_rows_do_not_count(self):
        h = [pres("1", "05/10/2026 09:00"),
             adm("admission", "05/10/2026 10:30", "", "Chirurgie I", "DR. A B", prid="7")]
        self.assertEqual(c.pick_presentation(dt("2026-10-05 11:00"), h), "1")

    def test_older_than_48_hours(self):
        self.assertIsNone(c.pick_presentation(dt("2026-10-05 11:00"),
                                              [pres("1", "02/10/2026 10:00")]))


class TestNames(unittest.TestCase):
    def test_order_title_diacritics(self):
        self.assertEqual(c.norm_name("DR. POPESCU ŞTEFAN"), c.norm_name("Stefan Popescu"))
        self.assertEqual(c.norm_name(""), "")

    def test_age(self):
        self.assertEqual(c.age_years("12y"), 12)
        self.assertAlmostEqual(c.age_years("6m"), 0.5)
        self.assertEqual(c.age_band(c.age_years("6m")), "<1")
        self.assertEqual(c.age_band(None), "?")

    def test_ward_name(self):
        self.assertEqual(c.ward_name("PEDIATRIE 2 ETAJ III(INACTIVA)"), "pediatrie 2")


def record(history, requester="DR. UPU DOI", triage="Cod 3", treatment=(), decision=None):
    return {"id": "1", "requested": "2026-10-05 16:30", "v_arrival": "2026-10-05 16:00",
            "status": "ended", "age": "7y", "prid": "50",
            "request": {"requester": requester, "physician_curant": "DR. UPU UNU"},
            "presentation": {"date_time": "05/10/2026 16:00", "triage_code": triage,
                             "transport_type": "Mijloace proprii", "treatment": list(treatment),
                             "decision": decision or "Plecat din UPU la domiciliu",
                             "medic": "DR. UPU UNU"},
            "history": [pres("50", "05/10/2026 16:00"), *history]}


class TestFeatures(unittest.TestCase):
    def setUp(self):
        self.home = {c.norm_name("DR. UPU UNU"): "upu", c.norm_name("DR. UPU DOI"): "upu",
                     c.norm_name("DR. WARD MEDIC"): "chirurgie i"}

    def test_spontaneous_visit(self):
        f = c.features(record([], triage="Cod 2", treatment=["x"]), self.home)
        self.assertEqual(f["tier"], "none")
        self.assertFalse(f["nonurgent"])
        self.assertEqual(f["shift"], "weeknight")
        self.assertEqual(f["arr_to_req"], 30)

    def test_ordered_by_a_ward_physician(self):
        f = c.features(record([], requester="Dr. Medic Ward"), self.home)
        self.assertTrue(f["req_outside"])
        self.assertEqual(f["req_home"], "chirurgie i")
        self.assertEqual(f["tier"], "definite")

    def test_recent_discharge_and_non_urgent(self):
        h = [adm("admission", "20/09/2026 10:00", "25/09/2026 12:00", "CHIRURGIE I",
                 "DR. WARD MEDIC")]
        f = c.features(record(h), self.home)
        self.assertEqual(f["days_since_discharge"], 10)
        self.assertEqual(f["dis_ward"], "chirurgie i")
        self.assertEqual(f["tier"], "probable")

    def test_open_day_admission(self):
        h = [adm("day_admission", "05/10/2026 09:00", "05/10/2026 18:00", "PEDIATRIE 1",
                 "DR. WARD MEDIC")]
        f = c.features(record(h), self.home)
        self.assertTrue(f["open_day_admission"])
        self.assertEqual(f["tier"], "definite")

    def test_prior_upu_visits_exclude_this_one(self):
        f = c.features(record([pres("40", "20/09/2026 10:00")]), self.home)
        self.assertEqual((f["upu30"], f["upu90"]), (1, 1))

    def test_later_elective_surgery(self):
        h = [adm("admission", "12/10/2026 08:00", "14/10/2026 10:00", "CHIRURGIE I",
                 "DR. WARD MEDIC")]
        f = c.features(record(h), self.home)
        self.assertEqual(f["later_surg_days"], 6)
        self.assertTrue(f["later_surg_elective"])
        self.assertEqual(f["tier"], "probable")
        f = c.features(record(h + [pres("60", "11/10/2026 20:00")]), self.home)
        self.assertFalse(f["later_surg_elective"])

    def test_staff_map(self):
        recs = [record([adm("admission", "01/09/2026 10:00", "03/09/2026 10:00", "ORTOPEDIE",
                            "DR. ORTO PED")])]
        home = c.staff_map(recs)
        self.assertEqual(home[c.norm_name("DR. UPU UNU")], "upu")
        self.assertEqual(home[c.norm_name("DR. ORTO PED")], "ortopedie")


class TestTexts(unittest.TestCase):
    def test_report_flags(self):
        f = c.text_features({"report": "Comparativ cu examinarea anterioara, fara colectii. "
                                       "Status post apendicectomie."}, dt("2026-10-05 16:00"))
        self.assertTrue(f["rep_compare"] and f["rep_postop"] and f["rep_normal"])

    def test_scheduled_control(self):
        t = {"epicrisis": "Recomandari: control chirurgical cu ecografie peste 7 zile.",
             "co_ward": "CHIRURGIE I", "co_out": "2026-09-28 12:00"}
        f = c.text_features(t, dt("2026-10-05 16:00"))
        self.assertEqual(f["epi_days"], 7)
        self.assertTrue(f["epi_on_time"] and f["epi_us"] and f["epi_surgery"])
        late = c.text_features(t, dt("2026-10-20 16:00"))
        self.assertFalse(late["epi_on_time"])

    def test_weeks(self):
        f = c.text_features({"epicrisis": "revine la 2 saptamani", "co_out": "2026-09-21 10:00"},
                            dt("2026-10-05 10:00"))
        self.assertEqual(f["epi_days"], 14)
        self.assertTrue(f["epi_on_time"])

    def test_previous_us_other_visit_only(self):
        recs = [{"id": "1", "pid": "p", "prid": "a", "requested": "2026-10-01 10:00"},
                {"id": "2", "pid": "p", "prid": "a", "requested": "2026-10-01 12:00"},
                {"id": "3", "pid": "p", "prid": "b", "requested": "2026-10-03 10:00"}]
        prev = c.previous_us(recs)
        self.assertNotIn("1", prev)
        self.assertNotIn("2", prev)
        self.assertAlmostEqual(prev["3"], 2 - 2 / 24)


class TestRoster(unittest.TestCase):
    def test_csv(self):
        import tempfile
        home = {c.norm_name("Dr. Popescu Oana"): "chirurgie i",
                c.norm_name("Dr. Popescu Mihai"): "chirurgie ii",
                c.norm_name("Dr. Ionescu Ion"): "chirurgie i",
                c.norm_name("Dr. Ionescu Ana"): "pediatrie 1"}
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write("date,weekday,line1,line2,line3_cut\n2026-11-09,Mon,Ionescu,Popescu O,Zaharia…\n")
        r = c.roster_from_csv(fh.name, home)
        os.unlink(fh.name)
        on = c.on_call(r, datetime(2026, 11, 9).date(), "p1")
        self.assertEqual(on, {c.norm_name("Ionescu Ion"), c.norm_name("Popescu Oana")})


if __name__ == "__main__":
    unittest.main()
