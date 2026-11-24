#!/usr/bin/env python3
"""Offline tests for coop_sponsor_check.py — fixtures only, no network.

  python3 -m unittest discover -s scripts/contrib/2026fa/arundhatik26-coop-sponsor-swe-15-1252/tests -v

The full-pipeline test runs the REAL scorer (scripts/score/role-scorer.mjs)
on fixture data, so it needs `node` but no network.
"""

import json
import os
import socket
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import coop_sponsor_check as c  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
PERSONA = os.path.join(FIX, "persona-fixture.json")


class NoNetwork:
    """Any socket connect during a test is a failure."""
    def __enter__(self):
        self._orig = socket.socket.connect
        def boom(*a, **k):
            raise AssertionError("network call attempted during offline test")
        socket.socket.connect = boom
    def __exit__(self, *a):
        socket.socket.connect = self._orig


class FullRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with NoNetwork():
            cls.log = c.run(PERSONA, cls.tmp.name)
        cls.by = {r["role_id"]: r for r in cls.log["roles"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_both_outputs_written(self):
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "run-log.json")))
        with open(os.path.join(self.tmp.name, "report.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("## Executive summary", md)
        for s in ("grad-dec-2027", "grad-apr-2028"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp.name, s, "role-scores.json")))

    def test_proven_live_role_applies(self):
        r = self.by["proven-live"]
        self.assertEqual(r["company"]["tier"]["value"], "Proven")
        self.assertEqual(r["company"]["total_approvals"]["source"], "record")
        self.assertEqual({v["recommendation"] for v in r["scenarios"].values()}, {"Apply"})

    def test_F1_not_in_dataset_is_unknown_not_zero(self):
        r = self.by["not-in-dataset"]
        self.assertEqual(r["company"]["status"], "not-in-dataset")
        with open(os.path.join(self.tmp.name, "grad-dec-2027", "roles.json"), encoding="utf-8") as f:
            roles = json.load(f)
        sent = next(x for x in roles if x["role_id"] == "not-in-dataset")
        self.assertNotIn("p", sent["sponsorship"])       # no invented 0.0
        self.assertEqual(sent["sponsorship"]["tier"], "Unknown")
        self.assertTrue(r["next_action"].startswith("NETWORK"))
        for v in r["scenarios"].values():
            self.assertNotEqual(v["recommendation"], "Apply")

    def test_F2_blank_approvals_is_no_record(self):
        r = self.by["blank-sponsor"]
        self.assertEqual(r["company"]["status"], "no-sponsorship-record")
        self.assertIsNone(r["company"]["total_approvals"]["value"])
        self.assertTrue(r["next_action"].startswith("NETWORK"))

    def test_F3_two_rows_same_name_is_ambiguous(self):
        r = self.by["ambiguous-twin"]
        self.assertEqual(r["company"]["status"], "ambiguous")
        self.assertEqual(len(r["company"]["rows"]), 2)
        self.assertTrue(r["next_action"].startswith("HUMAN CHECK"))

    def test_first_word_is_a_candidate_never_a_match(self):
        # Changed 2026-11-23 with the brand-name fix. Before: "ACME" found nothing. Now "ACME" is the first word of
        # "ACME SOFTWARE INC" and "ACME DECOY BRAND INC", so both are listed for a human (gate G2) — still never
        # auto-matched, which is what the old test protected.
        comp = self.by["decoy-substring"]["company"]
        self.assertEqual(comp["status"], "ambiguous")
        self.assertEqual({r["company_name"] for r in comp["rows"]}, {"ACME SOFTWARE INC", "ACME DECOY BRAND INC"})
        self.assertTrue(self.by["decoy-substring"]["next_action"].startswith("HUMAN CHECK"))

    def test_F4_tiers(self):
        self.assertEqual(self.by["likely-small"]["company"]["tier"]["value"], "Likely")
        nosoft = self.by["possible-nosoft"]["company"]
        self.assertEqual(nosoft["tier"]["value"], "Possible")
        self.assertEqual(nosoft["software_titles"]["value"], [])

    def test_F5_coop_after_graduation_closes_timeline(self):
        r = self.by["late-coop"]
        dec, apr = r["scenarios"]["grad-dec-2027"], r["scenarios"]["grad-apr-2028"]
        self.assertEqual(dec["timeline"]["status"], "closed")
        self.assertEqual(dec["recommendation"], "Skip")
        self.assertEqual(apr["timeline"]["status"], "open")
        self.assertTrue(r["next_action"].startswith("DEPENDS ON GRADUATION DATE"))

    def test_F6_liveness_dead_uncertain_unchecked_all_close(self):
        for rid, status in (("proven-dead", "expired"), ("proven-uncertain", "uncertain"),
                            ("proven-unchecked", "unchecked")):
            r = self.by[rid]
            self.assertEqual(r["liveness"]["status"], status)
            self.assertEqual(r["liveness"]["factor"]["value"], 0.0)
            for v in r["scenarios"].values():
                self.assertEqual(v["recommendation"], "Skip", rid)
            self.assertTrue(r["next_action"].startswith("NETWORK, DON'T APPLY"), rid)

    def test_unknown_soc_has_no_wage(self):
        ctx = self.log["soc_context"]["15-9999"]
        self.assertEqual(ctx["status"], "no-occupation-row")
        self.assertNotIn("annual_median_wage", ctx)
        self.assertEqual(self.log["soc_context"]["15-1252"]["annual_median_wage"]["value"], 133080.0)

    def test_every_scorer_term_is_labeled(self):
        ok = {"record", "model-judgment", "your-input"}
        for r in self.log["roles"]:
            for v in r["scenarios"].values():
                for t in v["scorer_trace"]["votes"] + v["scorer_trace"]["gates"]:
                    self.assertIn(t["source"], ok)

    def test_inputs_are_hashed(self):
        self.assertEqual(len(self.log["inputs"]["sponsor_csv"]["sha256"]), 64)


class Units(unittest.TestCase):
    def test_bad_fit_stops(self):
        with open(PERSONA, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["roles"][0]["fit"] = 1.7
        with self.assertRaises(c.InputError):
            c.validate_input(cfg)

    def test_bad_date_stops(self):
        with self.assertRaises(c.InputError):
            c.parse_date("Dec 2027", "graduation")

    def test_graduation_already_past(self):
        sc = {"name": "x", "graduation": "2026-05-01", "opt_months": 12, "stem_months": 24}
        role = {"role_id": "r", "coop_start": "2027-01-05", "coop_end": "2027-06-30"}
        tl = c.timeline_gate(role, sc, date(2026, 10, 2))
        self.assertEqual(tl["status"], "closed")
        self.assertEqual(tl["factor"]["value"], 0.0)

    def test_missing_csv_stops(self):
        with self.assertRaises(c.InputError):
            c.load_sponsor_index(os.path.join(FIX, "does-not-exist.csv"))

    def test_norm_name(self):
        self.assertEqual(c.norm_name("Bank of New York Mellon Corp."), "BANK OF NEW YORK MELLON")
        self.assertNotEqual(c.norm_name("MELLON"), c.norm_name("TAMARA MELLON BRAND INC"))

    def test_and_co_legal_form_matches_plain_name(self):
        # Exact names the USCIS H-1B Employer Data Hub lists for FY2026 (searched 2026-10-12).
        self.assertEqual(c.norm_name("GOLDMAN SACHS AND CO LLC"), "GOLDMAN SACHS")
        self.assertEqual(c.norm_name("GOLDMAN SACHS AND CO LLC"), c.norm_name("Goldman Sachs"))
        # The fix must not merge a different firm: "J GOLDMAN AND CO L P" is not Goldman Sachs.
        self.assertNotEqual(c.norm_name("J GOLDMAN AND CO L P"), c.norm_name("Goldman Sachs"))
        # An "AND" inside a name is kept.
        self.assertEqual(c.norm_name("PROCTER AND GAMBLE CO"), "PROCTER AND GAMBLE")


BRANDS = os.path.join(FIX, "brands-fixture.csv")   # exact dataset rows for the three brands (+ one invented decoy)
RULES = {"proven_min_approvals": 100, "p_proven": 0.9, "p_likely": 0.6, "p_sponsors_not_software": 0.3}
ALIASES = {"SOFI": ["SOCIAL FINANCE"]}


class BrandNames(unittest.TestCase):
    """Eval rows 19, 20, 25 (2026-10-25): the brand name hid a strong sponsor stored under its legal name.
    Predictions for this fix were written first: final-film/PREDICTIONS.md, 2026-11-23 15:32 EST."""

    @classmethod
    def setUpClass(cls):
        cls.idx = c.load_sponsor_index(BRANDS)

    def look(self, name, aliases=None):
        return c.resolve_company({"company": name}, self.idx, RULES, aliases)

    def names(self, comp):
        return {r["company_name"] for r in comp["rows"]}

    def test_robinhood_lists_robinhood_markets_for_a_human(self):
        comp = self.look("Robinhood")
        self.assertEqual(comp["status"], "ambiguous")
        self.assertIn("ROBINHOOD MARKETS INC", self.names(comp))

    def test_chime_lists_chime_financial_not_only_chime_inc(self):
        comp = self.look("Chime")
        self.assertEqual(comp["status"], "ambiguous")          # was: matched CHIME INC (2) with no human check
        self.assertEqual(self.names(comp), {"CHIME FINANCIAL INC", "CHIME INC"})

    def test_chime_does_not_pull_in_a_name_that_only_contains_it(self):
        self.assertNotIn("ARCHIMEDES DECOY INC", self.names(self.look("Chime")))

    def test_sofi_without_alias_misses_social_finance(self):
        comp = self.look("SoFi")
        self.assertNotIn("SOCIAL FINANCE INC", self.names(comp))

    def test_sofi_with_alias_lists_social_finance_for_a_human(self):
        comp = self.look("SoFi", ALIASES)
        self.assertEqual(comp["status"], "ambiguous")
        self.assertIn("SOCIAL FINANCE INC", self.names(comp))

    def test_every_candidate_says_how_it_was_found(self):
        comp = self.look("SoFi", ALIASES)
        how = {r["company_name"]: r["found_by"] for r in comp["rows"]}
        self.assertEqual(how["SOFI TECHNOLOGIES INC"], "first word(s) of the name")
        self.assertTrue(how["SOCIAL FINANCE INC"].startswith("alias"))

    def test_a_single_candidate_is_still_not_auto_answered(self):
        # One row found only by first word or alias still goes to a human: it is a guess, not an exact name.
        comp = self.look("Robinhood Markets")
        self.assertEqual(comp["status"], "matched")              # exact name → matched, as before
        idx = c.load_sponsor_index(BRANDS)
        one = c.resolve_company({"company": "Social"}, idx, RULES)
        self.assertEqual(one["status"], "ambiguous")             # 2 SOCIAL FINANCE rows, by first word
        lone = c.resolve_company({"company": "Archimedes"}, idx, RULES)
        self.assertEqual(lone["status"], "ambiguous")            # 1 row, first word only → still a human check
        self.assertEqual(len(lone["rows"]), 1)

    def test_alias_file_loads_and_is_your_input(self):
        path = os.path.join(os.path.dirname(HERE), "inputs", "brand-aliases.json")
        al = c.load_aliases(path)
        self.assertIn("SOFI", al)
        self.assertEqual(c.load_aliases(None), {})


if __name__ == "__main__":
    unittest.main()
