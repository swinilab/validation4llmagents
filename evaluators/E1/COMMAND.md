# E1 — manual test commands

Every command below was run against this checkout and its real output recorded.
Copy-paste them in order to exercise the module by hand.

The rules themselves, and the 1.1.0 changelog, are in [README.md](README.md).

E1 is stage 1 of the matching cascade (E1 normalize → E2 ontology → E3 embedding
→ E4 human). It normalizes text and flags negation and state words. **It never
decides whether two items match.**

---

## 0. Prerequisites

Run everything **inside WSL**. The `.venv` in this repo is a Linux venv — its
`python` symlinks are unusable from Windows, and the Windows Python has no
spaCy.

```bash
cd /home/swe/validation4llmagents
export PYTHONPATH=.
```

Both lines matter:

- **`cd` to the repo root** — the ontology path in `config.yaml` resolves
  relative to it.
- **`export PYTHONPATH=.`** — `evaluators/` has no `__init__.py`, so it is a
  namespace package. Without this you get `No module named evaluators`.

Check the interpreter has what it needs:

```bash
.venv/bin/python -c "import spacy, yaml; print(spacy.__version__, yaml.__version__)"
.venv/bin/python -c "import spacy; print(spacy.load('en_core_web_sm').meta['version'])"
```

Expected: `3.8.7 6.0.3` and `3.8.0`. If either fails:

```bash
uv pip install -r evaluators/E1/requirements.txt
uv pip install click        # spaCy's CLI needs it; not pulled in automatically
```

Show the CLI contract:

```bash
.venv/bin/python -m evaluators.E1 --help
```

---

## 1. Single strings (`--source text`)

Prints JSON to stdout and writes nothing. The fastest way to check behavior.

```bash
.venv/bin/python -m evaluators.E1 --source text \
  --text "The system shall not refund the payment."
```

```json
{
  "raw": "The system shall not refund the payment.",
  "normalized": "system not refund payment",
  "has_negation_cue": true,
  "main_predicate_negated": true,
  "negation_scope": "main",
  "negation_cues": ["not"],
  "state_mentions": [],
  "e1_version": "1.1.0"
}
```

### The spec table, one command each

```bash
E1=".venv/bin/python -m evaluators.E1 --source text --text"

$E1 "The system shall not refund the payment."
$E1 "The system shall refund the payment."
$E1 "The system verifies current inventory levels."
$E1 "The system updates the order to a payment failed state."
$E1 "The Warehouse team hands the packages over to external carriers and updates the order to a shipped state."
$E1 "The carrier shipped the goods."
$E1 "A Customer can manually cancel an order only if it is in the placed state."
$E1 "The system shall sustain 2,000 concurrent user sessions with a request error rate of no more than 0.1%."
```

Verified `normalized` / `negation_scope` / `state_mentions`:

| Input (abbreviated) | `normalized` | `scope` | `state_mentions` |
|---|---|---|---|
| shall **not** refund | `system **not** refund payment` | `main` | — |
| shall refund | `system refund payment` | `none` | — |
| verifies … levels | `system verify current inventory levels` | `none` | — |
| … to a payment failed state | `system update order to payment failed state` | `none` | `payment failed` |
| Warehouse … shipped state | `… update order to **shipped** state` | `none` | `shipped` |
| carrier **shipped** the goods | `carrier **ship** goods` | `none` | — |
| … only if … placed state | `customer manually cancel order only if it be in placed state` | `none` | `placed` |
| … no more than 0.1% | `… with request error rate of no more than 0.1%` | `none` | — |

The two things to look at:

- **Rows 1–2 differ by exactly one token.** Since 1.1.0 the cue is kept, so the
  two strings are no longer identical — `not` is there, and the scope flips.
- **Rows 5–6 are the state-protection test.** `shipped` stays `shipped` before
  `state`, but lemmatizes to `ship` as a predicate.

### Negation cues

```bash
$E1 "The system shall store no unencrypted primary account numbers in any log."      # no
$E1 "... modifiable by no role."                                                     # no
$E1 "The system shall support a 3x increase without modification to code."           # without
$E1 "The system can never expose the primary account number."                        # never
$E1 "The order cannot be cancelled after picking."                                   # cannot
$E1 "The system doesn't retain the card number."                                     # n't
```

Every one of those comes back `main_predicate_negated: true` except the last
(`without`, an adjunct → `negation_scope: subordinate`).

Not negation — these must come back `has_negation_cue: false`:

```bash
$E1 "A Customer can cancel an order only if it is in the placed state."   # "only if"
$E1 "The system halts the workflow when validation fails."                # "halts", "fails"
$E1 "... error rate of no more than 0.1%."                                # a bound
```

### Labels (`--label`)

Uses `normalize_label`: never drops the first token, never strips actors.

```bash
.venv/bin/python -m evaluators.E1 --source text --label --text "OrderLine"
.venv/bin/python -m evaluators.E1 --source text --label --text "payment_failed"
.venv/bin/python -m evaluators.E1 --source text --label --text "Validate payment"
.venv/bin/python -m evaluators.E1 --source text --label --text "[stock available]"
```

| Input | `normalized` |
|---|---|
| `OrderLine` | `order line` |
| `payment_failed` | `payment failed` |
| `Validate payment` | `validate payment` |
| `[stock available]` | `stock available` |

The difference `--label` makes — a head word that looks like an article:

```bash
.venv/bin/python -m evaluators.E1 --source text --label --text "The Order"   # -> "the order"
.venv/bin/python -m evaluators.E1 --source text         --text "The Order"   # -> "order"
```

### Value preservation

```bash
$E1 "Data shall use tls 1.2 and aes-256 over a 30-day window at 99.9% uptime."
```

`tls 1.2`, `aes-256`, `30-day` and `99.9%` all survive intact.

---

## 2. Files — the four presets

`--out` is optional. Omitted, output goes to `evaluators/E1/artifact/` as
`<input-stem>__e1.csv`.

```bash
.venv/bin/python -m evaluators.E1 --source gold-reqs \
  --in materials/M4-gold-v0.2/gold/gold-requirements.csv

.venv/bin/python -m evaluators.E1 --source class-inv \
  --in materials/M4-gold-v0.2/gold/gold-class-elements.csv

.venv/bin/python -m evaluators.E1 --source activity-inv \
  --in materials/M4-gold-v0.2/gold/gold-activity-elements.csv

.venv/bin/python -m evaluators.E1 --source reqs-json \
  --in evaluators/E1/tests/fixtures/requirements.json
```

Verified output:

```
E1 1.0.0: 49 rows  -> evaluators/E1/artifact/gold-requirements__e1.csv      (normalized: statement)
E1 1.0.0: 103 rows -> evaluators/E1/artifact/gold-class-elements__e1.csv    (normalized: canonical_name, detail)
E1 1.0.0: 44 rows  -> evaluators/E1/artifact/gold-activity-elements__e1.csv (normalized: verb, object, detail)
E1 1.0.0: 3 rows   -> evaluators/E1/artifact/requirements__e1.csv           (normalized: statement)
```

| `--source` | Format | Columns normalized |
|---|---|---|
| `reqs-json` | JSON array | `statement` |
| `gold-reqs` | CSV | `statement` |
| `class-inv` | CSV | `canonical_name`, `detail` (when non-empty) |
| `activity-inv` | CSV | `verb`, `object`, `detail` (when non-empty) |

On a real agent run:

```bash
.venv/bin/python -m evaluators.E1 --source reqs-json --in outputs/raw/RUN01/requirements.json
```

### A specific name, or JSONL

```bash
.venv/bin/python -m evaluators.E1 --source gold-reqs \
  --in materials/M4-gold-v0.2/gold/gold-requirements.csv \
  --out evaluators/E1/artifact/gold_v2.jsonl
```

A `.jsonl` extension switches the writer; anything else is CSV.

### An explicit config

```bash
.venv/bin/python -m evaluators.E1 --source text --config config.yaml \
  --text "The system shall refund the payment."
```

---

## 3. Inspecting the output

```bash
# the 5 added columns
head -1 evaluators/E1/artifact/gold-requirements__e1.csv | tr ',' '\n' | tail -5

# row parity: 50 = 49 rows + header, both sides
wc -l < materials/M4-gold-v0.2/gold/gold-requirements.csv
wc -l < evaluators/E1/artifact/gold-requirements__e1.csv

# the metadata sidecar
cat evaluators/E1/artifact/gold-requirements__e1.csv.meta.json
```

Added columns, verified:

```
statement__normalized, statement__has_negation_cue, statement__main_predicate_negated,
statement__negation_scope, statement__negation_cues, statement__state_mentions, e1_version
```

`.meta.json` keys, verified:

```
config, e1_version, input, library_versions, ontology_path, ontology_sha256, row_count, source
```

Every statement carrying a negation cue, with the scope the parser assigned
(on the gold set: six rows carry a cue, and only GR-30 is `main`):

```bash
.venv/bin/python - <<'PY'
import csv
rows = list(csv.DictReader(open("evaluators/E1/artifact/gold-requirements__e1.csv", encoding="utf-8-sig")))
for r in rows:
    if r["statement__has_negation_cue"] == "true":
        print(r["gold_req_id"], "|", r["statement__negation_scope"],
              "|", r["statement__negation_cues"], "|", r["statement__normalized"][:60])
print(len(rows), "rows total")
PY
```

Every state mention found:

```bash
.venv/bin/python - <<'PY'
import csv
for r in csv.DictReader(open("evaluators/E1/artifact/gold-requirements__e1.csv", encoding="utf-8-sig")):
    if r["statement__state_mentions"]:
        print(r["gold_req_id"], "->", r["statement__state_mentions"])
PY
```

---

## 4. Hard constraints

### The input file is never modified

```bash
G=materials/M4-gold-v0.2/gold/gold-requirements.csv
sha256sum $G > /dev/shm/e1_before
.venv/bin/python -m evaluators.E1 --source gold-reqs --in $G
sha256sum -c /dev/shm/e1_before && echo "INPUT UNCHANGED"
```

Verified: digest identical before and after (`5a8e1269b834ac77…`).

### Two runs are byte-identical

```bash
.venv/bin/python -m evaluators.E1 --source gold-reqs --in $G --out evaluators/E1/artifact/det1.csv
.venv/bin/python -m evaluators.E1 --source gold-reqs --in $G --out evaluators/E1/artifact/det2.csv
cmp evaluators/E1/artifact/det1.csv evaluators/E1/artifact/det2.csv && echo "BYTE-IDENTICAL"
rm evaluators/E1/artifact/det1.csv* evaluators/E1/artifact/det2.csv*
```

Verified identical, 16 599 bytes.

### Nothing is written outside the repo

```bash
.venv/bin/python -m evaluators.E1 --source gold-reqs --in $G --out /tmp/e1.csv    ; echo "exit=$?"
.venv/bin/python -m evaluators.E1 --source gold-reqs --in $G --out ../outside.csv ; echo "exit=$?"
```

Both refused with `exit=2`:

```
E1 error: Refusing to write outside the repository: /tmp/e1.csv.
E1 writes only inside /home/swe/validation4llmagents; omit --out to use
the default evaluators/E1/artifact/ directory.
```

### The ontology is read-only

```bash
sha256sum materials/M2-orderman-ontology.yaml
# matches ontology_sha256 in every .meta.json: 759fed00b964eb6b21a62e6b…
```

### Offline

No network is used. To prove it, unset resolution and rerun:

```bash
( unset http_proxy https_proxy; .venv/bin/python -m evaluators.E1 --source gold-reqs --in $G )
```

---

## 5. Error paths — all exit non-zero

```bash
# missing required column
.venv/bin/python -m evaluators.E1 --source gold-reqs \
  --in evaluators/E1/tests/fixtures/bad-columns.csv ; echo "exit=$?"

# input file does not exist
.venv/bin/python -m evaluators.E1 --source gold-reqs --in does/not/exist.csv ; echo "exit=$?"

# unknown source
.venv/bin/python -m evaluators.E1 --source nope ; echo "exit=$?"

# missing arguments
.venv/bin/python -m evaluators.E1 --source text      ; echo "exit=$?"
.venv/bin/python -m evaluators.E1 --source gold-reqs ; echo "exit=$?"
```

Verified:

| Case | Exit | Message |
|---|---|---|
| missing column | `2` | `E1 error: …bad-columns.csv: --source gold-reqs requires column(s) statement, which are not present. Columns found: gold_req_id, tier, requirement_text.` |
| missing file | `2` | `E1 error: Input file not found: does/not/exist.csv` |
| unknown source | `2` | `argparse: invalid choice: 'nope'` |
| `text` without `--text` | `2` | `E1 error: --source text requires --text.` |
| `gold-reqs` without `--in` | `2` | `E1 error: --source gold-reqs requires --in.` |

> **Careful reading exit codes through `wsl.exe` from PowerShell.** That wrapper
> swallows `$?` and truncates stderr — a failing command appears to exit 0.
> Check exit codes from inside WSL, or via `subprocess` in Python.

---

## 6. From Python (how E2 calls E1)

```bash
.venv/bin/python - <<'PY'
from evaluators.E1 import normalize, normalize_label, run_e1, E1_VERSION

print("E1", E1_VERSION)

r = normalize("The system updates the order to a payment failed state.")
print(r.normalized)       # system update order to payment failed state
print(r.state_mentions)   # ['payment failed']
print(r.negation_scope)   # none

n = normalize("The system shall not refund the payment.")
# 1.1.0: the cue stays in `normalized`, and scope is reported separately.
print(n.normalized)                        # system not refund payment
print(n.has_negation_cue, n.negation_cues) # True ['not']
print(n.main_predicate_negated)            # True

print(normalize_label("OrderLine").normalized)   # order line

# per-token detail, incl. why each token was dropped
for t in normalize("The system shall refund the payment.").tokens:
    print(f"  {t['text']:9s} {t['pos']:6s} kept={t['kept']!s:5s} {t.get('reason_removed','')}")

# batch, without shelling out; out_path=None -> evaluators/E1/artifact/
print(run_e1("gold-reqs", "materials/M4-gold-v0.2/gold/gold-requirements.csv"))
PY
```

---

## 7. From Windows PowerShell

```powershell
wsl.exe -d Ubuntu -- bash -c 'cd /home/swe/validation4llmagents; PYTHONPATH=. .venv/bin/python -m evaluators.E1 --source text --text "The system shall not refund the payment."'
```

Works, but see the exit-code caveat in §5. Prefer a WSL shell for real testing.

---

## 8. Tidying up

`evaluators/E1/artifact/` is gitignored except for its `.gitignore`, so generated
files never reach a commit. To clear it:

```bash
find evaluators/E1/artifact -type f ! -name .gitignore -delete
git status --short        # only the .gitignore should ever be tracked
```

---

## Not yet available

`pytest evaluators/E1/tests` currently **collects nothing** — `conftest.py` and
the fixtures exist, but the four test modules (`test_normalize.py`,
`test_negation.py`, `test_states.py`, `test_cli.py`) are not written yet. Until
they are, the commands above are the way to test E1. The intended command:

```bash
.venv/bin/python -m pytest evaluators/E1/tests -v
```
