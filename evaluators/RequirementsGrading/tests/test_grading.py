"""test_grading.py — Acceptance tests for RequirementGrading (§13)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
import pytest

from evaluators.RequirementsGrading.config import ConfigError, GradingConfig, RulesConfig
from evaluators.RequirementsGrading.stages.s0_units import extract_units_from_file, normalize_text
from evaluators.RequirementsGrading.stages.s3_axis import RuleEvaluator


REPO_ROOT = Path(__file__).resolve().parents[3]
GRADING_DIR = REPO_ROOT / "evaluators" / "RequirementsGrading"
GOLD_PATH = REPO_ROOT / "materials" / "G1-requirements.json"
RULES_PATH = GRADING_DIR / "rules.yaml"


@pytest.fixture
def rules() -> RulesConfig:
    return RulesConfig.load(RULES_PATH)


@pytest.fixture
def evaluator(rules: RulesConfig) -> RuleEvaluator:
    return RuleEvaluator(rules)


def test_normalization_rules(rules: RulesConfig):
    # Markdown stripped, trailing period removed, whitespace collapsed
    raw = "**Each order item** records a quantity, a unit price and `one product`. "
    norm = normalize_text(raw, rules)
    assert norm == "Each order item records a quantity, a unit price and one product"
    assert not norm.endswith(".")


def test_axis1_polarity_reject_first(evaluator: RuleEvaluator):
    # 'registers no order' contains 'registers' (accept), but reject must win!
    assert evaluator.classify_polarity("The system registers no order.") == "reject"
    assert evaluator.classify_polarity("The system registers the order.") == "accept"
    assert evaluator.classify_polarity("The system leaves the state unchanged.") == "reject"
    assert evaluator.classify_polarity("The system sets status to closed.") == "accept"
    assert evaluator.classify_polarity("No state change occurs.") == "none"


def test_axis2_transitions(evaluator: RuleEvaluator):
    text1 = "Changes status from pending to filled."
    text2 = "Changes status from filled to pending."
    t1 = evaluator.extract_transitions(text1)
    t2 = evaluator.extract_transitions(text2)
    assert t1 == {("pending", "filled")}
    assert t2 == {("filled", "pending")}
    assert t1 != t2


def test_axis2_case_sensitive_roles(evaluator: RuleEvaluator):
    # Roles are case-sensitive: Customer, OrderStaff, Accountant
    tokens_correct = evaluator.extract_identifier_tokens("When Customer submits order, OrderStaff reviews.")
    assert "Customer" in tokens_correct
    assert "OrderStaff" in tokens_correct
    assert "customer" not in tokens_correct

    tokens_lower = evaluator.extract_identifier_tokens("When customer submits order, orderstaff reviews.")
    assert "Customer" not in tokens_lower
    assert "OrderStaff" not in tokens_lower


def test_axis2_deliberate_trap_invoice_vs_payment(evaluator: RuleEvaluator):
    # Invoice becomes paid, payment becomes completed.
    # If a payment criterion says 'payment is paid', it yields 'payment' and 'paid'
    # whereas gold yields 'payment' and 'completed'.
    gold_text = "The payment status becomes completed."
    gen_text = "The payment status becomes paid."
    pass_ok, detail = evaluator.evaluate_axis2_identifiers(gold_text, gen_text)
    assert not pass_ok
    assert "subcheck=2b tokens" in detail


def test_axis2_cardinality_normalization(evaluator: RuleEvaluator):
    text1 = "A customer has at most one bank account."
    text2 = "A customer has no more than one bank account."
    c1 = evaluator.extract_cardinality(text1)
    c2 = evaluator.extract_cardinality(text2)
    assert c1["at most one"] == 1
    assert c2["at most one"] == 1
    assert c1 == c2


def test_axis3_numeric_sensitivity(evaluator: RuleEvaluator):
    gold = "The system shall respond within 2 seconds for at least 95% of submissions."
    gen_wrong = "The system shall respond within 3 seconds for at least 95% of submissions."
    pass_ok, detail = evaluator.evaluate_axis3_numeric(gold, gen_wrong, "nfr")
    assert not pass_ok
    assert "missing values" in detail

    gen_right = "The system responds within 2 seconds for at least 95% of submissions."
    pass_ok2, _ = evaluator.evaluate_axis3_numeric(gold, gen_right, "nfr")
    assert pass_ok2


# --- the runner (§13) ------------------------------------------------------------

CONFIG_PATH = REPO_ROOT / "config.yaml"


def YES_JUDGE(prompt: str) -> str:
    """A judge that accepts everything, so no test reaches a live model."""
    return "traceable: yes\nconsistent: yes\nrationale: fine"


@pytest.fixture
def grade_run(tmp_path):
    """Grade a requirements dict in-process; returns (exit_code, metrics)."""
    from evaluators.RequirementsGrading.run import EXIT, WORKSPACE, grade

    out = tmp_path / "RUN"

    def run(data: dict, on_pending: str = "halt", judge=YES_JUDGE):
        submission = tmp_path / "submission"
        submission.mkdir(exist_ok=True)
        (submission / "requirements.json").write_text(
            json.dumps(data), encoding="utf-8")
        code = grade(submission, out, run_id="t", config_path=CONFIG_PATH,
                     on_pending=on_pending, judge=judge)
        metrics_file = out / WORKSPACE / "run" / "05_metrics.json"
        metrics = (json.loads(metrics_file.read_text(encoding="utf-8"))
                   if metrics_file.is_file() else None)
        return code, metrics

    run.exit = EXIT
    run.out = out / WORKSPACE
    return run


def _gold() -> dict:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def _primary(metrics: dict) -> dict:
    return next(r for r in metrics["sweep"]
                if abs(r["threshold"] - metrics["primary_threshold"]) < 1e-4)


def test_identity_scores_one(grade_run):
    code, metrics = grade_run(_gold())
    assert code == grade_run.exit["DONE"]
    row = _primary(metrics)
    assert (row["recall"], row["precision"]) == (1.0, 1.0)
    assert row["matched_gold"] == metrics["gold_total"]
    assert metrics["pending_polarity"] == 0
    # Every unit passes the rule layer against itself. (Other pairs above the
    # threshold are rightly rejected, so the total rejection count is not zero.)
    axis = json.loads((grade_run.out / "run" / "03_axis.json").read_text(encoding="utf-8"))
    own = {r["gold_id"]: r["verdict"] for r in axis if r["gold_id"] == r["gen_id"]}
    assert len(own) == metrics["gold_total"]
    assert set(own.values()) == {"PASS"}


def test_results_land_in_the_run_dir_not_beside_the_module(grade_run):
    grade_run(_gold())
    assert (grade_run.out / "run" / "05_metrics.json").is_file()
    assert (grade_run.out / "run" / "manifest.json").is_file()
    assert not (GRADING_DIR / "run").exists()


def test_duplicated_criteria_are_deduped_and_recall_is_unchanged(grade_run):
    _, base = grade_run(_gold())
    data = _gold()
    story = data["requirements"][0]
    first = len(story["acceptance_criteria"])
    copies = [dict(ac, id=f"{story['id']}-AC{first + i + 1:02d}")
              for i, ac in enumerate(story["acceptance_criteria"][:3])]
    story["acceptance_criteria"] += copies
    _, dup = grade_run(data)
    # The gold already holds near-duplicates at the dedup threshold, so compare
    # against the baseline: exactly the three copies are added to the removed set.
    assert (dup["diagnostics"]["dedup_removed"]
            - base["diagnostics"]["dedup_removed"]) == 3
    assert _primary(dup)["recall"] == _primary(base)["recall"]
    assert dup["s_size"] == base["s_size"]


def test_stale_similarity_cache_is_recomputed(grade_run):
    grade_run(_gold())
    index = grade_run.out / "run" / "01_sim_index.json"
    before = json.loads(index.read_text(encoding="utf-8"))["digest"]
    data = _gold()
    data["requirements"][0]["acceptance_criteria"][0]["text"] = (
        "The system keeps a record of each customer.")
    grade_run(data, on_pending="provisional")
    after = json.loads(index.read_text(encoding="utf-8"))["digest"]
    assert before != after


# --- configuration layout ----------------------------------------------------------

def _config_with(tmp_path, mutate):
    import yaml
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def test_shared_keys_come_from_the_top_level(tmp_path):
    path = _config_with(tmp_path, lambda raw: raw.update(random_seed=7))
    assert GradingConfig.load(path).random_seed == 7


def test_a_shared_key_in_the_module_section_is_refused(tmp_path):
    def mutate(raw):
        raw["requirement_grading"]["random_seed"] = 7
    with pytest.raises(ConfigError, match="random_seed"):
        GradingConfig.load(_config_with(tmp_path, mutate))


def test_a_missing_shared_key_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="random_seed"):
        GradingConfig.load(_config_with(tmp_path, lambda raw: raw.pop("random_seed")))


def test_the_manifest_config_has_no_secret(grade_run):
    grade_run(_gold())
    manifest = json.loads((grade_run.out / "run" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert "judge_api_key" not in manifest["config"]
    assert "judge_model" in manifest["config"]


def test_a_bad_config_path_fails_the_run_not_the_process(tmp_path):
    from evaluators.RequirementsGrading.run import EXIT, grade
    submission = tmp_path / "submission"
    submission.mkdir()
    code = grade(submission, tmp_path / "RUN", config_path=tmp_path / "missing.yaml")
    assert code == EXIT["FAILED"]


# --- review rounds ---------------------------------------------------------------

def _fill(path, answer: str) -> int:
    """Answer every empty rubric row of the human file; returns how many."""
    import csv
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        row["traceable"] = row["consistent"] = answer
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _unrelated_submission() -> dict:
    """A submission whose units match nothing in gold, so the rubric is needed."""
    return {"requirements": [{
        "id": "US-01", "type": "functional",
        "statement": "As a Customer, I want a loyalty badge, so that I feel valued.",
        "acceptance_criteria": [
            {"id": f"US-01-AC0{i}", "format": "condition", "text": text}
            for i, text in enumerate([
                "The badge is rendered in teal.",
                "Weather forecasts for Hanoi are shown on the login page.",
                "Customers can play chess against each other."], start=1)]}]}


def test_a_halt_still_writes_the_manifest_and_review_file(grade_run):
    code, _ = grade_run(_unrelated_submission())
    assert code == grade_run.exit["NEEDS_REVIEW"]
    assert (grade_run.out / "run" / "manifest.json").is_file()
    assert (grade_run.out / "review" / "rubric_human.csv").is_file()


def test_a_finished_review_is_not_followed_by_a_new_batch(grade_run, tmp_path,
                                                          monkeypatch):
    # A sample smaller than the unmatched set: units are left over after round one.
    def mutate(raw):
        raw["kappa_sample_size"] = 1
        # The config moves to a temp dir, so gold paths must no longer be relative.
        raw["gold"] = {k: str(REPO_ROOT / v) for k, v in raw["gold"].items()}
    small = _config_with(tmp_path, mutate)
    monkeypatch.setattr(sys.modules[__name__], "CONFIG_PATH", small)
    grade_run(_unrelated_submission())
    human = grade_run.out / "review" / "rubric_human.csv"
    answered = _fill(human, "no")
    code, metrics = grade_run(_unrelated_submission())
    assert code == grade_run.exit["DONE"], "rerun asked for more rows"
    assert _fill(human, "no") == answered
    assert metrics["status"] == "final"


# --- the rubric judge (§9.3) -------------------------------------------------------

def _csv_rows(path):
    import csv
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_unmatched_is_decided_at_the_primary_threshold_not_the_lowest():
    from evaluators.RequirementsGrading.stages.s5_rubric import unmatched_ids
    candidates = [{"gold_id": "G", "gen_id": "A", "cosine": 0.72, "excluded": None},
                  {"gold_id": "G", "gen_id": "B", "cosine": 0.80, "excluded": None}]
    axis = [{"gold_id": "G", "gen_id": "A", "verdict": "PASS"},
            {"gold_id": "G", "gen_id": "B", "verdict": "PASS"}]
    # A passes the rule layer but only at 0.72: below the 0.75 primary threshold.
    assert unmatched_ids(candidates, axis, {"kept": ["A", "B", "C"]}, 0.75) == ["A", "C"]


def test_the_judge_labels_every_unmatched_unit(grade_run):
    code, metrics = grade_run(_unrelated_submission(), on_pending="provisional")
    llm = _csv_rows(grade_run.out / "review" / "rubric_llm.csv")
    assert code == grade_run.exit["DONE"]
    assert llm and all(r["traceable"] == "yes" and r["consistent"] == "yes" for r in llm)
    assert metrics["rubric_pass"] == len(llm)
    assert metrics["judge_model"]
    log = (grade_run.out / "run" / "06_judge_log.jsonl").read_text(encoding="utf-8")
    assert len(log.splitlines()) == len(llm)


def test_the_human_file_is_blind_to_the_judge(grade_run):
    grade_run(_unrelated_submission())
    header = (grade_run.out / "review" / "rubric_human.csv").read_text(
        encoding="utf-8").splitlines()[0]
    assert header == "gen_id,gen_text,traceable,consistent,reviewer,timestamp"
    assert all(not r["traceable"] for r in
               _csv_rows(grade_run.out / "review" / "rubric_human.csv"))


def test_kappa_compares_judge_and_human_on_the_sample(grade_run):
    grade_run(_unrelated_submission())
    _fill(grade_run.out / "review" / "rubric_human.csv", "yes")
    code, metrics = grade_run(_unrelated_submission())
    assert code == grade_run.exit["DONE"]
    assert metrics["kappa"] == 1.0 and metrics["kappa_n"] == 3
    assert metrics["kappa_accepted"] is True


def test_judge_rows_are_reused_not_asked_again(grade_run):
    calls = []

    def counting(prompt):
        calls.append(prompt)
        return YES_JUDGE(prompt)

    grade_run(_unrelated_submission(), judge=counting)
    asked = len(calls)
    assert asked
    grade_run(_unrelated_submission(), judge=counting)
    assert len(calls) == asked


def test_without_a_judge_units_stay_pending_or_fail_provisionally(grade_run):
    code, _ = grade_run(_unrelated_submission(), judge=None)
    assert code == grade_run.exit["NEEDS_REVIEW"]
    code, metrics = grade_run(_unrelated_submission(), on_pending="provisional",
                              judge=None)
    assert code == grade_run.exit["DONE"]
    assert metrics["rubric_pass"] == 0 and metrics["status"] == "provisional"


def test_an_unreachable_judge_fails_the_run(grade_run):
    from evaluators.ModelsGrading.judge import JudgeError

    def down(prompt):
        raise JudgeError("unreachable")

    code, _ = grade_run(_unrelated_submission(), judge=down)
    assert code == grade_run.exit["FAILED"]


def test_provisional_mode_with_nothing_pending_is_final(grade_run):
    # `status` says whether anything is still open, not which mode was asked for.
    grade_run(_unrelated_submission())
    _fill(grade_run.out / "review" / "rubric_human.csv", "yes")
    code, metrics = grade_run(_unrelated_submission(), on_pending="provisional")
    assert code == grade_run.exit["DONE"] and metrics["status"] == "final"
