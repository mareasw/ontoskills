#!/usr/bin/env python3
"""Tests for the claim verifier and repairer.

The model never runs here: every test pins a pure rule — how a claim resolves to
spans, what a repair may change, what the calibration reports. The one thing the
tests cannot prove is that the model's verdicts are good; the calibration run
against the recorded census measures that.

Run from the repository root:
    python -m unittest discover -s benchmark/docbench/tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCBENCH))

import verify_claims as vc  # noqa: E402


def span(span_id: str, start: int, text: str, doc: str = "D1", section=None) -> dict:
    return {
        "span_id": span_id,
        "doc_id": doc,
        "paragraph": text,
        "locator": {
            "kind": "html",
            "page": 1,
            "section_path": section or [],
            "url": "https://example.test/doc",
            "char_start": start,
            "char_end": start + len(text),
        },
    }


SPANS = [
    span("S0001", 0, "Article 4", section=["Chapter I"]),
    span("S0002", 10, "The Commission may terminate the appointment of the expert when:", section=["Chapter II"]),
    span("S0003", 80, "(a) there has been a material change in the circumstances.", section=["Chapter II"]),
    span("S0004", 150, "(b) the expert fails to maintain adequate measures.", section=["Chapter II"]),
    span("S0005", 210, "(c) a provider submitted a reasoned observation.", section=["Chapter II"]),
    span("S0006", 280, "The Commission shall publish an annual report.", section=["Chapter III"]),
    span("S0007", 340, "Unrelated filler text about nothing in particular.", section=["Chapter III"]),
]


def claim(claim_id: str, statement: str, spans: list[dict], **extra) -> dict:
    return {
        "claim_id": claim_id,
        "doc_id": "D1",
        "statement": statement,
        "modality": extra.pop("modality", "permission"),
        "evidence": [
            {"quote": s["paragraph"], "locator": dict(s["locator"]), "role": "supports"} for s in spans
        ],
        "schema_version": 2,
        **extra,
    }


class FakeCall:
    """Returns a fixed reply and records every prompt it was given."""

    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def __call__(self, prompt, system, max_tokens):
        self.prompts.append(prompt)
        self.systems.append(system)
        if callable(self.reply):
            return self.reply(prompt), {"input_tokens": 1, "output_tokens": 1}, "stop"
        return json.dumps(self.reply), {"input_tokens": 1, "output_tokens": 1}, "stop"


class SpanIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = vc.SpanIndex(SPANS)

    def test_resolve_by_locator(self) -> None:
        c = claim("D1-0001", "x", [SPANS[1]])
        self.assertEqual([s["span_id"] for s in self.index.resolve(c)], ["S0002"])

    def test_resolve_by_quote_when_locator_is_coarse(self) -> None:
        c = claim("D1-0001", "x", [SPANS[1]])
        c["evidence"][0]["locator"] = {"section_path": []}
        self.assertEqual([s["span_id"] for s in self.index.resolve(c)], ["S0002"])

    def test_neighbourhood_is_bounded_and_ordered(self) -> None:
        around = self.index.neighbourhood([SPANS[2]], radius=2)
        self.assertEqual([s["span_id"] for s in around], ["S0002", "S0004", "S0001", "S0005"])
        # radius 2 must not reach S0006 four positions away
        self.assertNotIn("S0006", [s["span_id"] for s in around])

    def test_neighbourhood_excludes_cited_spans(self) -> None:
        around = self.index.neighbourhood([SPANS[1], SPANS[2]], radius=1)
        ids = [s["span_id"] for s in around]
        self.assertIn("S0001", ids)
        self.assertIn("S0004", ids)
        self.assertNotIn("S0002", ids)
        self.assertNotIn("S0003", ids)

    def test_neighbourhood_is_capped(self) -> None:
        many = [span(f"S{i:04d}", i * 10, f"span number {i} with enough text") for i in range(1, 40)]
        index = vc.SpanIndex(many)
        around = index.neighbourhood([many[20]], radius=20)
        self.assertLessEqual(len(around), vc.MAX_CANDIDATES)


class PromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = vc.SpanIndex(SPANS)

    def test_audit_item_carries_statement_quote_and_section_only(self) -> None:
        c = claim("D1-0002", "The Commission may terminate the appointment.", [SPANS[1]], actor="Commission", conditions=["x"])
        text = vc.audit_item(c, self.index.resolve(c))
        self.assertIn("The Commission may terminate the appointment.", text)
        self.assertIn(SPANS[1]["paragraph"], text)
        self.assertIn("Chapter II", text)
        # The audit must not be told the structured actor/conditions: they are
        # the very inference under test.
        self.assertNotIn("actor:", text)
        self.assertNotIn("conditions:", text)

    def test_repair_item_offers_current_and_candidate_spans(self) -> None:
        c = claim("D1-0002", "The Commission may terminate for (a), (b) and (c).", [SPANS[1]], actor="Commission")
        current = self.index.resolve(c)
        text = vc.repair_item(c, current, self.index.neighbourhood(current))
        self.assertIn("[CURRENT S0002]", text)
        self.assertIn("[CANDIDATE S0003]", text)
        self.assertIn("actor:", text)


class ApplyRepairsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = vc.SpanIndex(SPANS)

    def test_rewrite_changes_only_the_statement(self) -> None:
        c = claim("D1-0002", "The Commission must terminate.", [SPANS[1]])
        repairs = {"D1-0002": {"action": "rewrite", "statement": "The Commission may terminate the appointment."}}
        out, report = vc.apply_repairs([c], repairs, self.index)
        self.assertEqual(out[0]["statement"], "The Commission may terminate the appointment.")
        self.assertEqual(out[0]["evidence"], c["evidence"])
        self.assertEqual(report["rewritten"], 1)

    def test_rewrite_is_rejected_when_empty_or_identical(self) -> None:
        c = claim("D1-0002", "The Commission may terminate.", [SPANS[1]])
        for statement in ("", "   ", c["statement"], "Yes."):
            out, report = vc.apply_repairs(
                [c], {"D1-0002": {"action": "rewrite", "statement": statement}}, self.index
            )
            self.assertEqual(out[0]["statement"], c["statement"])
            self.assertEqual(report["rejected"], 1)

    def test_reevidence_keeps_the_old_statement_when_the_rewrite_is_a_stub(self) -> None:
        c = claim("D1-0002", "The Commission may terminate when (a) or (b) applies.", [SPANS[1]])
        repairs = {
            "D1-0002": {
                "action": "reevidence",
                "statement": "N/A",
                "evidence_span_ids": ["S0003"],
            }
        }
        out, report = vc.apply_repairs([c], repairs, self.index)
        self.assertEqual(out[0]["statement"], c["statement"])
        self.assertEqual([item["quote"] for item in out[0]["evidence"]], [SPANS[2]["paragraph"]])
        self.assertEqual(report["reevidenced"], 1)
        self.assertEqual(report["rewritten"], 0)

    def test_reevidence_uses_verbatim_span_text(self) -> None:
        c = claim("D1-0002", "The Commission may terminate when (a), (b) or (c) applies.", [SPANS[1]])
        repairs = {"D1-0002": {"action": "reevidence", "evidence_span_ids": ["S0002", "S0003", "S0004", "S0005"]}}
        out, report = vc.apply_repairs([c], repairs, self.index)
        self.assertEqual(report["reevidenced"], 1)
        quotes = [item["quote"] for item in out[0]["evidence"]]
        self.assertEqual(quotes, [SPANS[i]["paragraph"] for i in (1, 2, 3, 4)])
        # Every quote is a span paragraph, so check_claims still passes.
        self.assertTrue(all(q in {s["paragraph"] for s in SPANS} for q in quotes))

    def test_reevidence_rejects_span_outside_the_neighbourhood(self) -> None:
        c = claim("D1-0002", "The Commission shall publish an annual report.", [SPANS[1]])
        repairs = {"D1-0002": {"action": "reevidence", "evidence_span_ids": ["S9999"]}}
        out, report = vc.apply_repairs([c], repairs, self.index)
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(out[0]["evidence"], c["evidence"])

    def test_reevidence_distance_limit_is_enforced(self) -> None:
        c = claim("D1-0002", "The Commission shall publish an annual report.", [SPANS[1]])
        # S0006 is four positions after S0002: outside the radius.
        repairs = {"D1-0002": {"action": "reevidence", "evidence_span_ids": ["S0006"]}}
        _out, report = vc.apply_repairs([c], repairs, self.index)
        self.assertEqual(report["rejected"], 1)

    def test_drop_removes_the_claim(self) -> None:
        c = claim("D1-0002", "The Commission must terminate.", [SPANS[1]])
        out, report = vc.apply_repairs([c], {"D1-0002": {"action": "drop"}}, self.index)
        self.assertEqual(out, [])
        self.assertEqual(report["dropped_ids"], ["D1-0002"])

    def test_unknown_action_leaves_the_claim_untouched(self) -> None:
        c = claim("D1-0002", "The Commission must terminate.", [SPANS[1]])
        out, report = vc.apply_repairs([c], {"D1-0002": {"action": "invent"}}, self.index)
        self.assertEqual(out, [c])
        self.assertEqual(report["unchanged"], 1)


class ConflictPruneTest(unittest.TestCase):
    def test_links_to_missing_claims_are_removed(self) -> None:
        a = claim("D1-0001", "a", [SPANS[0]], conflicts_with=["D1-0002", "D1-0003"])
        b = claim("D1-0002", "b", [SPANS[1]], conflicts_with=["D1-0001"])
        removed = vc.prune_conflicts([a])
        self.assertEqual(removed, 2)
        self.assertNotIn("conflicts_with", a)
        self.assertEqual(b["conflicts_with"], ["D1-0001"])


class AuditPassTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = vc.SpanIndex(SPANS)
        self.claims = [claim("D1-0001", "a", [SPANS[0]]), claim("D1-0002", "b", [SPANS[1]])]

    def test_usage_is_accumulated_across_calls(self) -> None:
        call = FakeCall([
            {"claim_id": "D1-0001", "verdict": "ok", "note": "-"},
            {"claim_id": "D1-0002", "verdict": "ok", "note": "-"},
        ])
        usage: dict = {}
        vc.audit_claims(self.claims, self.index, call, batch_size=1, usage=usage)
        self.assertEqual(usage, {"calls": 2, "input_tokens": 2, "output_tokens": 2})

    def test_verdicts_are_recorded_and_cached(self) -> None:
        call = FakeCall([
            {"claim_id": "D1-0001", "verdict": "ok", "note": "-"},
            {"claim_id": "D1-0002", "verdict": "weak", "note": "actor missing"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "audit.jsonl"
            audit = vc.audit_claims(self.claims, self.index, call, cache_path=cache, batch_size=2)
            self.assertEqual(audit["D1-0001"]["verdict"], "ok")
            self.assertEqual(audit["D1-0002"]["verdict"], "weak")
            self.assertEqual(len(cache.read_text().splitlines()), 2)

            # A resumed run asks the model nothing.
            again = vc.audit_claims(self.claims, self.index, FakeCall([]), cache_path=cache, resume=True)
            self.assertEqual(again["D1-0002"]["verdict"], "weak")

    def test_missing_verdict_does_not_become_ok(self) -> None:
        call = FakeCall([{"claim_id": "D1-0001", "verdict": "ok", "note": "-"}])
        audit = vc.audit_claims(self.claims, self.index, call, batch_size=2)
        self.assertEqual(audit["D1-0001"]["verdict"], "ok")
        self.assertNotEqual(audit["D1-0002"]["verdict"], "ok")  # unstated is never a pass

    def test_omitted_claims_are_re_asked_before_they_fail(self) -> None:
        seen: list[str] = []

        def call(prompt, system, max_tokens):
            seen.append(prompt)
            if "D1-0002" in prompt:
                rows = [{"claim_id": "D1-0002", "verdict": "ok", "note": "-"}]
            else:
                rows = [{"claim_id": "D1-0001", "verdict": "ok", "note": "-"}]
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        audit = vc.audit_claims(self.claims, self.index, call, batch_size=2)
        self.assertEqual(audit["D1-0001"]["verdict"], "ok")
        self.assertEqual(audit["D1-0002"]["verdict"], "ok")
        self.assertEqual(len(seen), 3)  # batch, then the omitted claim alone

    def test_unknown_verdict_string_is_not_ok(self) -> None:
        call = FakeCall([{"claim_id": "D1-0001", "verdict": "excellent", "note": ""}])
        audit = vc.audit_claims(self.claims[:1], self.index, call, batch_size=1)
        self.assertEqual(audit["D1-0001"]["verdict"], "weak")

    def test_malformed_reply_is_salvaged(self) -> None:
        reply = '[{"claim_id": "D1-0001", "verdict": "ok", "note": "-"}{"claim_id": "D1-0002", "verdict": "no", "note": "x"}]'
        call = FakeCall(lambda _p: reply)
        audit = vc.audit_claims(self.claims, self.index, call, batch_size=2)
        self.assertEqual(audit["D1-0001"]["verdict"], "ok")
        self.assertEqual(audit["D1-0002"]["verdict"], "no")

    def test_client_rejection_splits_the_batch_instead_of_aborting(self) -> None:
        def call(prompt, system, max_tokens):
            if "D1-0001" in prompt and "D1-0002" in prompt:
                raise SystemExit("HTTP 400: upstream rejected the request")
            cid = "D1-0001" if "D1-0001" in prompt else "D1-0002"
            return json.dumps([{"claim_id": cid, "verdict": "ok", "note": "-"}]), {
                "input_tokens": 1, "output_tokens": 1,
            }, "stop"

        audit = vc.audit_claims(self.claims, self.index, call, batch_size=2)
        self.assertEqual(audit["D1-0001"]["verdict"], "ok")
        self.assertEqual(audit["D1-0002"]["verdict"], "ok")

    def test_persistent_failure_aborts_after_splitting(self) -> None:
        seen: list[str] = []

        def call(prompt, system, max_tokens):
            seen.append(prompt)
            raise SystemExit("model call failed after retries: HTTP 503")

        with self.assertRaises(SystemExit) as caught:
            vc.audit_claims(self.claims, self.index, call, batch_size=2)
        self.assertIn("--resume", str(caught.exception))
        self.assertEqual(len(seen), 3)  # the pair, then each claim alone

    def test_dead_batch_still_judges_the_surviving_half(self) -> None:
        claims = [claim(f"D1-000{i}", f"statement {i}", [SPANS[1]]) for i in range(1, 5)]

        def call(prompt, system, max_tokens):
            if "D1-0003" in prompt:
                raise SystemExit("model call failed after retries: HTTP 503")
            rows = [
                {"claim_id": f"D1-000{i}", "verdict": "ok", "note": "-"}
                for i in range(1, 5) if f"D1-000{i}" in prompt
            ]
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "audit.jsonl"
            with self.assertRaises(SystemExit) as caught:
                vc.audit_claims(claims, self.index, call, cache_path=cache, batch_size=2)
            self.assertIn("--resume", str(caught.exception))
            cached = {row["claim_id"] for row in vc.load_jsonl(cache)}
            # The pair splits; only the claim that fails alone stays unresolved.
            self.assertEqual(cached, {"D1-0001", "D1-0002", "D1-0004"})


class RepairPassTest(unittest.TestCase):
    def test_repair_batches_by_claim_count(self) -> None:
        index = vc.SpanIndex(SPANS)
        claims = [claim(f"D1-000{i}", f"statement {i}", [SPANS[1]]) for i in range(1, 6)]
        call = FakeCall(lambda prompt: json.dumps([
            {"claim_id": f"D1-000{i}", "action": "rewrite", "statement": f"fixed {i}"}
            for i in range(1, 6)
            if f"D1-000{i}" in prompt
        ]))
        repairs = vc.repair_claims(claims, index, call, batch_size=2)
        self.assertEqual(len(repairs), 5)
        self.assertEqual(len(call.prompts), 3)
        self.assertEqual(repairs["D1-0003"]["statement"], "fixed 3")

    def test_rejected_batch_splits_and_repairs_every_claim(self) -> None:
        index = vc.SpanIndex(SPANS)
        claims = [claim("D1-0001", "a", [SPANS[1]]), claim("D1-0002", "b", [SPANS[1]])]

        def call(prompt, system, max_tokens):
            if "D1-0001" in prompt and "D1-0002" in prompt:
                raise SystemExit("model call failed after retries: HTTP 503")
            cid = "D1-0001" if "D1-0001" in prompt else "D1-0002"
            return json.dumps([{"claim_id": cid, "action": "drop"}]), {
                "input_tokens": 1, "output_tokens": 1,
            }, "stop"

        repairs = vc.repair_claims(claims, index, call, batch_size=2)
        self.assertEqual(repairs["D1-0001"]["action"], "drop")
        self.assertEqual(repairs["D1-0002"]["action"], "drop")

    def test_omitted_repair_is_asked_again_not_invented(self) -> None:
        index = vc.SpanIndex(SPANS)
        claims = [claim("D1-0001", "a", [SPANS[1]]), claim("D1-0002", "b", [SPANS[1]])]

        def call(prompt, system, max_tokens):
            rows = [{"claim_id": "D1-0001", "action": "drop"}] if "D1-0002" not in prompt else []
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        repairs = vc.repair_claims(claims, index, call, batch_size=2)
        self.assertEqual(repairs["D1-0001"]["action"], "drop")
        # The claim the model never answered has no action, so nothing is applied.
        self.assertEqual(repairs["D1-0002"]["action"], "")
        self.assertIn("omitted", repairs["D1-0002"]["note"])


class ConcurrencyTest(unittest.TestCase):
    """Batches are independent; running them side by side must not change them."""

    def setUp(self) -> None:
        self.index = vc.SpanIndex(SPANS)
        self.claims = [claim(f"D1-000{i}", f"statement {i}", [SPANS[1]]) for i in range(1, 7)]

    def _call(self, active: dict | None = None):
        guard = threading.Lock()

        def call(prompt, system, max_tokens):
            if active is not None:
                with guard:
                    active["now"] += 1
                    active["peak"] = max(active["peak"], active["now"])
            time.sleep(0.02)
            if active is not None:
                with guard:
                    active["now"] -= 1
            rows = [
                {"claim_id": f"D1-000{i}", "verdict": "ok", "note": "-"}
                for i in range(1, 7)
                if f"D1-000{i}" in prompt
            ]
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        return call

    def test_concurrent_audit_gives_the_same_verdicts(self) -> None:
        audit = vc.audit_claims(self.claims, self.index, self._call(), batch_size=1, concurrency=3)
        self.assertEqual(set(audit), {c["claim_id"] for c in self.claims})
        self.assertTrue(all(row["verdict"] == "ok" for row in audit.values()))

    def test_batches_really_run_in_flight(self) -> None:
        active = {"now": 0, "peak": 0}
        vc.audit_claims(self.claims, self.index, self._call(active), batch_size=1, concurrency=3)
        self.assertGreater(active["peak"], 1)

    def test_concurrent_cache_stays_one_json_object_per_line(self) -> None:
        usage: dict = {}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "audit.jsonl"
            vc.audit_claims(
                self.claims, self.index, self._call(),
                cache_path=cache, batch_size=1, concurrency=4, usage=usage,
            )
            lines = cache.read_text().splitlines()
            self.assertEqual(len(lines), len(self.claims))
            for line in lines:
                self.assertIn("claim_id", json.loads(line))
        self.assertEqual(usage["calls"], len(self.claims))

    def test_dead_batch_under_concurrency_keeps_the_others_cached(self) -> None:
        def call(prompt, system, max_tokens):
            if "D1-0003" in prompt:
                raise SystemExit("model call failed after retries: HTTP 503")
            rows = [
                {"claim_id": f"D1-000{i}", "verdict": "ok", "note": "-"}
                for i in range(1, 7)
                if f"D1-000{i}" in prompt
            ]
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "audit.jsonl"
            with self.assertRaises(SystemExit) as caught:
                vc.audit_claims(self.claims, self.index, call, cache_path=cache, batch_size=1, concurrency=3)
            self.assertIn("--resume", str(caught.exception))
            cached = {row["claim_id"] for row in vc.load_jsonl(cache)}
            self.assertEqual(cached, {f"D1-000{i}" for i in (1, 2, 4, 5, 6)})


class PipelineTest(unittest.TestCase):
    def test_pipeline_repairs_then_reaudits_and_drops_residual(self) -> None:
        index = vc.SpanIndex(SPANS)
        claims = [
            claim("D1-0001", "good", [SPANS[0]]),
            claim("D1-0002", "The Commission must terminate.", [SPANS[1]]),
            claim("D1-0003", "Hopeless claim with no evidence at all.", [SPANS[6]]),
        ]

        def call(prompt: str, system: str, max_tokens: int):
            if "evidence auditor" in system:
                rows = []
                if "D1-0001" in prompt:
                    rows.append({"claim_id": "D1-0001", "verdict": "ok"})
                if "D1-0002" in prompt:
                    fixed = "The Commission may terminate the appointment." in prompt
                    rows.append({"claim_id": "D1-0002", "verdict": "ok" if fixed else "weak"})
                if "D1-0003" in prompt:
                    rows.append({"claim_id": "D1-0003", "verdict": "no"})
                return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"
            rows = []
            if "D1-0002" in prompt:
                rows.append(
                    {"claim_id": "D1-0002", "action": "rewrite",
                     "statement": "The Commission may terminate the appointment."}
                )
            if "D1-0003" in prompt:
                rows.append({"claim_id": "D1-0003", "action": "drop"})
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        with tempfile.TemporaryDirectory() as tmp:
            out, report = vc.run_pipeline(
                claims,
                index,
                call,
                work=Path(tmp),
                rounds=2,
                audit_batch=5,
                repair_batch=5,
                keep_residual=False,
            )
        self.assertEqual([c["claim_id"] for c in out], ["D1-0001", "D1-0002"])
        self.assertEqual(out[1]["statement"], "The Commission may terminate the appointment.")
        self.assertEqual(report["final"]["claims"], 2)
        self.assertEqual(report["final"]["ok"], 2)
        self.assertEqual(report["rounds"][0]["rewritten"], 1)
        self.assertEqual(report["rounds"][0]["dropped"], 1)
        self.assertEqual(report["residual_dropped"], 0)
        self.assertEqual(report["kept_weak"], 0)

    def test_pipeline_keeps_weak_residual_and_drops_only_hard_failures(self) -> None:
        """PREFLIGHT §9.2: `weak` costs citation quality, not truth, so it ships."""
        index = vc.SpanIndex(SPANS)
        claims = [
            claim("D1-0001", "good", [SPANS[0]]),
            claim("D1-0002", "The Commission must terminate.", [SPANS[1]]),
            claim("D1-0003", "Hopeless claim with no evidence at all.", [SPANS[6]]),
        ]
        verdicts = {"D1-0001": "ok", "D1-0002": "weak", "D1-0003": "no"}

        def call(prompt: str, system: str, max_tokens: int):
            rows = [{"claim_id": cid, "verdict": v} for cid, v in verdicts.items() if cid in prompt]
            if "evidence auditor" not in system:
                rows = [
                    {"claim_id": "D1-0002", "action": "rewrite",
                     "statement": "The Commission may terminate the appointment of the expert."},
                    {"claim_id": "D1-0003", "action": "rewrite",
                     "statement": "Filler text about nothing in particular and more."},
                ]
                rows = [row for row in rows if row["claim_id"] in prompt]
            return json.dumps(rows), {"input_tokens": 1, "output_tokens": 1}, "stop"

        with tempfile.TemporaryDirectory() as tmp:
            out, report = vc.run_pipeline(
                claims, index, call, work=Path(tmp), rounds=2,
                audit_batch=5, repair_batch=5, verbose=False,
            )
        self.assertEqual([c["claim_id"] for c in out], ["D1-0001", "D1-0002"])
        self.assertEqual(report["residual_ids"], ["D1-0002", "D1-0003"])
        self.assertEqual(report["residual_dropped"], 1)
        self.assertEqual(report["kept_weak"], 1)
        self.assertEqual(report["kept_weak_ids"], ["D1-0002"])
        self.assertEqual(report["final"]["claims"], 2)
        self.assertEqual(report["final"]["ok"], 1)
        self.assertEqual(report["final"]["weak"], 1)
        self.assertEqual(report["final"]["no"], 0)

    def test_verdict_of_never_reads_silence_as_a_pass(self) -> None:
        claim_ = claim("D1-0001", "good", [SPANS[0]])
        self.assertEqual(vc.verdict_of(claim_, {}), "weak")
        self.assertEqual(vc.verdict_of(claim_, {"D1-0001": {"verdict": "maybe"}}), "weak")
        self.assertEqual(vc.verdict_of(claim_, {"D1-0001": {"verdict": "no"}}), "no")
        self.assertEqual(vc.verdict_of(claim_, {"D1-0001": {"verdict": "ok"}}), "ok")


class CalibrationTest(unittest.TestCase):
    def test_matrix_and_stop_rule_numbers(self) -> None:
        claims = [claim(f"D1-{i:04d}", "s", [SPANS[0]]) for i in range(1, 11)]
        known = {f"D1-{i:04d}": ("weak" if i <= 4 else "ok") for i in range(1, 11)}
        audit = {
            **{f"D1-{i:04d}": {"verdict": "weak"} for i in range(1, 4)},
            "D1-0004": {"verdict": "ok"},   # missed
            "D1-0005": {"verdict": "no"},   # false positive
            **{f"D1-{i:04d}": {"verdict": "ok"} for i in range(6, 11)},
        }
        report = vc.calibration_report(claims, audit, known)
        self.assertEqual(report["known_bad"], 4)
        self.assertEqual(report["caught"], 3)
        self.assertEqual(report["missed"], ["D1-0004"])
        self.assertEqual(report["false_positives"], ["D1-0005"])

    def test_sample_includes_every_known_non_ok(self) -> None:
        claims = [claim(f"D1-{i:04d}", "s", [SPANS[0]]) for i in range(1, 101)]
        known = {c["claim_id"]: ("ok" if i % 2 else "weak") for i, c in enumerate(claims)}
        sample = vc.calibration_sample(claims, known, ok_target=10)
        ids = {c["claim_id"] for c in sample}
        self.assertTrue(all(cid in ids for cid, verdict in known.items() if verdict != "ok"))
        self.assertEqual(sum(1 for c in sample if known[c["claim_id"]] == "ok"), 10)


class StatementTest(unittest.TestCase):
    def test_clean_statement_collapses_whitespace_and_quotes(self) -> None:
        self.assertEqual(vc.clean_statement('  "The  Commission\n may act." '), "The Commission may act.")


if __name__ == "__main__":
    unittest.main()
