"""Offline tests of control.py: the possible-planned-control score."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import control as c  # noqa: E402


def dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def pres(prid, start):
    return {"kind": "presentation", "presentation_id": prid, "start": start}


def stay(start, end, ward, medic, kind="admission"):
    return {"kind": kind, "start": start, "end": end, "section_in": ward, "section_out": ward,
            "medic_in": medic, "medic_out": medic}


# 2026-10-05 is a Monday
VISIT = pres("50", "05/10/2026 09:00")


class TestScore(unittest.TestCase):
    def test_spontaneous_night_ambulance(self):
        h = [pres("50", "05/10/2026 23:00")]
        r = c.assess(dt("2026-10-05 23:40"), h, "SAJ")
        self.assertFalse(r["flag"])
        self.assertEqual([x["code"] for x in r["reasons"]], ["ambulance"])

    def test_surgical_control_on_a_weekday_morning(self):
        h = [VISIT, stay("20/09/2026 10:00", "28/09/2026 12:00", "CHIRURGIE I", "DR. POPESCU ION")]
        r = c.assess(dt("2026-10-05 09:10"), h, "Mijloace proprii")
        # surgical 30 d (+2), any 90 d (+1), weekday morning (+1), fast (+1)
        self.assertEqual(r["score"], 5)
        self.assertTrue(r["flag"])
        self.assertEqual(r["reasons"][0], {"code": "surgical_discharge", "days": 6})

    def test_surgeon_on_call_from_roster(self):
        h = [pres("50", "05/10/2026 18:00"),
             stay("01/08/2026 10:00", "10/08/2026 12:00", "CHIRURGIE I", "DR. POPESCU ION")]
        roster = {date(2026, 10, 5): [("popescu", "i")]}
        r = c.assess(dt("2026-10-05 18:30"), h, "", roster)
        self.assertIn({"code": "surgeon_on_call"}, r["reasons"])
        self.assertEqual(r["score"], 3)                  # 90 d (+1), on call (+2)
        other = {date(2026, 10, 5): [("popescu", "m")]}
        self.assertNotIn({"code": "surgeon_on_call"},
                         c.assess(dt("2026-10-05 18:30"), h, "", other)["reasons"])

    def test_night_after_08_belongs_to_previous_roster_date(self):
        self.assertEqual(c.shift_date(dt("2026-10-06 07:30")), date(2026, 10, 5))
        self.assertEqual(c.shift_date(dt("2026-10-06 08:00")), date(2026, 10, 6))

    def test_recent_upu_visit_excludes_this_one(self):
        h = [VISIT, pres("40", "02/10/2026 20:00")]
        r = c.assess(dt("2026-10-05 09:40"), h)
        self.assertIn({"code": "recent_upu_visit", "days": 2}, r["reasons"])
        self.assertNotIn({"code": "fast_request"}, r["reasons"])

    def test_roster_csv(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "s-2026-10.csv"), "w") as fh:
                fh.write("date,weekday,line1,line2,line3_cut\n"
                         "2026-10-05,Mon,Popescu,Ionescu O,Zaharia…\n")
            roster = c.load_roster(os.path.join(d, "*.csv"))
        self.assertEqual(roster[date(2026, 10, 5)], [("popescu", ""), ("ionescu", "o")])


if __name__ == "__main__":
    unittest.main()
