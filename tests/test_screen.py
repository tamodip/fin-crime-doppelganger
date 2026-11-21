import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "system"))
import screen


def write_jsonl(folder, name, rows):
    with (folder / (name + ".jsonl")).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class EngineFixture(unittest.TestCase):
    def make_data(self, customer=None, hit=None, alert=None, accounts=None, checks=None, onboarding=None, notes=None, search=None, customers=None):
        self.temp = tempfile.TemporaryDirectory()
        folder = Path(self.temp.name)
        customer = customer or {
            "record_id": "CUS-000001", "full_name": "Maya Example", "preferred_name": None,
            "login_name": "mayae", "entity_type": "Individual", "dob": "1988-04-12",
            "residence_country": "France", "nationality": None, "email": "maya@example.test",
            "phone": "+44 7700 900001", "city": "Paris", "address": "Paris, France",
        }
        customers = customers or [customer]
        hit = hit or {
            "hit_id": "H-000001", "alert_id": "A-000001", "name": "Maya Example",
            "aliases": [], "entity_type": "Individual", "dobs": ["1988-04"],
            "countries": ["France"], "addresses": [], "nationality": [], "citizenship": [],
            "place_of_birth": None, "profile_notes": None, "deceased_date": None,
        }
        alert = alert or {
            "alert_id": "A-000001", "screened_at": "2026-11-01",
            "customer": {"name": "Maya Example", "entity_type": "Individual", "dob": "1988-04-12", "country": "France", "city": "Paris"},
            "account_ref": None, "login_handle": None, "email": None, "hit_ids": [hit["hit_id"]],
        }
        for name, rows in {
            "alerts": [alert], "hits": [hit], "customers": customers,
            "accounts": accounts or [], "onboarding": onboarding or [],
            "kyc_checks": checks or [], "notes": notes or [], "search_results": search or [],
        }.items():
            write_jsonl(folder, name, rows)
        (folder / "name_variants.json").write_text(json.dumps({
            "groups": [["Mohammad", "Mohammed", "Mohamed"], ["Abdul", "Abd"], ["Rahman", "Rehman"]],
            "company_legal_forms": ["Ltd", "Limited", "GmbH", "LLC", "Inc", "SA"],
        }), encoding="utf-8")
        return screen.Data(str(folder)), alert, hit

    def tearDown(self):
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def decide(self, data, alert, hit):
        people = screen.resolve_customer(data, alert)
        return screen.decide_hit(data, alert, hit, people)


class NamePolicyTests(EngineFixture):
    def test_accent_case_punctuation_and_order_are_ignored(self):
        self.assertTrue(screen.names_agree("Élodie O'Connor", "OConnor, ELODIE"))

    def test_joined_and_split_names_count_as_one_part(self):
        self.assertTrue(screen.names_agree("Abdulsalam Smith", "Abdul Salam Smith"))

    def test_a_single_hit_alias_can_match_one_customer_name_part(self):
        self.assertTrue(screen.names_agree("Musa Ibrahim", "Ibrahim"))

    def test_one_hit_part_cannot_be_reused_for_two_customer_parts(self):
        self.assertFalse(screen.names_agree("Malia Maria", "Marla Brown"))

    def test_placeholders_do_not_create_name_agreement(self):
        self.assertFalse(screen.names_agree("NA UNKNOWN", "Unknown NA"))

    def test_customer_with_one_real_part_is_not_cleared_on_name(self):
        customer = {"record_id": "CUS-000001", "full_name": "Madonna", "preferred_name": None,
                    "login_name": "madonna", "entity_type": "Individual", "dob": "1988-04-12",
                    "residence_country": None, "nationality": None, "email": None, "phone": None, "city": None, "address": None}
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "Madonna", "aliases": [],
               "entity_type": "Individual", "dobs": ["1988-04-12"], "countries": [], "addresses": [],
               "nationality": [], "citizenship": [], "profile_notes": None, "deceased_date": None}
        alert = {"alert_id": "A-000001", "screened_at": "2026-11-01",
                 "customer": {"name": "Madonna", "entity_type": "Individual", "dob": "1988-04-12", "country": None, "city": None},
                 "account_ref": None, "login_handle": None, "email": None, "hit_ids": ["H-000001"]}
        data, alert, hit = self.make_data(customer, hit, alert)
        self.assertEqual(self.decide(data, alert, hit)["decision"], "REVIEW")


class ResolutionTests(EngineFixture):
    def test_unlinked_typo_candidate_is_retrieved_before_fuzzy_comparison(self):
        customer = {"record_id": "CUS-000001", "full_name": "John Smith", "preferred_name": None,
                    "login_name": "jsmith", "entity_type": "Individual", "dob": "1988-04-12",
                    "residence_country": None, "nationality": None, "email": None, "phone": None, "city": None, "address": None}
        alert = {"alert_id": "A-000001", "screened_at": "2026-11-01",
                 "customer": {"name": "Jonh Smith", "entity_type": "Individual", "dob": "1988-04-12", "country": None, "city": None},
                 "account_ref": None, "login_handle": None, "email": None, "hit_ids": ["H-000001"]}
        data, alert, hit = self.make_data(customer, alert=alert)
        self.assertEqual(screen.resolve_customer(data, alert), [["CUS-000001"]])

    def test_broken_supplied_link_does_not_fall_back_to_an_unrelated_name_search(self):
        alert = {"alert_id": "A-000001", "screened_at": "2026-11-01",
                 "customer": {"name": "Maya Example", "entity_type": "Individual", "dob": "1988-04-12", "country": "France", "city": "Paris"},
                 "account_ref": "ACC-MISSING", "login_handle": None, "email": None, "hit_ids": ["H-000001"]}
        data, alert, hit = self.make_data(alert=alert)
        self.assertEqual(screen.resolve_customer(data, alert), [])

    def test_multiple_linked_candidates_are_disambiguated_by_screened_details(self):
        second = {"record_id": "CUS-000002", "full_name": "Other Person", "preferred_name": None,
                  "login_name": "other", "entity_type": "Individual", "dob": "1970-01-01",
                  "residence_country": "Italy", "nationality": None, "email": None, "phone": None, "city": "Rome", "address": "Rome"}
        accounts = [{"account_id": "ACC-1", "customer_id": "CUS-000001"}, {"account_id": "ACC-1", "customer_id": "CUS-000002"}]
        alert = {"alert_id": "A-000001", "screened_at": "2026-11-01",
                 "customer": {"name": "Maya Example", "entity_type": "Individual", "dob": "1988-04-12", "country": "France", "city": "Paris"},
                 "account_ref": "ACC-1", "login_handle": None, "email": None, "hit_ids": ["H-000001"]}
        data, alert, hit = self.make_data(alert=alert, accounts=accounts, customers=[
            {"record_id": "CUS-000001", "full_name": "Maya Example", "preferred_name": None, "login_name": "mayae", "entity_type": "Individual", "dob": "1988-04-12", "residence_country": "France", "nationality": None, "email": None, "phone": None, "city": "Paris", "address": "Paris"}, second])
        self.assertEqual(screen.resolve_customer(data, alert), [["CUS-000001"]])

    def test_shared_phone_alone_does_not_merge_records(self):
        a = {"record_id": "CUS-000001", "full_name": "Maya Example", "entity_type": "Individual", "dob": "1988-04-12", "phone": "+44 1", "email": None}
        b = {"record_id": "CUS-000002", "full_name": "Lena Example", "entity_type": "Individual", "dob": "1990-06-15", "phone": "+44 1", "email": None}
        data, _alert, _hit = self.make_data(customer=a, customers=[a, b])
        self.assertEqual(screen.person_closure(data, "CUS-000001"), ["CUS-000001"])

    def test_shared_phone_and_full_dob_merge_records(self):
        a = {"record_id": "CUS-000001", "full_name": "Maya Example", "entity_type": "Individual", "dob": "1988-04-12", "phone": "+44 1", "email": None}
        b = {"record_id": "CUS-000002", "full_name": "Maya Older", "entity_type": "Individual", "dob": "1988-04-12", "phone": "+44 1", "email": None}
        data, _alert, _hit = self.make_data(customer=a, customers=[a, b])
        self.assertEqual(screen.person_closure(data, "CUS-000001"), ["CUS-000001", "CUS-000002"])


class PolicyBoundaryTests(EngineFixture):
    def test_one_agreeing_dob_among_several_prevents_dob_clearance(self):
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "Maya Example", "aliases": [],
               "entity_type": "Individual", "dobs": ["1970-01-01", "1988"], "countries": ["France"],
               "addresses": [], "nationality": [], "citizenship": [], "profile_notes": None, "deceased_date": None}
        data, alert, hit = self.make_data(hit=hit)
        self.assertEqual(self.decide(data, alert, hit)["decision"], "SAME_ENTITY")

    def test_location_difference_plus_name_and_dob_agreement_is_review(self):
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "Maya Example", "aliases": [],
               "entity_type": "Individual", "dobs": ["1988-04-12"], "countries": ["Italy"],
               "addresses": [], "nationality": [], "citizenship": [], "profile_notes": None, "deceased_date": None}
        data, alert, hit = self.make_data(hit=hit)
        self.assertEqual(self.decide(data, alert, hit)["decision"], "REVIEW")

    def test_death_date_before_screening_is_a_dated_contradiction(self):
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "Maya Example", "aliases": [],
               "entity_type": "Individual", "dobs": ["1988-04-12"], "countries": ["France"],
               "addresses": [], "nationality": [], "citizenship": [], "profile_notes": None, "deceased_date": "2020-01-01"}
        data, alert, hit = self.make_data(hit=hit)
        row = self.decide(data, alert, hit)
        self.assertEqual((row["decision"], row["reason_code"]), ("DIFFERENT_ENTITY", "DECEASED"))

    def test_same_day_death_and_screening_is_not_proven_before_screening(self):
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "Maya Example", "aliases": [],
               "entity_type": "Individual", "dobs": ["1988-04-12"], "countries": ["France"],
               "addresses": [], "nationality": [], "citizenship": [], "profile_notes": None, "deceased_date": "2026-11-01"}
        data, alert, hit = self.make_data(hit=hit)
        self.assertNotEqual(self.decide(data, alert, hit)["reason_code"], "DECEASED")

    def test_company_incorporated_later_in_same_year_is_temporally_impossible(self):
        customer = {"record_id": "CUS-000001", "full_name": "North Star Ltd", "entity_type": "Company", "dob": "2020-07-20", "residence_country": "France", "email": None, "phone": None}
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "North Star Ltd", "aliases": [], "entity_type": "Company",
               "dobs": ["2020-07-20"], "countries": ["France"], "addresses": [], "nationality": [], "citizenship": [],
               "profile_notes": "According to regulator.example; July 19, 2020: North Star received a licence.", "deceased_date": None}
        alert = {"alert_id": "A-000001", "screened_at": "2026-11-01", "customer": {"name": "North Star Ltd", "entity_type": "Company", "dob": "2020-07-20", "country": "France", "city": None}, "account_ref": None, "login_handle": None, "email": None, "hit_ids": ["H-000001"]}
        data, alert, hit = self.make_data(customer, hit, alert)
        row = self.decide(data, alert, hit)
        self.assertEqual((row["decision"], row["reason_code"]), ("DIFFERENT_ENTITY", "TEMPORAL_IMPOSSIBILITY"))

    def test_company_profile_biography_is_not_used_as_incorporation_date(self):
        customer = {"record_id": "CUS-000001", "full_name": "North Star Ltd", "entity_type": "Company", "dob": "2010-07-20", "residence_country": "France", "email": None, "phone": None}
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "North Star Ltd", "aliases": [], "entity_type": "Company",
               "dobs": [], "countries": ["France"], "addresses": [], "nationality": [], "citizenship": [],
               "profile_notes": "North Star Ltd was founded in 1990.\n\nAccording to regulator.example; July 19, 2020: It received a licence.", "deceased_date": None}
        alert = {"alert_id": "A-000001", "screened_at": "2026-11-01", "customer": {"name": "North Star Ltd", "entity_type": "Company", "dob": "2010-07-20", "country": "France", "city": None}, "account_ref": None, "login_handle": None, "email": None, "hit_ids": ["H-000001"]}
        data, alert, hit = self.make_data(customer, hit, alert)
        self.assertEqual(self.decide(data, alert, hit)["decision"], "SAME_ENTITY")

    def test_entity_type_mismatch_is_explicit(self):
        hit = {"hit_id": "H-000001", "alert_id": "A-000001", "name": "Maya Example Ltd", "aliases": [], "entity_type": "Company",
               "dobs": [], "countries": [], "addresses": [], "nationality": [], "citizenship": [], "profile_notes": None, "deceased_date": None}
        data, alert, hit = self.make_data(hit=hit)
        row = self.decide(data, alert, hit)
        self.assertEqual((row["decision"], row["reason_code"]), ("DIFFERENT_ENTITY", "ENTITY_TYPE_MISMATCH"))

    def test_rejected_and_expired_kyc_do_not_override_customer_facts(self):
        checks = [
            {"applicant_id": "APP-1", "check_id": "KYC-1", "checked_at": "2025-01-01", "verified_name": "Other Person", "verified_dob": "1970-01-01", "document_country": "Italy", "document_number": "NO1", "result": "rejected"},
            {"applicant_id": "APP-1", "check_id": "KYC-2", "checked_at": "2025-02-01", "verified_name": "Other Person", "verified_dob": "1970-01-01", "document_country": "Italy", "document_number": "NO2", "result": "expired"},
        ]
        onboarding = [{"customer_id": "CUS-000001", "account_id": "ACC-1", "kyc_applicant_id": "APP-1"}]
        data, _alert, _hit = self.make_data(checks=checks, onboarding=onboarding)
        self.assertEqual(data.checks_for_customer("CUS-000001"), [])
        self.assertFalse(screen.is_kyc_note({"channel": "kyc", "text": "Identity check failed and was rejected."}))

    def test_approved_kyc_note_paraphrase_provides_verified_facts(self):
        note = {"note_id": "NOTE-1", "requester_email": "maya@example.test", "created_at": "2025-01-01", "channel": "kyc",
                "text": "Persona performed a successful check on MAYA EXAMPLE, born April 12, 1988, using a passport from France."}
        data, _alert, _hit = self.make_data(notes=[note])
        person = screen.build_person(data, ["CUS-000001"])
        self.assertEqual(person["verified_name"], "MAYA EXAMPLE")
        self.assertEqual(person["dob"], (1988, 4, 12))


class DateAndSourceTests(EngineFixture):
    def test_partial_dates_are_not_overclaimed_as_ordered(self):
        self.assertFalse(screen.definitely_after((2020, 7, None), (2020, 7, 1)))
        self.assertTrue(screen.definitely_after((2020, 8, None), (2020, 7, 1)))
        self.assertFalse(screen.definitely_before((2020, 11, None), (2020, 11, 15)))

    def test_age_at_report_year_boundary_keeps_two_possible_birth_years(self):
        self.assertEqual(screen.age_birth_years("A person, aged 45 in March 2019, was sentenced."), ((1973, 1974), (2019, 3, None)))

    def test_company_dob_never_comes_from_biography_or_search_results(self):
        hit = {"hit_id": "H-000001", "entity_type": "Company", "dobs": [], "profile_notes": "Born in 1990.", "name": "Maya Example"}
        data, _alert, _ = self.make_data(hit=hit)
        self.assertEqual(screen.hit_dobs(data, hit), [])

    def test_decisive_hit_fields_are_cited(self):
        data, alert, hit = self.make_data()
        row = self.decide(data, alert, hit)
        self.assertIn("H-000001#dobs", row["evidence"])
        self.assertIn("H-000001#name", row["evidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
