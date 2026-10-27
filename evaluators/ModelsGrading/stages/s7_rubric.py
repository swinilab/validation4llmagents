"""Stage S6 -- rubric for unmatched generated elements (spec §7.6).

Unmatched set: generated elements with no `PASS` pair at the primary threshold.
The rubric is judged once, at that threshold.

Gold does not exhaust the domain, so an element absent from gold may still be
correct. Each is judged on the two correctness conditions: **traceable** and
**consistent**. Atomicity is not a condition and must not be tested (§7.6).

A rejected pair does not reach here: the rubric is for generated elements with
no assigned PASS pair at all, not a salvage route for pairs the rule layer threw
out (§7.5). An element whose prerequisite missed *does* reach here (§7.1).
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from .. import ledgers
from ..judge import JudgeError

# A fixed judge prompt (§7.6). Interpolated with the element and the domain
# input; the pipeline never varies it per element beyond that.
JUDGE_PROMPT = """\
You are grading one element of a UML model against a domain specification.

Domain requirements (the only admissible source of truth for traceability):
{domain}

The element under judgement:
  kind:  {kind}
  label: {label}
  id:    {element_id}

Gold model elements (for the consistency test only -- the element under
judgement matched none of them, which is not by itself an error):
{gold_summary}

Answer the two conditions independently.

1. traceable -- is this element attributable to a real domain requirement or a
   real part of the domain description above, rather than an invented
   capability? A class split out of another (for example an Address class
   separated from Customer) is traceable when the underlying data is required.
2. consistent -- does it avoid contradicting any gold element above?

Do NOT judge atomicity, granularity, naming style or presentation.

Reply with exactly three lines:
traceable: yes|no
consistent: yes|no
rationale: <one sentence>
"""


def unmatched_gen(elements: dict, axis_records: list[dict], threshold: float,
                  diagrams) -> list[dict]:
    """Generated elements with no assigned PASS pair at `threshold` (§7.6)."""
    passing: set[tuple[str, str]] = set()
    for record in axis_records:
        if record["verdict"] != "PASS":
            continue
        cosine = record.get("cosine")
        # A by-construction pair (swimlane, transition) carries the cosine of the
        # action pair(s) it was built from, so it is filtered exactly when they are.
        if cosine is not None and cosine < threshold:
            continue
        passing.add((record["diagram"], record["gen_id"]))

    out: list[dict] = []
    for diagram in diagrams:
        for element in elements[diagram]["gen"]:
            if (diagram, element["element_id"]) in passing:
                continue
            out.append({"diagram": diagram, **element})
    out.sort(key=lambda e: (e["diagram"], e["element_id"]))
    return out


def _gold_summary(elements: dict, diagrams) -> str:
    lines: list[str] = []
    for diagram in diagrams:
        for element in elements[diagram]["gold"]:
            lines.append(f"  [{diagram}/{element['kind']}] {element['element_id']}")
    return "\n".join(lines)


def build_prompt(element: dict, domain: str, gold_summary: str) -> str:
    return JUDGE_PROMPT.format(
        domain=domain.strip(), kind=element["kind"],
        label=element.get("label_raw", element.get("label_norm", "")),
        element_id=element["element_id"], gold_summary=gold_summary)


def _judge_bool(value: str) -> bool | None:
    """Read a judge's yes/no from the first word, so `**Yes**.` or `yes, since
    ...` still count. Anything else stays None (unscored), never a guess."""
    words = re.findall(r"[a-z0-9]+", value.lower())
    return ledgers.as_bool(words[0]) if words else None


def parse_judge_reply(text: str) -> tuple[bool | None, bool | None, str]:
    """Pull `traceable`, `consistent` and `rationale` out of the reply.

    Tolerates markdown around the key (`**traceable:** yes`) and punctuation
    around the value. A condition the reply does not state clearly is None.
    """
    traceable = consistent = None
    rationale = ""
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key, value = re.sub(r"[^a-z]", "", key.lower()), value.strip()
        if key == "traceable":
            traceable = _judge_bool(value)
        elif key == "consistent":
            consistent = _judge_bool(value)
        elif key == "rationale":
            rationale = value.strip("*_` ")
    return traceable, consistent, rationale


def _log_call(log_path: Path | None, record: dict[str, Any]) -> None:
    """Append one judge call (prompt and raw reply included) to the JSONL log."""
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _ask_judge(judge, prompt: str, element: dict, config: dict,
               log_path: Path | None) -> tuple[bool | None, bool | None, str]:
    """Call the judge until its reply parses, up to `judge_max_attempts` times.

    Every attempt is logged with the prompt and the raw reply. A reply that
    never parses leaves the unreadable condition None, so the element stays
    unscored instead of being recorded as a verdict nobody gave. A transport
    failure (`JudgeError`) is logged and re-raised, as before.
    """
    traceable = consistent = None
    rationale = ""
    for attempt in range(1, config["judge_max_attempts"] + 1):
        record = {
            "element_id": element["element_id"], "diagram": element.get("diagram"),
            "kind": element["kind"], "attempt": attempt,
            "judge_model": config["judge_model"],
            "judge_temperature": config["judge_temperature"],
            "timestamp": _now(), "prompt": prompt,
        }
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


def run(elements: dict, axis_records: list[dict], config: dict, diagrams,
        review_dir: Path, domain_path: Path, on_pending: str,
        judge=None, log_path: Path | None = None) -> dict[str, Any]:
    """Judge the unmatched set and maintain the κ sample.

    `judge` is a callable taking a prompt and returning the model's reply. It is
    injected so the pipeline is runnable and testable without a live model; with
    `config.judge_model` unset there is no judge to call, and every unmatched
    element stays unscored (pending) unless running provisionally.
    """
    unmatched = unmatched_gen(elements, axis_records,
                              config["threshold_models"], diagrams)
    review_dir.mkdir(parents=True, exist_ok=True)

    llm_path = review_dir / ledgers.RUBRIC_LLM
    human_path = review_dir / ledgers.RUBRIC_HUMAN
    rounds_path = review_dir / ledgers.KAPPA_ROUNDS

    if not unmatched:
        ledgers.write_rubric_llm(llm_path, [])
        return {"unmatched": [], "rubric_pass": 0, "pending_rubric": 0,
                "unresolved": 0, "kappa": None, "judged": [],
                "rubric_source": "none"}

    domain = domain_path.read_text(encoding="utf-8") if domain_path.is_file() else ""
    gold_summary = _gold_summary(elements, diagrams)

    judged: list[dict[str, Any]] = []
    existing = {row["element_id"]: row for row in ledgers.read_csv(llm_path)}

    for element in unmatched:
        previous = existing.get(element["element_id"])
        # Reuse a row only when both conditions were scored; a half-read row is
        # judged again.
        if previous and (previous.get("traceable") or "").strip() \
                and (previous.get("consistent") or "").strip():
            judged.append(previous)
            continue
        if judge is None or not config["judge_model"]:
            judged.append({
                "element_id": element["element_id"], "kind": element["kind"],
                "label": element.get("label_raw", ""),
                "traceable": "", "consistent": "", "rationale": "",
                "judge_model": config["judge_model"] or "",
                "timestamp": "",
            })
            continue
        traceable, consistent, rationale = _ask_judge(
            judge, build_prompt(element, domain, gold_summary), element, config,
            log_path)
        # None (an unreadable reply) is written blank: the element stays
        # unscored rather than being recorded as a "no" the judge never gave.
        cell = {True: "yes", False: "no"}
        judged.append({
            "element_id": element["element_id"], "kind": element["kind"],
            "label": element.get("label_raw", ""),
            "traceable": cell.get(traceable, ""),
            "consistent": cell.get(consistent, ""),
            "rationale": rationale, "judge_model": config["judge_model"],
            "timestamp": _now(),
        })

    ledgers.write_rubric_llm(llm_path, judged)

    # The blind human sample for κ (§7.6): the LLM's labels must not appear in
    # this file, and previously drawn elements are excluded so a later round is
    # genuinely held out.
    rounds = ledgers.read_kappa_rounds(rounds_path)
    already = {eid for r in rounds for eid in r.get("element_ids", [])}
    pool = [e for e in unmatched if e["element_id"] not in already]
    size = min(config["kappa_sample_size"], len(pool))
    sample_elements = random.Random(config["random_seed"]).sample(pool, size) if pool else []
    sample = [{
        "element_id": e["element_id"], "kind": e["kind"],
        "label": e.get("label_raw", ""), "traceable": "", "consistent": "",
        "reviewer": "", "timestamp": "",
    } for e in sorted(sample_elements, key=lambda e: e["element_id"])]
    pending_rubric = ledgers.sync_rubric_human(human_path, sample)

    human_rows = {row["element_id"]: row for row in ledgers.read_csv(human_path)}
    kappa, n = _cohens_kappa(judged, human_rows)

    judged_by_id = {row["element_id"]: row for row in judged}
    rubric_pass = 0
    unscored = 0
    for element in unmatched:
        row = judged_by_id.get(element["element_id"], {})
        traceable = ledgers.as_bool(row.get("traceable", ""))
        consistent = ledgers.as_bool(row.get("consistent", ""))
        if traceable is None or consistent is None:
            unscored += 1
            continue
        if traceable and consistent:
            rubric_pass += 1

    # Still open whatever the mode: the metrics are final only without it.
    unresolved = pending_rubric + unscored

    if on_pending == "provisional":
        # §7.6: in provisional mode, unmatched elements are all treated as
        # failing, which keeps Precision a lower bound.
        pending_rubric = 0
        unscored = 0

    return {
        "unmatched": [e["element_id"] for e in unmatched],
        "unmatched_detail": unmatched,
        "rubric_pass": rubric_pass,
        "pending_rubric": pending_rubric + (0 if on_pending == "provisional" else unscored),
        "unresolved": unresolved,
        "kappa": kappa, "kappa_n": n, "kappa_pool": config["kappa_pool"],
        # §7.6: κ >= kappa_accept lets the judge's labels stand. None while no
        # κ exists (no judge, or the human sample is not filled in yet).
        "kappa_accepted": (None if kappa is None
                           else kappa >= config["kappa_accept"]),
        "judged": judged,
        "review_files": {"llm": str(llm_path), "human": str(human_path)},
    }


def _cohens_kappa(judged: list[dict], human: dict[str, dict]) -> tuple[float | None, int]:
    """Cohen's κ over the combined binary label (`traceable AND consistent`)."""
    pairs: list[tuple[bool, bool]] = []
    for row in judged:
        other = human.get(row["element_id"])
        if other is None:
            continue
        a_t = ledgers.as_bool(row.get("traceable", ""))
        a_c = ledgers.as_bool(row.get("consistent", ""))
        b_t = ledgers.as_bool(other.get("traceable", ""))
        b_c = ledgers.as_bool(other.get("consistent", ""))
        if None in (a_t, a_c, b_t, b_c):
            continue
        pairs.append((bool(a_t and a_c), bool(b_t and b_c)))

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


def append_kappa_round(review_dir: Path, config: dict, element_ids: list[str],
                       kappa: float | None, n: int) -> None:
    """Append a completed κ round (§7.6).

    Never recompute κ on the sample used to tune the prompt: a new round draws
    a fresh held-out sample, which `run` enforces by excluding every previously
    listed element id.
    """
    path = review_dir / ledgers.KAPPA_ROUNDS
    rounds = ledgers.read_kappa_rounds(path)
    rounds.append({"round": len(rounds) + 1, "seed": config["random_seed"],
                   "element_ids": element_ids, "kappa": kappa, "n": n})
    ledgers.write_kappa_rounds(path, rounds)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
