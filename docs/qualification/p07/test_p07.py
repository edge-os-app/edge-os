import copy
import itertools
import json
import random
import runpy
import unittest
from pathlib import Path

from qualification import (
    BindingNotEmittable,
    InvalidInput,
    Unsupported,
    assemble_segments,
    bucketize,
    binding_incompatibilities,
    bucket_available_at,
    bucket_status_counts,
    decode_swap_log,
    decision_times,
    dataset_revision,
    epoch,
    feasibility,
    history_observations,
    ingest,
    keccak256,
    opportunity_eligibility,
    profile_problems,
    profile_sha256,
    qualify,
    reference_trade,
    research_binding_view,
    to_p02_binding,
    validate_schedule,
)

FIXTURES = json.loads((Path(__file__).resolve().parent / "fixtures.json").read_text(encoding="utf-8"))
PROFILES = FIXTURES["profiles"]
P02 = runpy.run_path(str(Path(__file__).resolve().parents[2] / "contracts/p02/check_contract.py"))


class KeccakIdentity(unittest.TestCase):
    def test_known_answers(self) -> None:
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_v2_swap_topic_comes_from_the_signature(self) -> None:
        profile = PROFILES["SYN_Q0"]["event"]
        self.assertEqual("0x" + keccak256(profile["signature"].encode()).hex(), profile["topic0"])

    def test_v3_signature_gives_a_different_topic(self) -> None:
        v3 = "Swap(address,address,int256,int256,uint160,uint128,int24)"
        self.assertEqual("0x" + keccak256(v3.encode()).hex(),
                         "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67")


class DecodeAndConvert(unittest.TestCase):
    def test_positive_cases_match_hand_written_expectations(self) -> None:
        cases = [c for c in FIXTURES["decode_cases"] if "trade" in c["expect"]]
        self.assertGreaterEqual(len(cases), 12)
        for case in cases:
            with self.subTest(case["id"]):
                got = decode_swap_log(PROFILES[case["profile"]], case["log"])
                want = case["expect"]["trade"]
                self.assertEqual(got.pool_side, want["pool_side"])
                self.assertEqual(str(got.quote_raw), want["quote_raw"])
                self.assertEqual(str(got.base_raw), want["base_raw"])
                self.assertEqual(got.quote_amount, want["quote_amount"])
                self.assertEqual(got.base_amount, want["base_amount"])
                self.assertEqual(got.price, want["price"])
                for key in ("block_number", "log_index", "block_timestamp", "block_hash"):
                    if key in case["expect"]:
                        self.assertEqual(getattr(got, key), case["expect"][key])

    def test_unsupported_cases_raise_their_named_code(self) -> None:
        cases = [c for c in FIXTURES["decode_cases"] if "unsupported" in c["expect"]]
        self.assertGreaterEqual(len(cases), 22)
        for case in cases:
            with self.subTest(case["id"]):
                with self.assertRaises(Unsupported) as caught:
                    decode_swap_log(PROFILES[case["profile"]], case["log"])
                self.assertEqual(caught.exception.code, case["expect"]["unsupported"])

    def test_both_directions_give_the_same_price_in_either_pool_order(self) -> None:
        by_id = {c["id"]: c for c in FIXTURES["decode_cases"]}
        prices = {
            decode_swap_log(PROFILES[by_id[i]["profile"]], by_id[i]["log"]).price
            for i in ("D01-quote-in-base-out", "D02-base-in-quote-out",
                      "D07-reversed-pool-order-sell", "D08-reversed-pool-order-buy")
        }
        self.assertEqual(prices, {"2.5"})

    def test_input_log_is_not_modified(self) -> None:
        case = FIXTURES["decode_cases"][0]
        before = copy.deepcopy(case["log"])
        decode_swap_log(PROFILES[case["profile"]], case["log"])
        self.assertEqual(case["log"], before)


class Ingest(unittest.TestCase):
    def run_case(self, case: dict, logs: list | None = None):
        return ingest(PROFILES[case["profile"]], case["logs"] if logs is None else logs)

    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["ingest_cases"]:
            with self.subTest(case["id"]):
                got, want = self.run_case(case), case["expect"]
                self.assertEqual(got.identities(), want["identities"])
                self.assertEqual(got.duplicates, want["duplicates"])
                self.assertEqual(
                    [{"kind": c["kind"], "identities": sorted(c["identities"])} for c in got.conflicts],
                    want["conflicts"],
                )
                summary = got.summary()
                self.assertEqual(summary["rejected_codes"], want["rejected_codes"])
                self.assertEqual(summary["removed"], want["removed"])
                self.assertEqual(summary["foreign"], want["foreign"])
                self.assertEqual(summary["unlocated_rejections"], want["unlocated"])
                self.assertEqual(summary["pool_sides"], want["pool_sides"])

    def test_duplicate_copies_are_counted_once_each(self) -> None:
        by_id = {c["id"]: c for c in FIXTURES["ingest_cases"]}
        self.assertEqual(self.run_case(by_id["I01-canonical-order"]).summary()["duplicate_copies"], 0)
        self.assertEqual(self.run_case(by_id["I02-exact-duplicate"]).summary()["duplicate_copies"], 1)

    def test_provider_row_order_never_changes_the_result(self) -> None:
        case = next(c for c in FIXTURES["ingest_cases"] if c["id"] == "I01-canonical-order")
        self.assertEqual(len(case["logs"]), 5)
        for order in itertools.permutations(case["logs"]):
            self.assertEqual(self.run_case(case, list(order)).identities(), case["expect"]["identities"])

    def test_conflicting_versions_are_held_out_not_chosen(self) -> None:
        case = next(c for c in FIXTURES["ingest_cases"] if c["id"] == "I03-conflicting-duplicate")
        got = self.run_case(case)
        self.assertNotIn("999001:103:0:7", got.identities())
        self.assertEqual(got.summary()["conflicts"], 1)

    def test_failed_record_does_not_stop_the_batch(self) -> None:
        case = next(c for c in FIXTURES["ingest_cases"] if c["id"] == "I07-rejected-records-are-counted")
        self.assertEqual(self.run_case(case).identities(), ["999001:101:0:0"])


def coverage_for(case_id: str) -> list[dict]:
    case = next(c for c in FIXTURES["coverage_cases"] if c["id"] == case_id)
    return assemble_segments(PROFILES[case["profile"]], case["scan_request"], case["pages"],
                             case["archive_height"])["segments"]


class Coverage(unittest.TestCase):
    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["coverage_cases"]:
            with self.subTest(case["id"]):
                got = assemble_segments(PROFILES[case["profile"]], case["scan_request"], case["pages"],
                                        case["archive_height"])
                self.assertEqual(got["segments"], case["expect"]["segments"])
                self.assertEqual([b["code"] for b in got["breaks"]], case["expect"]["break_codes"])

    def test_page_order_in_the_input_does_not_matter(self) -> None:
        case = FIXTURES["coverage_cases"][0]
        got = assemble_segments(PROFILES[case["profile"]], case["scan_request"], list(reversed(case["pages"])),
                                case["archive_height"])
        self.assertEqual(got["segments"], case["expect"]["segments"])


class Buckets(unittest.TestCase):
    def run_case(self, case: dict, logs: list | None = None) -> list[dict]:
        profile = PROFILES[case["profile"]]
        result = ingest(profile, case["logs"] if logs is None else logs)
        return bucketize(profile, result, coverage_for(case["coverage_case"]), case["window"])

    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["bucket_cases"]:
            with self.subTest(case["id"]):
                got = self.run_case(case)
                want = case["expect"]["buckets"]
                self.assertEqual(len(got), len(want))
                for bucket, expected in zip(got, want):
                    self.assertEqual(bucket["start"], expected["start"])
                    self.assertEqual(bucket["status"], expected["status"])
                    self.assertEqual(bucket["reasons"], expected["reasons"])
                    self.assertEqual(bucket["trade_count"], expected["trade_count"])
                    self.assertEqual(bucket["quote_volume"], expected["quote_volume"])
                    close = bucket["close"]
                    self.assertEqual(None if close is None else close["identity"], expected["close_identity"])
                    self.assertEqual(None if close is None else close["price"], expected["close_price"])

    def test_close_does_not_depend_on_provider_row_order(self) -> None:
        case = FIXTURES["bucket_cases"][0]
        rng = random.Random(7)
        for _ in range(60):
            logs = rng.sample(case["logs"], len(case["logs"]))
            got = self.run_case(case, logs)
            self.assertEqual([b["close"]["identity"] if b["close"] else None for b in got],
                             [None, "999001:106:0:0", "999001:108:0:0", None])

    def test_no_bucket_invents_a_price_or_volume_without_proof(self) -> None:
        for case in FIXTURES["bucket_cases"]:
            for bucket in self.run_case(case):
                if bucket["status"] in ("INCOMPLETE", "UNQUALIFIED"):
                    self.assertIsNone(bucket["close"])
                    self.assertIsNone(bucket["quote_volume"])
                if bucket["status"] == "COMPLETE_EMPTY":
                    self.assertIsNone(bucket["close"])
                    self.assertEqual(bucket["quote_volume"], "0")

    def test_volume_counts_the_quote_leg_once_in_both_directions(self) -> None:
        case = FIXTURES["bucket_cases"][0]
        first = self.run_case(case)[1]
        self.assertEqual(first["quote_volume_raw"], "9700000")

    def test_window_must_use_whole_five_minute_buckets(self) -> None:
        case = FIXTURES["bucket_cases"][0]
        profile = PROFILES[case["profile"]]
        for bad in ({"start_utc": "2026-09-25T09:55:30Z", "end_utc": "2026-09-25T10:15:00Z"},
                    {"start_utc": "2026-09-25T09:55:00Z", "end_utc": "2026-09-25T10:15:30Z"},
                    {"start_utc": "2026-09-25T10:15:00Z", "end_utc": "2026-09-25T09:55:00Z"}):
            with self.assertRaises(InvalidInput):
                bucketize(profile, ingest(profile, []), coverage_for(case["coverage_case"]), bad)


class ReferenceWindows(unittest.TestCase):
    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["reference_cases"]:
            with self.subTest(case["id"]):
                profile = PROFILES[case["profile"]]
                got = reference_trade(profile, ingest(profile, case["logs"]), coverage_for(case["coverage_case"]),
                                      case["window"])
                want = case["expect"]
                self.assertEqual(got["status"], want["status"])
                if want["status"] == "FOUND":
                    self.assertEqual(got["trade"]["identity"], want["identity"])
                    self.assertEqual(got["trade"]["price"], want["price"])
                else:
                    self.assertEqual(got["reason"], want["reason"])
                    self.assertNotIn("trade", got)


class Availability(unittest.TestCase):
    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["availability_cases"]:
            with self.subTest(case["id"]):
                got = bucket_available_at(case["availability"], case["bucket"], case.get("delivered"))
                want = case["expect"]
                self.assertEqual(got["at"], want["at"])
                self.assertEqual(got["basis"], want["basis"])
                self.assertEqual(got.get("reason"), want.get("reason"))

    def test_unusable_models_are_rejected_not_defaulted(self) -> None:
        for case in FIXTURES["availability_errors"]:
            with self.subTest(case["id"]):
                with self.assertRaises(InvalidInput) as caught:
                    bucket_available_at(case["availability"], case["bucket"], case.get("delivered"))
                self.assertEqual(caught.exception.code, case["code"])

    def test_unknown_series_name_is_rejected(self) -> None:
        bucket = FIXTURES["eligibility_cases"][0]["buckets"][0]
        with self.assertRaises(InvalidInput) as caught:
            opportunity_eligibility("2026-09-25T10:20:00Z", [("close", bucket["start"])], [bucket],
                                    {"model": "ASSUMED_DELAY", "delay_seconds": 180})
        self.assertEqual(caught.exception.code, "SERIES")

    def test_unknown_bucket_status_is_rejected_by_eligibility_too(self) -> None:
        weird = {"start": "2026-09-25T10:00:00Z", "end": "2026-09-25T10:05:00Z", "status": "WEIRD"}
        with self.assertRaises(InvalidInput) as caught:
            opportunity_eligibility("2026-09-25T10:20:00Z", [("price", weird["start"])], [weird],
                                    {"model": "ASSUMED_DELAY", "delay_seconds": 180})
        self.assertEqual(caught.exception.code, "BUCKET_STATUS")

    def test_leap_second_text_is_not_a_timestamp(self) -> None:
        for text in ("2026-09-25T10:00:60Z", "2026-09-25T23:59:60Z", "2026-09-25 10:00:00Z", "2026-09-25T10:00:00"):
            with self.assertRaises(InvalidInput):
                epoch(text)
        self.assertEqual(epoch("2026-09-25T10:00:59Z") + 1, epoch("2026-09-25T10:01:00Z"))

    def test_eligibility_keeps_every_reason_and_never_moves_the_decision(self) -> None:
        for case in FIXTURES["eligibility_cases"]:
            with self.subTest(case["id"]):
                got = opportunity_eligibility(case["decision"], [tuple(r) for r in case["requirements"]],
                                              case["buckets"], case["availability"], case.get("delivered"))
                self.assertEqual(got["decision"], case["decision"])
                self.assertEqual(got["eligible"], case["expect"]["eligible"])
                self.assertEqual([r["code"] for r in got["reasons"]], case["expect"]["codes"])


class ScheduleFeasibility(unittest.TestCase):
    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["feasibility_cases"]:
            with self.subTest(case["id"]):
                got = feasibility(case["claim"], case["segments"], case["availability"])
                self.assertEqual(got["status"], case["expect"]["status"])
                self.assertEqual(len(got["partitions"]), len(case["expect"]["partitions"]))
                for actual, wanted in zip(got["partitions"], case["expect"]["partitions"]):
                    for key, value in wanted.items():
                        self.assertEqual(actual[key], value, key)

    def test_unusable_floors_and_partitions_are_rejected(self) -> None:
        for case in FIXTURES["claim_errors"]:
            with self.subTest(case["id"]):
                with self.assertRaises(InvalidInput) as caught:
                    feasibility(case["claim"], FIXTURES["feasibility_cases"][0]["segments"],
                                FIXTURES["feasibility_cases"][0]["availability"])
                self.assertEqual(caught.exception.code, case["code"])

    def test_schedule_off_the_bucket_grid_is_rejected(self) -> None:
        for case in FIXTURES["schedule_errors"]:
            with self.subTest(case["id"]):
                with self.assertRaises(InvalidInput):
                    validate_schedule(case["schedule"])

    def test_decision_times_follow_the_declared_clock_not_the_worker(self) -> None:
        schedule = FIXTURES["feasibility_cases"][0]["claim"]["schedule"]
        times = decision_times(schedule, "2026-09-25T00:00:00Z", "2026-09-25T03:00:00Z")
        self.assertEqual(times, [1790295000, 1790298600, 1790302200])


def apply_changes(root: dict, changes: list) -> dict:
    """Each change is a path ending in its new value. A path with ~delete removes the named key."""
    for change in changes:
        if len(change) >= 3 and change[-2] == "~delete":
            node = root
            for key in change[:-2]:
                node = node[key]
            del node[change[-1]]
            continue
        node = root
        for key in change[:-2]:
            node = node[key]
        node[change[-2]] = change[-1]
    return root


def base_profile() -> dict:
    profile = copy.deepcopy(PROFILES[FIXTURES["qualification_base"]["profile"]])
    profile["availability"] = copy.deepcopy(FIXTURES["qualification_base"]["profile_availability"])
    return profile


def pages_observations() -> dict:
    """Complete evidence for the two buckets that the SYN_Q0_PAGES pages prove: 10:00 to 10:10."""
    evidence = copy.deepcopy(FIXTURES["qualification_base"]["observations"])
    evidence["ingest"]["trades"] = 6
    evidence["corroboration"].update(sample_size=6, population_size=6)
    evidence["bucket_status_counts"] = {"COMPLETE_OCCUPIED": 2, "COMPLETE_EMPTY": 0, "INCOMPLETE": 0, "UNQUALIFIED": 0}
    evidence["bucket_window"] = {"start_utc": "2026-09-25T10:00:00Z", "end_utc": "2026-09-25T10:10:00Z"}
    return evidence


def real_pages_profile() -> dict:
    """A fixture profile with portable pages, labeled REAL_SOURCE only to exercise the projection rule."""
    profile = copy.deepcopy(PROFILES["SYN_Q0_PAGES"])
    profile["availability"] = copy.deepcopy(FIXTURES["qualification_base"]["profile_availability"])
    profile["evidence_class"] = "REAL_SOURCE"
    return profile


CLAIM_NAMES = ["BINDING_IDENTITY", "EVENT_AND_AMOUNT_MEANING", "HISTORY_COMPLETENESS_AND_ORDER",
               "POINT_IN_TIME_AVAILABILITY", "SCHEDULE_FEASIBILITY"]


class ProfileContract(unittest.TestCase):
    def test_every_case_reports_exactly_its_problems(self) -> None:
        for case in FIXTURES["profile_cases"]:
            with self.subTest(case["id"]):
                profile = apply_changes(copy.deepcopy(PROFILES[case["profile"]]), case["set"])
                self.assertEqual(sorted({p["code"] for p in profile_problems(profile)}), case["problems"])

    def test_profile_hash_ignores_key_order_and_follows_content(self) -> None:
        profile = copy.deepcopy(PROFILES["SYN_Q0"])
        shuffled = dict(reversed(list(profile.items())))
        self.assertEqual(profile_sha256(profile), profile_sha256(shuffled))
        changed = apply_changes(copy.deepcopy(profile), [["venue", "pool_address", "0x" + "ab" * 20]])
        self.assertNotEqual(profile_sha256(profile), profile_sha256(changed))

    def test_dataset_revision_ignores_page_order_and_follows_page_hashes(self) -> None:
        pages = PROFILES["SYN_Q0_PAGES"]["dataset"]["pages"]
        expected = PROFILES["SYN_Q0_PAGES"]["dataset"]["dataset_revision"]["manifest_sha256"]
        self.assertEqual(dataset_revision(pages), expected)
        self.assertEqual(dataset_revision(list(reversed(pages))), expected)
        altered = copy.deepcopy(pages)
        altered[1]["sha256"] = "0" * 64
        self.assertNotEqual(dataset_revision(altered), expected)

    def test_retained_report_profile_is_a_valid_profile(self) -> None:
        self.assertEqual(profile_problems(FIXTURES["retained_report"]["profile"]), [])


class BindingCompatibility(unittest.TestCase):
    def test_every_case_matches_hand_written_expectations(self) -> None:
        profile = PROFILES["SYN_Q0"]
        for case in FIXTURES["compat_cases"]:
            with self.subTest(case["id"]):
                other = {**research_binding_view(profile), **case["other"]}
                for key in case.get("delete", []):
                    del other[key]
                self.assertEqual(binding_incompatibilities(profile, other), case["codes"])

    def test_pool_native_order_is_kept_apart_from_the_base_quote_pair(self) -> None:
        q0, b0 = research_binding_view(PROFILES["SYN_Q0"]), research_binding_view(PROFILES["SYN_B0"])
        self.assertEqual(q0["token_order"], [q0["base_asset"], q0["quote_asset"]])
        self.assertEqual(b0["token_order"], [b0["base_asset"], b0["quote_asset"]])
        self.assertEqual(q0["token_order"], [FIXTURES["addresses"]["token1"], FIXTURES["addresses"]["token0"]])
        self.assertEqual(b0["token_order"], [FIXTURES["addresses"]["token0"], FIXTURES["addresses"]["token1"]])


class PerClaimQualification(unittest.TestCase):
    def run_case(self, case: dict) -> dict:
        profile = real_pages_profile() if case.get("profile") == "SYN_Q0_PAGES" else base_profile()
        if case.get("profile"):
            profile["evidence_class"] = "SYNTHETIC_FIXTURE"
        root = {"profile": profile, "observations": copy.deepcopy(FIXTURES["qualification_base"]["observations"])}
        apply_changes(root, case["set"])
        return qualify(root["profile"], root["observations"])

    def test_every_case_matches_hand_written_expectations(self) -> None:
        for case in FIXTURES["qualification_cases"]:
            with self.subTest(case["id"]):
                got = self.run_case(case)
                for name in CLAIM_NAMES:
                    self.assertEqual(got["claims"][name]["verdict"], case["expect"]["claims"].get(name, "QUALIFIED"), name)
                self.assertEqual(got["overall"], case["expect"]["overall"])

    def test_complete_evidence_still_leaves_execution_and_profit_unassessed(self) -> None:
        got = self.run_case(FIXTURES["qualification_cases"][0])
        self.assertEqual(got["scope"], "OFFLINE_CONTRACT_ONLY")
        self.assertEqual(got["not_assessed"], ["EXECUTION_ATTAINABILITY", "PROFITABILITY_OR_VALIDATION",
                                               "TRADER_NET_FILL_OR_PROFIT"])
        self.assertNotIn("EXECUTION_ATTAINABILITY", got["claims"])

    def test_a_missing_count_is_named_as_missing_not_as_a_mismatch(self) -> None:
        case = next(c for c in FIXTURES["qualification_cases"] if c["id"] == "Q58-rejected-total-missing")
        got = self.run_case(case)
        reasons = {(r["code"], r["kind"]) for r in got["claims"]["HISTORY_COMPLETENESS_AND_ORDER"]["reasons"]}
        self.assertEqual(reasons, {("REJECTED_TOTAL_NOT_REPORTED", "MISSING_EVIDENCE")})

    def test_every_reason_names_its_kind(self) -> None:
        got = self.run_case(FIXTURES["qualification_cases"][1])
        reasons = got["claims"]["BINDING_IDENTITY"]["reasons"]
        self.assertEqual([(r["code"], r["kind"]) for r in reasons], [("CHAIN_ID_FROM_DOCUMENTATION_ONLY", "ASSUMPTION")])

    def test_inputs_are_not_modified(self) -> None:
        profile, obs = base_profile(), copy.deepcopy(FIXTURES["qualification_base"]["observations"])
        before = copy.deepcopy((profile, obs))
        qualify(profile, obs)
        self.assertEqual((profile, obs), before)

    def test_retained_report_gets_a_limited_or_unresolved_verdict_never_qualified(self) -> None:
        report = FIXTURES["retained_report"]
        got = qualify(report["profile"], report["observations"])
        for name, verdict in report["expect"]["claims"].items():
            self.assertEqual(got["claims"][name]["verdict"], verdict, name)
        self.assertEqual(got["overall"], report["expect"]["overall"])
        for name, codes in report["expect"]["must_include_codes"].items():
            have = {r["code"] for r in got["claims"][name]["reasons"]}
            for code in codes:
                self.assertIn(code, have, f"{name} {code}")
        self.assertNotIn("QUALIFIED", {c["verdict"] for c in got["claims"].values()})

    def test_pipeline_output_feeds_the_qualifier(self) -> None:
        profile = copy.deepcopy(PROFILES["SYN_Q0_PAGES"])
        profile["availability"] = copy.deepcopy(FIXTURES["qualification_base"]["profile_availability"])
        logs = next(c for c in FIXTURES["bucket_cases"] if c["id"] == "K01-boundaries-close-and-volume")["logs"]
        evidence = copy.deepcopy(FIXTURES["qualification_base"]["observations"])
        for window, verdict in ((None, "LIMITED"),
                                ({"start_utc": "2026-09-25T10:00:00Z", "end_utc": "2026-09-25T10:10:00Z"}, "QUALIFIED")):
            with self.subTest(window=window):
                observed = history_observations(profile, logs, window)
                evidence.update(ingest=observed["ingest"], bucket_status_counts=observed["bucket_status_counts"],
                                bucket_window=observed["bucket_window"])
                evidence["corroboration"].update(sample_size=6, population_size=6)
                got = qualify(profile, evidence)
                self.assertEqual(got["claims"]["HISTORY_COMPLETENESS_AND_ORDER"]["verdict"], verdict)

    def test_status_counts_cover_every_status(self) -> None:
        counts = bucket_status_counts([{"status": "COMPLETE_EMPTY"}, {"status": "INCOMPLETE"}, {"status": "INCOMPLETE"}])
        self.assertEqual(counts, {"COMPLETE_OCCUPIED": 0, "COMPLETE_EMPTY": 1, "INCOMPLETE": 2, "UNQUALIFIED": 0})


class FailClosed(unittest.TestCase):
    JUNK = (None, [], "x", 1, True, {}, 1.5)

    def test_malformed_profile_sections_give_problems_not_crashes(self) -> None:
        profile = copy.deepcopy(PROFILES["SYN_Q0_PAGES"])
        for key in profile:
            for junk in self.JUNK:
                if (key, junk) == ("profile_id", "x"):
                    continue  # a short string is a valid profile id
                with self.subTest(key=key, junk=junk):
                    broken = copy.deepcopy(profile)
                    broken[key] = junk
                    self.assertTrue(profile_problems(broken))
        for key in profile["dataset"]:
            for junk in self.JUNK:
                with self.subTest(dataset=key, junk=junk):
                    broken = copy.deepcopy(profile)
                    broken["dataset"][key] = junk
                    self.assertTrue(profile_problems(broken))
        for index in (0, 1):
            for junk in self.JUNK:
                with self.subTest(token=index, junk=junk):
                    broken = copy.deepcopy(profile)
                    broken["pool_tokens"][index] = junk
                    self.assertTrue(profile_problems(broken))
        for junk in (None, [], "x", 1):
            self.assertTrue(profile_problems(junk))

    def test_profile_with_a_float_is_unresolved_not_a_crash(self) -> None:
        profile = copy.deepcopy(PROFILES["SYN_Q0_PAGES"])
        profile["dataset"]["query"]["definition"]["from_block"] = 100.5
        got = qualify(profile, copy.deepcopy(FIXTURES["qualification_base"]["observations"]))
        self.assertEqual(got["claims"]["BINDING_IDENTITY"]["verdict"], "UNRESOLVED")
        self.assertIsNone(got["profile_sha256"])
        with self.assertRaises(BindingNotEmittable):
            to_p02_binding(profile, got)

    def test_junk_in_any_profile_leaf_gives_problems_not_a_crash(self) -> None:
        def leaves(node: object, path: tuple = ()) -> list[tuple]:
            if isinstance(node, dict):
                return [p for k, v in node.items() for p in leaves(v, path + (k,))] or [path]
            if isinstance(node, list):
                return [p for i, v in enumerate(node) for p in leaves(v, path + (i,))] or [path]
            return [path]

        profile = copy.deepcopy(PROFILES["SYN_Q0_PAGES"])
        for path in leaves(profile):
            for junk in ([], {}, "x", None, True, -1, 1.5, "\uff12"):
                broken = copy.deepcopy(profile)
                node = broken
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = junk
                try:
                    profile_problems(broken)
                    qualify(broken, copy.deepcopy(FIXTURES["qualification_base"]["observations"]))
                except Exception as error:  # noqa: BLE001 - any crash is the failure
                    self.fail(f"crash at {path} with {junk!r}: {error!r}")

    def test_qualifier_never_passes_on_junk_observations(self) -> None:
        profile = base_profile()
        for junk in (None, [], "x", 1, {"binding": "READ", "ingest": 5, "corroboration": [1], "feasibility": "FEASIBLE"}):
            with self.subTest(junk=junk):
                self.assertEqual(qualify(profile, junk)["overall"], "UNRESOLVED")

    def test_result_binds_to_its_profile_and_evidence(self) -> None:
        profile, evidence = base_profile(), copy.deepcopy(FIXTURES["qualification_base"]["observations"])
        first = qualify(profile, evidence)
        evidence["ingest"]["trades"] += 1
        second = qualify(profile, evidence)
        self.assertEqual(first["profile_sha256"], second["profile_sha256"])
        self.assertNotEqual(first["observations_sha256"], second["observations_sha256"])

    def test_unusable_claims_are_rejected_before_counting(self) -> None:
        claim = copy.deepcopy(FIXTURES["feasibility_cases"][0]["claim"])
        segments = FIXTURES["feasibility_cases"][0]["segments"]
        half = copy.deepcopy(claim)
        half["partitions"][0]["required_control"] = None
        with self.assertRaises(InvalidInput) as caught:
            feasibility(half, segments, FIXTURES["feasibility_cases"][0]["availability"])
        self.assertEqual(caught.exception.code, "FLOOR_INCOMPLETE")
        for key in ("horizon_seconds", "reference_window_seconds"):
            bad = copy.deepcopy(claim)
            bad[key] = 0
            with self.assertRaises(InvalidInput) as caught:
                feasibility(bad, segments, FIXTURES["feasibility_cases"][0]["availability"])
            self.assertEqual(caught.exception.code, "CLAIM_VALUE")


class P02Projection(unittest.TestCase):
    def test_synthetic_profile_projects_to_an_accepted_unqualified_binding(self) -> None:
        profile = PROFILES["SYN_Q0"]
        binding = to_p02_binding(profile, qualify(profile, {}))
        P02["validate_record"]("ResearchBinding", binding)
        self.assertEqual((binding["evidence_class"], binding["qualification"]), ("SYNTHETIC_FIXTURE", "UNQUALIFIED"))
        self.assertEqual(binding["token_order"], [binding["base_asset"], binding["quote_asset"]])

    def test_only_a_fully_qualified_real_profile_projects_as_qualified(self) -> None:
        profile = real_pages_profile()
        result = qualify(profile, pages_observations())
        self.assertEqual(result["overall"], "QUALIFIED")
        binding = to_p02_binding(profile, result)
        P02["validate_record"]("ResearchBinding", binding)
        self.assertEqual((binding["evidence_class"], binding["qualification"]), ("QUALIFIED_SOURCE", "QUALIFIED"))

    def test_limited_or_unresolved_real_profile_cannot_project(self) -> None:
        report = FIXTURES["retained_report"]
        with self.assertRaises(BindingNotEmittable) as caught:
            to_p02_binding(report["profile"], qualify(report["profile"], report["observations"]))
        self.assertEqual(caught.exception.code, "VERDICT_UNRESOLVED")
        profile = real_pages_profile()
        profile["network"]["chain_id_source"] = "DOCUMENTATION"
        limited = qualify(profile, apply_changes({"o": pages_observations()},
                                                 [["o", "binding", "chain_id", "DOCUMENTATION"]])["o"])
        with self.assertRaises(BindingNotEmittable) as caught:
            to_p02_binding(profile, limited)
        self.assertEqual(caught.exception.code, "VERDICT_LIMITED")

    def test_projection_refuses_a_result_for_a_different_profile(self) -> None:
        a, b = PROFILES["SYN_Q0"], PROFILES["SYN_B0"]
        with self.assertRaises(BindingNotEmittable) as caught:
            to_p02_binding(a, qualify(b, {}))
        self.assertEqual(caught.exception.code, "RESULT_FOR_OTHER_PROFILE")


if __name__ == "__main__":
    unittest.main()
