"""s3_axis.py — Stage S3: Rule layer with three axes (Polarity, Identifiers, Numeric) and Polarity Ledger."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import GradingConfig, RulesConfig
from ..models import AxisResult, Candidate, Unit


class RuleEvaluator:
    def __init__(self, rules: RulesConfig) -> None:
        self.rules = rules

        # Precompile polarity regexes
        self.polarity_reject_patterns = [
            re.compile(pat, re.IGNORECASE) for pat in rules.polarity["reject"]
        ]
        self.polarity_accept_patterns = [
            re.compile(pat, re.IGNORECASE) for pat in rules.polarity["accept"]
        ]

        # Precompile transition pattern
        all_statuses = set()
        for s_list in rules.status_sets.values():
            all_statuses.update(s_list)
        status_regex_part = "|".join(re.escape(s) for s in sorted(all_statuses, key=len, reverse=True))
        trans_pat_str = rules.transition_pattern.replace("(STATUS)", f"({status_regex_part})")
        self.transition_regex = re.compile(trans_pat_str, re.IGNORECASE)

        # Token vocabulary
        self.token_statuses = {s.lower() for s in all_statuses}
        self.token_payment_methods = {pm.lower() for pm in rules.payment_methods}
        self.token_entity_nouns = {en.lower() for en in rules.entity_nouns}
        self.token_roles = set(rules.roles)  # case-sensitive

        # Cardinality phrases
        self.cardinality_canonical = set(rules.cardinality_phrases.get("canonical", []))
        self.cardinality_aliases = rules.cardinality_phrases.get("aliases", {})
        all_card = list(self.cardinality_canonical) + list(self.cardinality_aliases.keys())
        card_regex_part = "|".join(re.escape(c) for c in sorted(all_card, key=len, reverse=True))
        self.cardinality_regex = re.compile(rf"\b({card_regex_part})\b", re.IGNORECASE)

        # Numeric regexes
        num_units = rules.numeric.get("units", [])
        num_units_pat = "|".join(re.escape(u) for u in sorted(num_units, key=len, reverse=True))
        self.num_regex = re.compile(rf"(\d+(?:\.\d+)?)\s*({num_units_pat})", re.IGNORECASE)
        self.num_direction_markers = rules.numeric.get("direction_markers", [])
        self.num_literals = rules.numeric.get("literals", [])

    # --- Axis 1: Polarity ---
    def classify_polarity(self, text: str) -> str:
        for pat in self.polarity_reject_patterns:
            if pat.search(text):
                return "reject"
        for pat in self.polarity_accept_patterns:
            if pat.search(text):
                return "accept"
        return "none"

    def evaluate_axis1_polarity(self, gold_text: str, gen_text: str) -> tuple[str, str | None]:
        """Returns (outcome, detail). Outcome is 'pass', 'FAIL', 'MANUAL', or 'not_applicable'."""
        gold_pol = self.classify_polarity(gold_text)
        if gold_pol == "none":
            return "not_applicable", None

        gen_pol = self.classify_polarity(gen_text)
        if gen_pol == gold_pol:
            return "pass", None
        elif gen_pol in ("reject", "accept"):
            return "FAIL", f"gold={gold_pol} gen={gen_pol}"
        else:
            return "MANUAL", f"gold={gold_pol} gen=none"

    # --- Axis 2: Identifiers & Direction ---
    def extract_transitions(self, text: str) -> set[tuple[str, str]]:
        found = set()
        for m in self.transition_regex.finditer(text):
            src, dst = m.group(1).lower(), m.group(2).lower()
            found.add((src, dst))
        return found

    def extract_identifier_tokens(self, text: str) -> set[str]:
        words = re.findall(r"\b[A-Za-z0-9_\-\.]+\b", text)
        matched = set()
        for w in words:
            # Check case-sensitive roles
            if w in self.token_roles:
                matched.add(w)
            w_lower = w.lower()
            if w_lower in self.token_statuses:
                matched.add(w_lower)
            if w_lower in self.token_payment_methods:
                matched.add(w_lower)
            if w_lower in self.token_entity_nouns:
                matched.add(w_lower)
        return matched

    def extract_cardinality(self, text: str) -> Counter[str]:
        counter = Counter()
        for m in self.cardinality_regex.finditer(text):
            phrase = m.group(1).lower()
            canonical = self.cardinality_aliases.get(phrase, phrase)
            counter[canonical] += 1
        return counter

    def evaluate_axis2_identifiers(self, gold_text: str, gen_text: str) -> tuple[bool, str | None]:
        # 2a. Transitions
        gold_trans = self.extract_transitions(gold_text)
        if gold_trans:
            gen_trans = self.extract_transitions(gen_text)
            if gen_trans != gold_trans:
                return False, f"subcheck=2a transitions: gold={sorted(gold_trans)} gen={sorted(gen_trans)}"

        # 2b. Identifier tokens
        gold_tokens = self.extract_identifier_tokens(gold_text)
        if gold_tokens:
            gen_tokens = self.extract_identifier_tokens(gen_text)
            if gen_tokens != gold_tokens:
                diff_gold = gold_tokens - gen_tokens
                diff_gen = gen_tokens - gold_tokens
                detail_parts = []
                if diff_gold:
                    detail_parts.append(f"missing={sorted(diff_gold)}")
                if diff_gen:
                    detail_parts.append(f"extra={sorted(diff_gen)}")
                return False, f"subcheck=2b tokens: {'; '.join(detail_parts)}"

        # 2c. Cardinality
        gold_card = self.extract_cardinality(gold_text)
        if gold_card:
            gen_card = self.extract_cardinality(gen_text)
            if gen_card != gold_card:
                return False, f"subcheck=2c cardinality: gold={dict(gold_card)} gen={dict(gen_card)}"

        return True, None

    # --- Axis 3: Numeric Values & Thresholds ---
    def _normalize_unit(self, unit: str) -> str:
        u = unit.lower()
        if u.endswith("s") and u not in ("s", "%"):
            u = u[:-1]
        return u

    def extract_numeric_features(self, text: str) -> tuple[set[tuple[str, str]], set[str], set[str]]:
        values = set()
        for m in self.num_regex.finditer(text):
            val_str, unit_str = m.group(1), self._normalize_unit(m.group(2))
            values.add((val_str, unit_str))

        literals = set()
        for lit in self.num_literals:
            if lit.lower() in text.lower():
                literals.add(lit)

        directions = set()
        for dm in self.num_direction_markers:
            if re.search(rf"\b{re.escape(dm)}\b", text, re.IGNORECASE):
                directions.add(dm.lower())

        return values, literals, directions

    def evaluate_axis3_numeric(self, gold_text: str, gen_text: str, gold_kind: str) -> tuple[bool, str | None]:
        if gold_kind != "nfr":
            return True, None

        g_vals, g_lits, g_dirs = self.extract_numeric_features(gold_text)
        if not g_vals and not g_lits:
            # e.g. NFR-04 has no numeric threshold
            return True, None

        s_vals, s_lits, s_dirs = self.extract_numeric_features(gen_text)

        # Values mismatch
        if not g_vals.issubset(s_vals):
            missing_vals = g_vals - s_vals
            return False, f"missing values: {sorted(missing_vals)}"

        # Literals mismatch (e.g. TLS 1.2)
        if not g_lits.issubset(s_lits):
            missing_lits = g_lits - s_lits
            return False, f"missing literals: {sorted(missing_lits)}"

        # Direction markers mismatch
        if not g_dirs.issubset(s_dirs):
            missing_dirs = g_dirs - s_dirs
            return False, f"missing direction markers: {sorted(missing_dirs)}"

        return True, None


def load_polarity_ledger(ledger_path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Loads existing polarity ledger rows keyed by (gold_id, gen_id)."""
    if not ledger_path.is_file():
        return {}
    ledger_rows = {}
    with ledger_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("gold_id", ""), row.get("gen_id", ""))
            ledger_rows[key] = row
    return ledger_rows


def append_to_polarity_ledger(
    ledger_path: Path,
    new_rows: list[dict[str, str]],
) -> None:
    """Appends question rows to polarity_ledger.csv."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "gold_id", "gen_id", "cosine", "gold_text", "gen_text",
        "verdict", "reviewer", "timestamp", "note"
    ]
    file_exists = ledger_path.is_file()

    with ledger_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in new_rows:
            writer.writerow(r)


def run_s3(
    units_file: Path,
    candidates_file: Path,
    out_dir: Path,
    review_dir: Path,
    config: GradingConfig,
    rules: RulesConfig,
    on_pending: str = "halt",  # 'halt' or 'provisional'
) -> tuple[Path, str, int]:
    """Execute Stage S3. Returns (out_path, stage_status, pending_count)."""
    units_data = json.loads(units_file.read_text(encoding="utf-8"))
    gold_by_id = {u["unit_id"]: u for u in units_data.get("gold", [])}
    gen_by_id = {u["unit_id"]: u for u in units_data.get("gen", [])}

    candidates_raw = json.loads(candidates_file.read_text(encoding="utf-8"))
    candidates = [c for c in candidates_raw if c.get("excluded") is None]

    evaluator = RuleEvaluator(rules)
    ledger_path = review_dir / "polarity_ledger.csv"
    existing_ledger = load_polarity_ledger(ledger_path)

    results: list[AxisResult] = []
    new_ledger_rows: list[dict[str, str]] = []
    pending_count = 0

    for cand in candidates:
        gid = cand["gold_id"]
        sid = cand["gen_id"]
        cosine = cand.get("cosine", 0.0)

        g_unit = gold_by_id.get(gid)
        s_unit = gen_by_id.get(sid)
        if not g_unit or not s_unit:
            continue

        g_text = g_unit["text_raw"]
        s_text = s_unit["text_raw"]
        g_kind = g_unit["kind"]

        # 1. Axis 1 - Polarity
        ax1_outcome, ax1_detail = evaluator.evaluate_axis1_polarity(g_text, s_text)
        if ax1_outcome == "FAIL":
            results.append(AxisResult(
                gold_id=gid, gen_id=sid, verdict="FAIL",
                failed_axis="polarity", detail=ax1_detail, source="rule"
            ))
            continue

        # 2. Axis 2 - Identifiers
        ax2_pass, ax2_detail = evaluator.evaluate_axis2_identifiers(g_text, s_text)
        if not ax2_pass:
            results.append(AxisResult(
                gold_id=gid, gen_id=sid, verdict="FAIL",
                failed_axis="identifier", detail=ax2_detail, source="rule"
            ))
            continue

        # 3. Axis 3 - Numeric
        ax3_pass, ax3_detail = evaluator.evaluate_axis3_numeric(g_text, s_text, g_kind)
        if not ax3_pass:
            results.append(AxisResult(
                gold_id=gid, gen_id=sid, verdict="FAIL",
                failed_axis="numeric", detail=ax3_detail, source="rule"
            ))
            continue

        # If Axis 1 was MANUAL:
        if ax1_outcome == "MANUAL":
            ledger_entry = existing_ledger.get((gid, sid))
            ledger_verdict = (ledger_entry.get("verdict") or "").strip().upper() if ledger_entry else ""

            if ledger_verdict in ("PASS", "FAIL"):
                results.append(AxisResult(
                    gold_id=gid, gen_id=sid, verdict=ledger_verdict,  # type: ignore
                    failed_axis=None if ledger_verdict == "PASS" else "polarity",
                    detail=ledger_entry.get("note") or "Adjudicated via polarity ledger",
                    source="ledger",
                ))
            else:
                # Needs human review
                pending_count += 1
                if on_pending == "provisional":
                    subst_verdict = "FAIL" if config.manual_default == "not_covered" else "PASS"
                    results.append(AxisResult(
                        gold_id=gid, gen_id=sid, verdict=subst_verdict,
                        failed_axis="polarity", detail=f"Provisional default ({config.manual_default})",
                        source="default",
                    ))
                else:
                    results.append(AxisResult(
                        gold_id=gid, gen_id=sid, verdict="MANUAL",
                        failed_axis="polarity", detail=ax1_detail,
                        source="rule",
                    ))

                if not ledger_entry:
                    new_ledger_rows.append({
                        "gold_id": gid,
                        "gen_id": sid,
                        "cosine": str(round(cosine, 4)),
                        "gold_text": g_text,
                        "gen_text": s_text,
                        "verdict": "",
                        "reviewer": "",
                        "timestamp": "",
                        "note": "",
                    })
        else:
            # All axes passed!
            results.append(AxisResult(
                gold_id=gid, gen_id=sid, verdict="PASS",
                failed_axis=None, detail=None, source="rule"
            ))

    if new_ledger_rows:
        append_to_polarity_ledger(ledger_path, new_ledger_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "03_axis.json"
    payload = [r.to_dict() for r in results]
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    status = "NEEDS_REVIEW" if (pending_count > 0 and on_pending == "halt") else "DONE"
    return out_file, status, pending_count
