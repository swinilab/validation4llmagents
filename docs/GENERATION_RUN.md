# Generation phase — what was run and how

This document records the **generation phase** of the study (the step that
produces the SRS package that the grading modules in `evaluators/` then score). It
is written to support the method and threats-to-validity sections of the paper.
Every number below comes from the run directory
`generated/RUN_20261026_GPTOSS120B/` or from the code; nothing is estimated.

Grading is documented separately: `RequirementsGrading/README.md`,
`ModelsGrading/README.md`, `VMXGrading/README.md`.

---

## 1. At a glance

| Item | Value |
|---|---|
| Task given to the agent | Write a complete SRS for an order-management system from 50 functional and 8 non-functional domain requirements |
| Generator | ChatDev multi-agent workflow (`chatdev` 0.1.0, workflow `ChatDev_v1`, 26 nodes, 54 edges) |
| Underlying LLM | `gpt-oss:120b`, served by Ollama Cloud (OpenAI-compatible endpoint `https://ollama.com/v1`), same model on every agent node |
| Sampling temperature | **0.7** (ChatDev's default; the workflow nodes set none). `agent.temperature: 0.2` in `config.yaml` is **not** used on this path (see §6) |
| Max output tokens | not set (provider default) |
| Seed | none |
| Prompt | `materials/M1-prompt.md` with `{{FR_INPUT}}` / `{{NFR_INPUT}}` filled from `materials/M1a.json` |
| Deliverables | `srs.md`, `structural.puml`, `behavioral.puml`, `requirements.json`, `VMX.csv` |
| Runs reported | 1 (`RUN_20261026_GPTOSS120B`) |

The generator never sees the gold standards (`materials/G1`–`G4`) or the grading
configuration. Its only input is the prompt.

---

## 2. Input

### 2.1 Prompt

`materials/M1-prompt.md` is a single prompt (about 14.7 KB before injection). It
contains, in order:

1. **Role and task.** "You are a requirements engineer"; produce an SRS in which every
   functional requirement is a user story with acceptance criteria.
2. **Domain requirements.** The three business roles (Customer, OrderStaff,
   Accountant) and the two placeholders `{{FR_INPUT}}` and `{{NFR_INPUT}}`.
3. **Requirement style.** User-story template (`As a <role>, I want <capability>, so
   that <benefit>`), the rule that the agent decides story granularity itself, at
   least three acceptance criteria per story (Given-When-Then or Condition form),
   NFRs as quantified `shall` statements with no acceptance criteria, identifier
   patterns (`US-NN`, `NFR-NN`, `US-NN-ACNN`), and the required ordering.
4. **Output standard.** The clause structure of `srs.md` (Introduction, Overall
   description, Requirements with 3.1 functional and 3.2.1–3.2.3 quality
   attributes, Verification, Supporting information).
5. **Diagrams.** A structural PlantUML class diagram (classes, typed attributes,
   enums for restricted value sets, relationships with multiplicities, composition
   where an entity has no meaning apart from its owner) and a behavioral PlantUML
   activity diagram (one initial node, final nodes, decisions with guards, fork/join
   for independent work, loops for retries, `:Entity [status];` object nodes,
   swimlanes per role).
6. **Output files.** Exactly five files, with exact names, plus the full schema of
   `requirements.json`.
7. **Traceability.** The format of `VMX.csv`: header
   `SRS-Req-ID,Domain-Req-ID,Structural-Elements,Behavorial-Elements` (the column
   name is spelled `Behavorial` in the prompt and in the grader), semicolon-separated
   multi-values, names copied exactly from the diagrams and from the domain input.

### 2.2 Domain requirements

`materials/M1a.json` holds `FR_INPUT` (`REQ-F-01` … `REQ-F-50`) and `NFR_INPUT`
(`REQ-N-01` … `REQ-N-08`). Each is one `shall` statement. They are injected by
`workflow_pipeline._read_prompt` as bullet lines, `- **REQ-F-01**: <statement>`,
before the prompt is sent. The same file is the rubric's traceability input and
the `Domain-Req-ID` vocabulary in grading (`gold.domain` in `config.yaml`).

---

## 3. Generator

### 3.1 Agent and model

`agents/gen.py` (`ChatDevGenerationAgent`) calls the ChatDev SDK
(`chatdev.run_workflow`) with the workflow `ChatDev_v1.yaml` that ships inside the
installed `chatdev` package. It passes three variables, `BASE_URL`, `API_KEY`,
`MODEL_NAME`, and overrides the `model` of **every agent node** with
`agent.model`, so a single model plays all roles. The workflow YAML itself is not
copied or edited by this repository.

The endpoint key is read from `agent.api_key` in `config.yaml` (git-ignored). Only
when `agent.api_base` is OpenRouter is `OPENROUTER_API_KEY` required instead.

### 3.2 Workflow structure (ChatDev_v1)

Seven agent nodes (role prompts as shipped in the installed package, all with the same file and
folder tool set: `save_file`, `apply_text_edits`, `read_file_segment`,
`search_in_files`, `list_directory`, `create_folder`, `delete_path`,
`describe_available_files`, and the `uv_related` tools) and loop counters that
bound each phase:

| Phase | Agent nodes | Loop bound | Exit condition |
|---|---|---|---|
| Coding | Programmer Coding | — | single pass |
| Code completion | Programmer Code Complete | 5 | reply contains `<INFO> FINISHED` |
| Code review | Code Reviewer ↔ Programmer Code Review | 10 | reviewer reply contains `<INFO> Finished` |
| Test | Programmer Test Error Summary, Programmer Test Modification, Software Test Engineer | 3 (phase) and 5 (modification) | `<INFO>` in reply |
| Manual (ChatDev's user-manual phase) | Chief Product Officer, Chief Executive Officer | 1 | loop counter |

The role prompts describe building *software*; the task text supplied through the
prompt is what turns the pipeline into SRS authoring. The Test phase therefore does
not execute anything meaningful for this task (§5).

### 3.3 Settings that take effect

| Setting | Source | Effect on this path |
|---|---|---|
| model | `agent.model` | applied to every agent node |
| endpoint | `agent.api_base` | `BASE_URL` of the workflow |
| key | `agent.api_key` | `API_KEY` of the workflow |
| temperature | — | **ChatDev default 0.7**; `agent.temperature` is read only by an unreachable fallback |
| timeout | `agent.timeout` | not passed to ChatDev |
| prompt | `agent.prompt_template`, `agent.prompt_inputs` | read by the pipeline before generation |
| output dir | `agent.generated_dir` + `--run-id` | `generated/<run-id>/` |

---

## 4. Outputs

Everything the generator writes lives in one ChatDev folder inside the run
directory; the grading modules later write next to it, never into it.

```
generated/<RUN_ID>/
├── sdk_ChatDev_v1_<timestamp>_<timestamp>/        # written by ChatDev, left untouched
│   ├── code_workspace/
│   │   ├── srs.md  structural.puml  behavioral.puml  requirements.json  VMX.csv
│   │   └── attachments/
│   ├── execution_logs.json          # every node start/end, model call, tool call, error
│   ├── node_outputs.yaml            # final output of each node
│   ├── token_usage_<workflow>.json  # tokens per node and per call
│   └── workflow_summary.yaml        # workflow definition as executed
├── grading/{reqs,models,vmx}/       # grading output (separate documents)
├── report_<run dir>.json            # raw report, merged across invocations
└── report_<run dir>.txt             # rendered from the JSON by report_to_txt.py
```

The five deliverables are exactly the files the prompt names. They are written by
the agents through tool calls (`save_file`, `apply_text_edits`), not extracted from
chat text.

---

## 5. Reference run: `RUN_20261026_GPTOSS120B`

Source: `execution_logs.json`, `token_usage_*.json`, `workflow_summary.yaml`.

| Item | Value |
|---|---|
| Wall clock | 2026-10-26 15:52:01 → 15:53:56, 114.8 s |
| Model calls | 26 |
| Tokens | 365,887 total (326,300 input, 39,587 output) |
| Nodes executed (19 starts) | USER, Coding Phase Prompt, Programmer Coding, Code Complete Phase, Programmer Code Complete, Code Review Comment Phase, Code Reviewer, Test Error Summary Phase, Programmer Test Error Summary, Test Modification Phase (assistant and user), Programmer Test Modification, PSEUDO, Manual Phase (assistant and user), Chief Product Officer, Chief Executive Officer, Manual Phase Loop Counter, FINAL |
| Not executed | Software Test Engineer, Programmer Code Review |

Calls and tokens by node:

| Node | Calls | Input tokens | Output tokens |
|---|---:|---:|---:|
| Programmer Coding | 6 | 67,115 | 9,377 |
| Programmer Code Complete | 7 | 93,897 | 11,887 |
| Code Reviewer | 2 | 13,505 | 158 |
| Programmer Test Error Summary | 1 | 6,487 | 257 |
| Programmer Test Modification | 1 | 6,673 | 687 |
| Chief Product Officer | 8 | 131,820 | 16,955 |
| Chief Executive Officer | 1 | 6,803 | 266 |

How the deliverables came to be: Programmer Coding wrote a first version of all five
files; Programmer Code Complete revised them with `apply_text_edits`; the Code
Reviewer only listed the directory; the test phase made no change to the files; the
Chief Product Officer rewrote `srs.md`, `structural.puml`, `behavioral.puml`,
`requirements.json` and `VMX.csv` in the manual phase, so **the graded files are the
Chief Product Officer's final saves**.

Tool-call failures (3 in the log), each retried by the agent in the same node:
`apply_text_edits` missing `start_line` (structural.puml), `save_file` with an
invalid `mode` (srs.md), and `save_file` without `path` (requirements.json).

Size of the result: `srs.md` 136 lines; `requirements.json` 18 requirements (10 user
stories with 40 acceptance criteria, and 8 NFRs); `VMX.csv` 18 data rows + header.
The gold standard has 70 units, so the agent chose a coarser granularity than the
gold (the prompt leaves granularity to the agent).

`requirements.json` is stored pretty-printed. It parses to the same JSON object as
the agent's last successful `save_file` of that file (checked against
`execution_logs.json`).

---

## 6. Reproducing the generation

```bash
uv run main.py --phase gen --run-id RUN_<name>
```

`--phase gen` runs generation only; `--phase grade` grades an existing run;
`--phase all` does both. Before the first run: copy `config.example.yaml` to
`config.yaml` and set `agent.model`, `agent.api_base` and `agent.api_key`.
Environment: Python ≥ 3.12, `chatdev` ≥ 0.1.0 (resolved to 0.1.0 in `uv.lock`).

What is **not** reproducible: the endpoint serves `gpt-oss:120b` as a moving tag
(no snapshot id), no seed is passed, and the temperature is 0.7. Two runs of the
same command therefore give different SRS packages; any variance claim needs
several runs.

---

## 7. Points to state in the paper

1. One generator configuration: ChatDev_v1 with one model on all roles; one
   reported run unless more are added.
2. Temperature 0.7 (ChatDev default), not the 0.2 written in `config.yaml`, no seed,
   model tag not pinned to a snapshot.
3. The prompt fixes format and clause structure but leaves story granularity to the
   agent; the output therefore has fewer, coarser requirements than the gold, which
   affects Recall (the gold has 70 units).
4. The generator saw only `M1a.json` through the prompt; gold models and grading
   rules were never visible to it.
5. The test and review phases of ChatDev add little for a documentation task: no
   code is run and the review is a directory listing in the reference run.
6. Token cost and latency: 365,887 tokens and about 115 s for the reference run.

## 8. Implementation notes (not for the paper body)

- `config.yaml` keys `agent.type`, `agent.workflow`, `agent.stream`,
  `agent.max_tokens`, `agent.temperature` and `agent.timeout` have no effect on the
  ChatDev path: `agents/gen.py` hard-codes `ChatDev_v1.yaml`, and the direct-API
  fallback after the ChatDev branch is unreachable (the branch always returns or
  exits).
- `materials/M1a-elaboration.json` (30 functional requirements, 8 NFRs) is not
  referenced by the pipeline.
