"""s5_rubric.py — Stage S5: rubric for unmatched generated units (spec §9.3).

Unmatched set: units in `S` with no `PASS` pair at the primary threshold. The
rubric is judged once, at that threshold.

Gold does not exhaust the domain, so a unit absent from gold may still be correct.
Each is judged on the two correctness conditions: **traceable** and
**consistent**. Atomicity is not a condition and must not be tested.

An LLM judge labels every unmatched unit (`review/rubric_llm.csv`); a blind human
sample is labelled independently (`review/rubric_human.csv`), and Cohen's κ between
the two says whether the judge's labels may stand. The judge, its prompt handling
and the review-file conventions are shared with ModelsGrading.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluators.ModelsGrading import ledgers
from evaluators.ModelsGrading.judge import JudgeError
from evaluators.ModelsGrading.stages.s7_rubric import parse_judge_reply

from ..config import GradingConfig

RUBRIC_LLM_FIELDS = ["gen_id", "gen_text", "traceable", "consistent", "rationale",
                     "judge_model", "timestamp"]
# The LLM's labels must not appear in the human file. Blindness is enforced by the
# schema, not by instruction (§9.3).
RUBRIC_HUMAN_FIELDS = ["gen_id", "gen_text", "traceable", "consistent",
                       "reviewer", "timestamp"]

# Every judge call, prompt and raw reply included, in the run dir. Appended to,
# never rewritten, so reruns and retries stay auditable.
JUDGE_LOG = "06_judge_log.jsonl"

# A fixed judge prompt (§9.3), interpolated with the unit and the domain input.
JUDGE_PROMPT = """\
You are grading one requirement unit written for a software system against its
domain specification.

Domain specification (the only admissible source of truth for traceability):
{domain}

The unit under judgement:
  kind: {kind}   (ac = acceptance criterion of a user story, nfr = non-functional requirement)
  id:   {unit_id}
  text: {text}

Gold acceptance criteria (for the consistency test only -- the unit under
judgement matched none of them, which is not by itself an error):
{gold_summary}

Answer the two conditions independently.

1. traceable -- is this unit attributable to a real domain requirement or a real
   part of the domain description above, rather than an invented capability?
2. consistent -- does it avoid contradicting any gold unit above?

Do NOT judge atomicity, granularity, wording style or presentation.

Reply with exactly three lines:
traceable: yes|no
consistent: yes|no
rationale: <one sentence>
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def unmatched_ids(candidates: list[dict], axis_results: list[dict],
                  dedup_data: dict, threshold: float) -> list[str]:
    """Units in `S` with no assigned `PASS` pair at `threshold` (§9.3)."""
    kept = set(dedup_data.get("kept", []))
    cosine = {(c["gold_id"], c["gen_id"]): c.get("cosine", 0.0)
              for c in candidates if c.get("excluded") is None}
    matched = {r["gen_id"] for r in axis_results
               if r.get("verdict") == "PASS"
               and cosine.get((r["gold_id"], r["gen_id"]), 0.0) >= threshold}
    return sorted(kept - matched)


def build_prompt(unit: dict, domain: str, gold_summary: str) -> str:
    return JUDGE_PROMPT.format(domain=domain.strip(), kind=unit["kind"],
                               unit_id=unit["unit_id"], text=unit["text_raw"],
                               gold_summary=gold_summary)


def _log_call(log_path: Path | None, record: dict[str, Any]) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _ask_judge(judge, prompt: str, unit: dict, config: GradingConfig,
               log_path: Path | None) -> tuple[bool | None, bool | None, str]:
    """Call the judge until its reply parses, up to `judge_max_attempts` times.

    Every attempt is logged. A reply that never parses leaves the unreadable
    condition None, so the unit stays unscored instead of being recorded as a
    verdict nobody gave. A transport failure (`JudgeError`) is logged and re-raised.
    """
    traceable = consistent = None
    rationale = ""
    for attempt in range(1, config.judge_max_attempts + 1):
        record = {"gen_id": unit["unit_id"], "attempt": attempt,
                  "judge_model": config.judge_model,
                  "judge_temperature": config.judge_temperature,
                  "timestamp": _now(), "prompt": prompt}
        try:
            reply = judge(prompt)
        except JudgeError as error:
            _log_call(log_path, {**record, "reply": None, "error": str(error)})
            raise
        traceable, consistent, rationale = parse_judge_reply(reply)
        parsed = traceable is not None and consistent is not None
        _log_call(log_path, {**record, "reply": reply, "parsed": parsed,
                             "traceable": traceable, "consistent": consistent,
                             "rationale": rationale})
        if parsed:
            break
    return traceable, consistent, rationale


def _cohens_kappa(judged: list[dict], human: dict[str, dict]) -> tuple[float | None, int]:
    """Cohen's κ over the combined binary label (`traceable AND consistent`)."""
    pairs: list[tuple[bool, bool]] = []
    for row in judged:
        other = human.get(row["gen_id"])
        if other is None:
            continue
        labels = [ledgers.as_bool(row.get("traceable", "")),
                  ledgers.as_bool(row.get("consistent", "")),
                  ledgers.as_bool(other.get("traceable", "")),
                  ledgers.as_bool(other.get("consistent", ""))]
        if None in labels:
            continue
        pairs.append((labels[0] and labels[1], labels[2] and labels[3]))

    n = len(pairs)
    if n == 0:
        return None, 0
    agree = sum(1 for a, b in pairs if a == b) / n
    a_yes = sum(1 for a, _ in pairs if a) / n
    b_yes = sum(1 for _, b in pairs if b) / n
    expected = a_yes * b_yes + (1 - a_yes) * (1 - b_yes)
    if expected == 1.0:
        return 1.0 if agree == 1.0 else 0.0, n
    return round((agree - expected) / (1 - expected), 4), n


def run_s5(
    units_file: Path,
    candidates_file: Path,
    axis_file: Path,
    dedup_file: Path,
    out_dir: Path,
    review_dir: Path,
    domain_path: Path,
    config: GradingConfig,
    on_pending: str = "halt",
    judge=None,
) -> dict[str, Any]:
    """Execute Stage S5: judge the unmatched set and maintain the κ sample.

    `judge` is a callable taking a prompt and returning the model's reply, injected
    so the stage is runnable and testable without a live model. With none (no
    `judge_model`) every unmatched unit stays unscored, hence pending, unless
    running provisionally, where unscored units count as failing the rubric.

    Returns the rubric result: `rubric_pass`, `pending_rubric`, `status` (`DONE` or
    `NEEDS_REVIEW`), `kappa`, `kappa_n`, `kappa_accepted`, `review_files`.
    """
    units_data = json.loads(units_file.read_text(encoding="utf-8"))
    gen_by_id = {u["unit_id"]: u for u in units_data.get("gen", [])}
    candidates = json.loads(candidates_file.read_text(encoding="utf-8"))
    axis_results = json.loads(axis_file.read_text(encoding="utf-8"))
    dedup_data = json.loads(dedup_file.read_text(encoding="utf-8"))

    unmatched = unmatched_ids(candidates, axis_results, dedup_data, config.threshold)

    review_dir.mkdir(parents=True, exist_ok=True)
    llm_path = review_dir / ledgers.RUBRIC_LLM
    human_path = review_dir / ledgers.RUBRIC_HUMAN
    rounds_path = review_dir / ledgers.KAPPA_ROUNDS
    result: dict[str, Any] = {
        "rubric_pass": 0, "pending_rubric": 0, "unresolved": 0, "status": "DONE",
        "kappa": None, "kappa_n": 0, "kappa_accepted": None,
        "review_files": {"llm": str(llm_path), "human": str(human_path)},
    }
    if not unmatched:
        _write_csv(llm_path, RUBRIC_LLM_FIELDS, [])
        return result

    domain = domain_path.read_text(encoding="utf-8") if domain_path.is_file() else ""
    gold_summary = "\n".join(f"  [{u['unit_id']}] {u['text_raw']}"
                             for u in units_data.get("gold", []))

    existing = {row["gen_id"]: row for row in ledgers.read_csv(llm_path)
                if row.get("gen_id")}
    judged: list[dict[str, Any]] = []
    for uid in unmatched:
        unit = gen_by_id[uid]
        previous = existing.get(uid)
        # Reuse a row only when both conditions were scored; a half-read row is
        # judged again.
        if previous and (previous.get("traceable") or "").strip() \
                and (previous.get("consistent") or "").strip():
            judged.append(previous)
            continue
        row = {"gen_id": uid, "gen_text": unit["text_raw"], "traceable": "",
               "consistent": "", "rationale": "",
               "judge_model": config.judge_model or "", "timestamp": ""}
        if judge is not None and config.judge_model:
            traceable, consistent, rationale = _ask_judge(
                judge, build_prompt(unit, domain, gold_summary), unit, config,
                out_dir / JUDGE_LOG)
            # None (an unreadable reply) is written blank: the unit stays unscored
            # rather than being recorded as a "no" the judge never gave.
            cell = {True: "yes", False: "no"}
            row.update(traceable=cell.get(traceable, ""),
                       consistent=cell.get(consistent, ""),
                       rationale=rationale, timestamp=_now())
        judged.append(row)
    _write_csv(llm_path, RUBRIC_LLM_FIELDS, judged)

    # The blind human sample for κ (§9.3): drawn from the units no earlier round
    # used, so a later round is genuinely held out. The draw is deterministic in
    # the seed and the pool, so a rerun asks for the same units, not a new batch.
    rounds = ledgers.read_kappa_rounds(rounds_path)
    used = {gid for r in rounds for gid in r.get("gen_ids", [])}
    pool = [uid for uid in unmatched if uid not in used]
    size = min(config.kappa_sample_size, len(pool))
    sample = sorted(random.Random(config.random_seed).sample(pool, size))

    human_rows = ledgers.read_csv(human_path)
    on_file = {row.get("gen_id") for row in human_rows}
    for uid in sample:
        if uid not in on_file:
            human_rows.append({"gen_id": uid, "gen_text": gen_by_id[uid]["text_raw"]})
    _write_csv(human_path, RUBRIC_HUMAN_FIELDS, human_rows)
    human = {row["gen_id"]: row for row in human_rows}
    pending_human = sum(
        1 for uid in sample
        if not ((human[uid].get("traceable") or "").strip()
                and (human[uid].get("consistent") or "").strip()))

    kappa, kappa_n = _cohens_kappa(judged, human)

    rubric_pass = unscored = 0
    for row in judged:
        traceable = ledgers.as_bool(row.get("traceable", ""))
        consistent = ledgers.as_bool(row.get("consistent", ""))
        if traceable is None or consistent is None:
            unscored += 1
        elif traceable and consistent:
            rubric_pass += 1

    # §9.3: in provisional mode unmatched units that were not scored are treated as
    # failing, which keeps Precision a lower bound.
    pending = 0 if on_pending == "provisional" else pending_human + unscored
    result.update(
        rubric_pass=rubric_pass, pending_rubric=pending,
        status="NEEDS_REVIEW" if pending else "DONE",
        # What is still open whatever the mode: the metrics are final only without it.
        unresolved=pending_human + unscored,
        kappa=kappa, kappa_n=kappa_n,
        # κ >= kappa_accept lets the judge's labels stand. None while no κ exists
        # (no judge, or the human sample is not filled in yet).
        kappa_accepted=None if kappa is None else kappa >= config.kappa_accept,
        unscored=unscored, pending_human=pending_human)
    return result


def append_kappa_round(review_dir: Path, config: GradingConfig, gen_ids: list[str],
                       kappa: float | None, n: int) -> None:
    """Append a completed κ round (§9.3).

    Never recompute κ on the sample used to tune the prompt: a new round draws a
    fresh held-out sample, which `run_s5` enforces by excluding every `gen_id`
    listed in an earlier round.
    """
    path = review_dir / ledgers.KAPPA_ROUNDS
    rounds = ledgers.read_kappa_rounds(path)
    rounds.append({"round": len(rounds) + 1, "seed": config.random_seed,
                   "gen_ids": gen_ids, "kappa": kappa, "n": n})
    ledgers.write_kappa_rounds(path, rounds)
