"""s0_units.py — Stage S0: Unit extraction and normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config import GradingConfig, RulesConfig
from ..models import FormatViolation, Unit


ID_REQ_PATTERN = re.compile(r"^(US|NFR)-\d{2}$")
ID_AC_PATTERN = re.compile(r"^US-\d{2}-AC\d{2}$")

KNOWN_REQ_MEMBERS = {
    "id", "type", "form", "statement", "role", "capability",
    "acceptance_criteria", "priority", "verification_method",
}
REQUIRED_REQ_MEMBERS = {"id", "type", "statement"}

KNOWN_AC_MEMBERS = {"id", "format", "text", "given", "when", "then"}
REQUIRED_AC_MEMBERS = {"id", "text"}


def normalize_text(text: str, rules: RulesConfig) -> str:
    """Normalize text according to §4.2 and rules.yaml."""
    norm_cfg = rules.normalization
    chars_to_strip = norm_cfg.get("strip_markdown_chars", ["*", "_", "`"])
    res = text
    for ch in chars_to_strip:
        res = res.replace(ch, "")

    if norm_cfg.get("collapse_whitespace", True):
        res = re.sub(r"\s+", " ", res)

    res = res.strip()

    if norm_cfg.get("strip_trailing_period", True) and res.endswith("."):
        res = res[:-1].rstrip()

    return res


def extract_units_from_file(
    path: Path | str,
    rules: RulesConfig,
    is_gold: bool = False,
) -> tuple[list[Unit], list[FormatViolation]]:
    """Extract units and record format violations from a requirements JSON file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Requirements file not found: {p}")

    try:
        content = p.read_text(encoding="utf-8")
        raw_data = json.loads(content)
    except Exception as exc:
        raise ValueError(f"json_parse_error: Failed to parse {p}: {exc}") from exc

    if isinstance(raw_data, list):
        req_list = raw_data
    elif isinstance(raw_data, dict) and "requirements" in raw_data and isinstance(raw_data["requirements"], list):
        req_list = raw_data["requirements"]
    else:
        raise ValueError(f"Invalid requirements format in {p}: expected list or dict with 'requirements' key")

    units: list[Unit] = []
    violations: list[FormatViolation] = []
    seen_ids: set[str] = set()

    for r_idx, r in enumerate(req_list):
        if not isinstance(r, dict):
            violations.append(FormatViolation(f"REQ-{r_idx}", "invalid_record", "Requirement is not an object"))
            continue

        req_id = r.get("id", f"REQ-{r_idx}")

        # Check required members
        for req_m in REQUIRED_REQ_MEMBERS:
            if req_m not in r:
                violations.append(FormatViolation(req_id, "missing_member", f"Requirement missing '{req_m}'"))

        # Check unknown members
        for m in r:
            if m not in KNOWN_REQ_MEMBERS:
                violations.append(FormatViolation(req_id, "unknown_member", f"Unknown member '{m}' in requirement"))

        # ID pattern check
        if not ID_REQ_PATTERN.match(str(req_id)):
            violations.append(FormatViolation(req_id, "id_pattern", f"Invalid requirement ID: {req_id}"))

        # Duplicate ID
        if req_id in seen_ids:
            violations.append(FormatViolation(req_id, "id_duplicate", f"Duplicate requirement ID: {req_id}"))
            continue
        seen_ids.add(req_id)

        rtype = r.get("type", "")
        stmt = r.get("statement", "")

        # Newline in statement
        if isinstance(stmt, str) and "\n" in stmt:
            violations.append(FormatViolation(req_id, "newline_in_field", "Newline in requirement statement"))

        acs = r.get("acceptance_criteria", [])

        if rtype == "functional":
            if not isinstance(acs, list) or len(acs) < 3:
                violations.append(FormatViolation(req_id, "ac_below_minimum", f"Functional requirement has fewer than 3 ACs ({len(acs) if isinstance(acs, list) else 0})"))

            if isinstance(acs, list):
                for ac_idx, ac in enumerate(acs):
                    if not isinstance(ac, dict):
                        violations.append(FormatViolation(f"{req_id}-AC-{ac_idx}", "invalid_record", "AC is not an object"))
                        continue

                    ac_id = ac.get("id", f"{req_id}-AC{ac_idx+1:02d}")

                    # Check required members
                    for ac_m in REQUIRED_AC_MEMBERS:
                        if ac_m not in ac:
                            violations.append(FormatViolation(ac_id, "missing_member", f"AC missing '{ac_m}'"))

                    # Check unknown members
                    for m in ac:
                        if m not in KNOWN_AC_MEMBERS:
                            violations.append(FormatViolation(ac_id, "unknown_member", f"Unknown member '{m}' in AC"))

                    # ID pattern check
                    if not ID_AC_PATTERN.match(str(ac_id)):
                        violations.append(FormatViolation(ac_id, "id_pattern", f"Invalid AC ID: {ac_id}"))

                    # AC prefix mismatch
                    if not str(ac_id).startswith(f"{req_id}-AC"):
                        violations.append(FormatViolation(ac_id, "ac_prefix_mismatch", f"AC ID {ac_id} does not start with {req_id}-AC"))

                    # Duplicate AC ID
                    if ac_id in seen_ids:
                        violations.append(FormatViolation(ac_id, "id_duplicate", f"Duplicate AC ID: {ac_id}"))
                        continue
                    seen_ids.add(ac_id)

                    ac_text = ac.get("text", "")
                    if isinstance(ac_text, str) and "\n" in ac_text:
                        violations.append(FormatViolation(ac_id, "newline_in_field", "Newline in AC text"))

                    raw_text = str(ac_text) if ac_text is not None else ""
                    norm_text = normalize_text(raw_text, rules)

                    if not norm_text:
                        violations.append(FormatViolation(ac_id, "empty_text", "Empty normalized text in AC"))
                        continue

                    units.append(Unit(
                        unit_id=str(ac_id),
                        parent_id=str(req_id),
                        kind="ac",
                        text_raw=raw_text,
                        text_norm=norm_text,
                    ))
        else:
            # Non-functional requirement
            if bool(acs):
                violations.append(FormatViolation(req_id, "ac_on_nfr", "Non-functional requirement has acceptance_criteria"))

            raw_text = str(stmt) if stmt is not None else ""
            norm_text = normalize_text(raw_text, rules)

            if not norm_text:
                violations.append(FormatViolation(req_id, "empty_text", "Empty normalized text in requirement statement"))
                continue

            units.append(Unit(
                unit_id=str(req_id),
                parent_id=str(req_id),
                kind="nfr",
                text_raw=raw_text,
                text_norm=norm_text,
            ))

    return units, violations


def run_s0(
    run_id: str,
    submission_path: Path | str,
    gold_path: Path | str,
    out_dir: Path,
    config: GradingConfig,
    rules: RulesConfig,
) -> Path:
    """Execute Stage S0 and write 00_units.json."""
    gold_units, gold_violations = extract_units_from_file(gold_path, rules, is_gold=True)

    if gold_violations:
        raise RuntimeError(f"Gold requirements produced {len(gold_violations)} format violations: {gold_violations}")

    if config.expected_gold_units is not None and len(gold_units) != config.expected_gold_units:
        raise RuntimeError(
            f"Expected {config.expected_gold_units} gold units, but extracted {len(gold_units)} from {gold_path}"
        )

    gen_units, gen_violations = extract_units_from_file(submission_path, rules, is_gold=False)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "00_units.json"
    payload = {
        "run_id": run_id,
        "gold": [u.to_dict() for u in gold_units],
        "gen": [u.to_dict() for u in gen_units],
        "violations": [v.to_dict() for v in gen_violations],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_file
