"""report_summary.py — One table of the final metrics of every graded run.

Reads the raw report (`report_<run>.json`, written by `report_writer.py`) of each
run directory under `generated/`, prints one row per run and writes the same rows
as CSV. The ten metrics are the ones of materials/M2-metrics.md §1.1, each in its
own column (no F1: recall and precision are reported separately). Run directories are found by looking for that report, so a new run shows
up without any change here:

    python main.py --phase summary [--out generated/final_metrics.csv]
    python report_summary.py [generated] [-o final_metrics.csv]

Values the grading marked `n/a` (a metric that was not measured, e.g. behind a
failed syntax gate) stay `n/a`; a run or module that has not been graded is blank.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_DIR = "generated"
DEFAULT_OUT = "final_metrics.csv"

# The ten metrics of M2 §1.1 (Completeness, then Correctness), as CSV columns.
METRICS = (
    "requirement_recall", "structural_semantic_recall", "behavioral_semantic_recall",
    "vmx_requirement_coverage",
    "requirement_precision", "structural_semantic_precision",
    "behavioral_semantic_precision",
    "structural_syntax_validity", "behavioral_syntax_validity",
    "vmx_referential_integrity",
)

# CSV columns, in order: the run, the ten metrics, then what is needed to read them
# (the syntax gate decides whether a semantic metric is `n/a`; the statuses say
# whether a module is final; kappa says whether the judge's labels were accepted).
COLUMNS = (
    "run", *METRICS,
    "structural_syntax_gate", "behavioral_syntax_gate",
    "reqs_status", "models_status", "vmx_status",
    "requirements_kappa", "requirements_kappa_n", "models_kappa", "models_kappa_n",
)

# Columns of the printed table: (header, CSV column).
TABLE = (
    ("run", "run"),
    ("ReqRec", "requirement_recall"), ("StrRec", "structural_semantic_recall"),
    ("BehRec", "behavioral_semantic_recall"), ("VMXCov", "vmx_requirement_coverage"),
    ("ReqPrec", "requirement_precision"), ("StrPrec", "structural_semantic_precision"),
    ("BehPrec", "behavioral_semantic_precision"),
    ("StrSyn", "structural_syntax_validity"), ("BehSyn", "behavioral_syntax_validity"),
    ("VMXInt", "vmx_referential_integrity"),
)


def _num(value: object) -> object:
    """Numbers rounded for display; `n/a`, None and text pass through."""
    if isinstance(value, bool) or value is None:
        return "" if value is None else value
    if isinstance(value, (int, float)):
        return round(value, 4)
    return value


def _status(entry: dict | None) -> str:
    """`final` / `provisional` from the module's message; else pass/fail."""
    if not entry:
        return ""
    message = str(entry.get("message", ""))
    if "status=" in message:
        return message.split("status=", 1)[1].split()[0].strip(",;")
    return "pass" if entry.get("passed") else "fail"


def find_reports(generated: Path) -> dict[str, Path]:
    """`{run name: raw report}` for every run directory that has one."""
    reports: dict[str, Path] = {}
    if not generated.is_dir():
        return reports
    for run_dir in sorted(p for p in generated.iterdir() if p.is_dir()):
        candidates = sorted(run_dir.glob("report_*.json"),
                            key=lambda p: (p.stem != f"report_{run_dir.name}",
                                           -p.stat().st_mtime))
        if candidates:
            reports[run_dir.name] = candidates[0]
    return reports


def row_for(run: str, report: dict) -> dict[str, object]:
    """The summary row of one raw report."""
    grading = report.get("grading") or {}
    row: dict[str, object] = dict.fromkeys(COLUMNS, "")
    row["run"] = run

    reqs = grading.get("reqs")
    if reqs:
        metrics = (reqs.get("details") or {}).get("metrics") or {}
        primary = metrics.get("primary_threshold")
        at_primary = next((r for r in metrics.get("sweep", [])
                           if r.get("threshold") == primary), {})
        row.update(reqs_status=_status(reqs),
                   requirement_recall=_num(at_primary.get("recall", "")),
                   requirement_precision=_num(at_primary.get("precision", "")),
                   requirements_kappa=_num(metrics.get("kappa")),
                   requirements_kappa_n=_num(metrics.get("kappa_n")))

    models = grading.get("models")
    if models:
        metrics = (models.get("details") or {}).get("metrics") or {}
        row.update(models_status=_status(models),
                   models_kappa=_num(metrics.get("kappa")),
                   models_kappa_n=_num(metrics.get("kappa_n")))
        for diagram, prefix in (("structural", "structural"), ("behavioral", "behavioral")):
            block = metrics.get(diagram)
            if isinstance(block, dict):
                row[f"{prefix}_syntax_gate"] = block.get("gate", "")
                row[f"{prefix}_syntax_validity"] = _num(block.get("syntax_validity", ""))
                row[f"{prefix}_semantic_recall"] = _num(block.get("recall", ""))
                row[f"{prefix}_semantic_precision"] = _num(block.get("precision", ""))

    vmx = grading.get("vmx")
    if vmx:
        metrics = (vmx.get("details") or {}).get("metrics") or {}
        row.update(vmx_status=_status(vmx),
                   vmx_requirement_coverage=_num(
                       (metrics.get("coverage") or {}).get("score", "")),
                   vmx_referential_integrity=_num(
                       (metrics.get("integrity") or {}).get("score", "")))
    return row


def collect(generated: Path) -> list[dict[str, object]]:
    """Rows of every run under `generated`; an unreadable report is skipped loudly."""
    rows = []
    for run, path in find_reports(generated).items():
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"skipped {path}: {error}", file=sys.stderr)
            continue
        rows.append(row_for(run, report))
    return rows


def render_table(rows: list[dict[str, object]]) -> str:
    """The printed table: one line per run, columns padded to their widest cell."""
    body = [[str(r[column]) for _, column in TABLE] for r in rows]
    headers = [header for header, _ in TABLE]
    widths = [max(len(h), *(len(line[i]) for line in body)) if body else len(h)
              for i, h in enumerate(headers)]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()

    return "\n".join([line(headers), line(["-" * w for w in widths]),
                      *(line(b) for b in body)])


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def summarize(generated: str | Path = DEFAULT_DIR, out: str | Path | None = None) -> int:
    """Print the table and write the CSV (`<generated>/final_metrics.csv` by default)."""
    generated = Path(generated)
    rows = collect(generated)
    if not rows:
        print(f"no report_<run>.json found under {generated}/", file=sys.stderr)
        return 1
    print(render_table(rows))
    target = Path(out) if out else generated / DEFAULT_OUT
    write_csv(rows, target)
    print(f"\n{len(rows)} run(s) -> {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Table and CSV of the final metrics of every graded run")
    parser.add_argument("generated", nargs="?", default=DEFAULT_DIR,
                        help=f"directory holding the run directories (default {DEFAULT_DIR})")
    parser.add_argument("-o", "--out", default=None,
                        help=f"CSV to write (default <generated>/{DEFAULT_OUT})")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    return summarize(args.generated, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
