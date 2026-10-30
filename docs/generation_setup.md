# Generation setup — how the nine SRS packages were produced

This document records the **generation side** of the study: who or what produced
the SRS packages that the validation pipeline then scores, with which model, which
prompt and which settings. It is written as source material for the method and
threats-to-validity sections of the paper. The scoring side is in
[validation_pipeline.md](validation_pipeline.md).

Status: 2026-10-29. Every number comes from a file in `generated/<run>/` or from the
code; a statement that could not be checked from those is marked *not verified*.
This file replaces `GENERATION_RUN.md`, which described one ChatDev run
(`RUN_20261026_GPTOSS120B`).

---

## 1. At a glance

| Item | Value |
|---|---|
| Task given to each generator | Write a complete SRS for an order-management system from 50 functional and 8 non-functional domain requirements |
| Generator systems compared | **3**: ChatDev multi-agent workflow on `gpt-oss:120b`; Claude Code (Opus 5.5); Google Antigravity (Gemini 3.8 Flash, High) |
| Runs per system | **3** → 9 runs in total |
| Prompt | `materials/M1-prompt.md` with `{{FR_INPUT}}` / `{{NFR_INPUT}}` filled from `materials/M1a.json` (23,658 characters after injection) |
| Deliverables per run | `srs.md`, `structural.puml`, `behavioral.puml`, `requirements.json`, `VMX.csv` — all nine runs delivered all five files |
| Seeds | none, in any system |
| Gold standard visible to the generator | never; its only input is the prompt |

The comparison is between **agent systems** (model plus scaffolding plus tool), not
between models: the three systems differ in model, in the number of agent roles and
in the tool that drives them (§6).

---

## 2. The nine runs

| Run | System | Model | How it was driven | Duration | Effort measure |
|---|---|---|---|---|---|
| `gptoss-1` | ChatDev_v1 workflow | `gpt-oss:120b` | `main.py --phase gen` | 163 s | 24 model calls, 302,547 tokens |
| `gptoss-2` | ChatDev_v1 workflow | `gpt-oss:120b` | `main.py --phase gen` | 117 s | 20 model calls, 312,805 tokens |
| `gptoss-3` | ChatDev_v1 workflow | `gpt-oss:120b` | `main.py --phase gen` | 91 s | 24 model calls, 276,329 tokens |
| `claude-code-1` | Claude Code CLI v2.1.311 | Opus 5.5 (Claude Pro) | prompt pasted into a fresh session | "Cooked for 5m 46s" | not recorded |
| `claude-code-2` | Claude Code CLI v2.1.311 | Opus 5.5 (Claude Pro) | prompt pasted into a fresh session | "Cogitated for 6m 3s" | not recorded |
| `claude-code-3` | Claude Code CLI v2.1.311 | Opus 5.5 (Claude Pro) | prompt pasted into a fresh session | "Churned for 5m 22s" | not recorded |
| `antigravity-1` | Google Antigravity agent | Gemini 3.8 Flash (High) | prompt pasted into a new conversation | 12.7 min | 63 steps |
| `antigravity-2` | Google Antigravity agent | Gemini 3.8 Flash (High) | prompt pasted into a new conversation | 16.4 min | 89 steps |
| `antigravity-3` | Google Antigravity agent | Gemini 3.8 Flash (High) | prompt pasted into a new conversation | 12.1 min | 64 steps |

Where each figure comes from:

- ChatDev: `token_usage_*.json` (`total_usage`, length of `call_history`) and the first
  and last timestamp in `execution_logs.json`. The three runs started at 12:59:15,
  13:00:26 and 13:00:45 on 2026-10-27 and finished at 13:01:59, 13:02:23 and
  13:02:16, so **they ran concurrently** against the same endpoint.
- Claude Code: the session banner (`Claude Code v2.1.311`, `Opus 5.5 · Claude Pro`) and
  the completion line at the end of each transcript. That duration is what the CLI
  printed for the last turn; whether the whole task was one turn was *not verified*.
- Antigravity: the model is named in the transcript line "the user changed setting
  `Model Selection` from None to Gemini 3.8 Flash (High)"; steps and duration come
  from the transcript headers (`Total steps`, first and last message timestamp,
  2026-10-27 06:45–07:02 UTC).
- Transcripts are kept next to each run: `generated/claude-code-N/claude-N-conversation.md`
  and `generated/antigravity-N/conversation.md`.

---

## 3. Input

### 3.1 Prompt

`materials/M1-prompt.md` is one prompt. In order, it contains:

1. **Role and task.** "You are a requirements engineer"; produce an SRS in which every
   functional requirement is a user story with acceptance criteria.
2. **Domain requirements.** The three business roles (Customer, OrderStaff,
   Accountant) and the placeholders `{{FR_INPUT}}` and `{{NFR_INPUT}}`.
3. **Requirement style.** User-story template, the rule that the agent decides story
   granularity itself, at least three acceptance criteria per story (Given-When-Then
   or Condition form), NFRs as quantified `shall` statements without acceptance
   criteria, identifier patterns (`US-NN`, `NFR-NN`, `US-NN-ACNN`) and ordering.
4. **Output standard.** Clause structure of `srs.md`.
5. **Diagrams.** A structural PlantUML class diagram (classes, typed attributes,
   enums for restricted value sets, relationships with multiplicities, composition
   where an entity has no meaning apart from its owner) and a behavioral PlantUML
   activity diagram (initial and final nodes, decisions with guards, fork/join, loops
   for retries, `:Entity [status];` object nodes, swimlanes per role).
6. **Output files.** Exactly five files with exact names, plus the schema of
   `requirements.json`.
7. **Traceability.** Format of `VMX.csv`: header
   `SRS-Req-ID,Domain-Req-ID,Structural-Elements,Behavorial-Elements` (the column is
   spelled `Behavorial` in the prompt and in the grader), semicolon-separated values,
   names copied exactly from the diagrams and the domain input.

### 3.2 Domain requirements

`materials/M1a.json` holds `FR_INPUT` (`REQ-F-01` … `REQ-F-50`) and `NFR_INPUT`
(`REQ-N-01` … `REQ-N-08`), one `shall` statement each. `workflow_pipeline._read_prompt`
injects them as bullet lines (`- **REQ-F-01**: <statement>`). The same file is the
rubric's traceability input and the `Domain-Req-ID` vocabulary in grading
(`gold.domain` in `config.yaml`).

### 3.3 Was the prompt the same in all nine runs?

- **ChatDev runs:** built by `_read_prompt` from the files above, so identical by
  construction.
- **Antigravity runs:** the user message in all three transcripts is **character for
  character identical** to the text `_read_prompt` produces (checked).
- **Claude Code runs:** the transcripts begin with the same text, but they are
  terminal captures. A comparison that ignores whitespace did **not** match the
  expected text (I did not investigate why; terminal rendering is the likely cause),
  so equality could not be shown. State this as "the same prompt file was used", not
  as "byte-identical".

---

## 4. System A — ChatDev workflow on `gpt-oss:120b` (`gptoss-1..3`)

### 4.1 Agent and model

`agents/gen.py` (`ChatDevGenerationAgent`) calls the ChatDev SDK
(`chatdev.run_workflow`) with the workflow `ChatDev_v1.yaml` shipped inside the
installed `chatdev` package. It passes `BASE_URL`, `API_KEY` and `MODEL_NAME` and
overrides the `model` of **every agent node** with `agent.model`, so a single model
plays all roles. The workflow YAML is not copied or edited by this repository.

| Setting | Value |
|---|---|
| Model | `gpt-oss:120b`, an Ollama tag with no snapshot id |
| Endpoint | Ollama Cloud, `https://ollama.com/v1` (OpenAI-compatible) |
| Temperature | **0.7**, ChatDev's default (the workflow nodes set none; `agents/gen.py` records it as `CHATDEV_DEFAULT_TEMPERATURE`) |
| Max output tokens | not set (provider default) |
| Package | `chatdev` 0.1.0, workflow `ChatDev_v1` |

`agent.temperature: 0.2` in `config.yaml` is **not** applied on this path; it is only
read by a fallback branch that is never reached. Do not report 0.2.

### 4.2 Workflow structure

Seven agent nodes (role prompts as shipped in the package; all with the same file
and folder tools: `save_file`, `apply_text_edits`, `read_file_segment`,
`search_in_files`, `list_directory`, `create_folder`, `delete_path`,
`describe_available_files`, plus the `uv_related` tools). Loop counters bound each
phase:

| Phase | Agent nodes | Loop bound | Exit condition |
|---|---|---|---|
| Coding | Programmer Coding | — | single pass |
| Code completion | Programmer Code Complete | 5 | reply contains `<INFO> FINISHED` |
| Code review | Code Reviewer ↔ Programmer Code Review | 10 | reviewer reply contains `<INFO> Finished` |
| Test | Programmer Test Error Summary, Programmer Test Modification, Software Test Engineer | 3 (phase), 5 (modification) | `<INFO>` in reply |
| Manual | Chief Product Officer, Chief Executive Officer | 1 | loop counter |

The role prompts describe building *software*; the task text in the prompt is what
turns the pipeline into SRS authoring. The test phase therefore executes nothing
meaningful for this task.

### 4.3 What the three runs actually executed

Node executions (`node_execution_counts` in `token_usage_*.json`):

| Node | gptoss-1 | gptoss-2 | gptoss-3 |
|---|---:|---:|---:|
| Programmer Coding | 1 | 1 | 7 |
| Programmer Code Complete | 4 | 4 | 2 |
| Code Reviewer | 4 | 3 | 2 |
| Programmer Test Error Summary | 1 | 1 | 1 |
| Programmer Test Modification | 7 | 9 | 6 |
| Software Test Engineer | 2 | 0 | 1 |
| Chief Product Officer | 4 | 1 | 4 |
| Chief Executive Officer | 1 | 1 | 1 |
| Tokens (input / output) | 252,702 / 49,845 | 273,095 / 39,710 | 250,056 / 26,273 |

Same configuration, three different execution paths: the number of calls, the
amount of rework and the final tokens vary from run to run. This is the generator
variance the three-run design is meant to expose.

The deliverables are written by the agents through tool calls (`save_file`,
`apply_text_edits`), not extracted from chat text; the graded files are the last
versions saved before the workflow ended.

---

## 5. Systems B and C — single-agent tools driven by hand

### 5.1 Claude Code (`claude-code-1..3`)

- Claude Code CLI v2.1.311, model shown in the banner as **Opus 5.5**, on a Claude Pro
  plan.
- Each run was a fresh session in its own empty directory (`~\Desktop\claude-code-N`);
  the prompt was pasted as the first message.
- The agent wrote the five files itself. In `claude-code-1` the closing message lists
  the assumptions it made (for example who creates products, how the bank account is
  modelled); the other transcripts were not read for this.
- Not recorded in the transcripts, so not reportable: temperature and other sampling
  parameters, the tool's system prompt, token counts.

### 5.2 Google Antigravity (`antigravity-1..3`)

- Antigravity agent with the model setting changed to **Gemini 3.8 Flash (High)**
  at the start of the conversation.
- Each run was a new conversation; the prompt was sent as one user message wrapped in
  `<USER_REQUEST>`. Exports were produced from `transcript_full.jsonl`.
- The three conversations started 06:45:57, 06:46:00 and 06:46:02 UTC, i.e. within five
  seconds of each other, and ended after 12.1 to 16.4 minutes.
- Not recorded: sampling parameters and token counts.

### 5.3 How these runs enter the pipeline

Their files sit directly in `generated/<run>/` (no `sdk_*` folder). The pipeline
grades a directory like that by treating it as the workspace
(`_standalone_generation`), and the generation record in the report says
`LLM: standalone`. The generator column of the report is therefore **not**
informative for runs 4–9; the table in §2 is the record of who produced what.

---

## 6. What differs between the systems

| | ChatDev (A) | Claude Code (B) | Antigravity (C) |
|---|---|---|---|
| Model family | OpenAI open-weights (`gpt-oss:120b`) | Anthropic (Opus 5.5) | Google (Gemini 3.8 Flash) |
| Agent roles | 7 role prompts in a looped workflow | 1 agent | 1 agent |
| Review / test phases | yes (they add little for a documentation task) | none in the prompt | none in the prompt |
| Driven by | script, automatic | human pasting the prompt | human pasting the prompt |
| Sampling known | temperature 0.7 | no | no |
| Runs concurrent | yes | no | yes (within seconds) |

Consequences to state in the paper: a difference in the metrics cannot be attributed
to the model alone; n = 3 per system gives a rough idea of variance, not a
significance test; the human-driven runs are not scripted and cannot be replayed
exactly.

The judge used in grading (`deepseek-v4.1-flash:cloud`) belongs to none of the three
families, which satisfies the requirement in M2 §2.3 that the judge differ from the
generator's family.

---

## 7. Outputs

```
generated/<run>/
├── sdk_ChatDev_v1_<timestamp>_<timestamp>/   ChatDev runs only, left untouched
│   ├── code_workspace/   srs.md structural.puml behavioral.puml requirements.json VMX.csv
│   ├── execution_logs.json   every node start/end, model call, tool call, error
│   ├── node_outputs.yaml     final output of each node
│   ├── token_usage_<workflow>.json
│   └── workflow_summary.yaml
├── srs.md structural.puml behavioral.puml requirements.json VMX.csv   (Claude Code, Antigravity)
├── claude-N-conversation.md / conversation.md                          transcript
├── grading/{reqs,models,vmx}/   written by the validation pipeline
├── report_<run>.json            raw report
└── report_<run>.txt             rendered from the JSON
```

### 7.1 What the nine packages look like

Counts are taken from `requirements.json` of each run (a `US-*` entry carries its
acceptance criteria; `NFR-*` entries are single statements). The gold standard has
62 acceptance criteria + 8 NFRs = **70 units**, 50 structural elements and 39
behavioral elements.

| Run | `srs.md` lines | User stories | Acceptance criteria | NFRs | VMX rows | Generated elements (structural / behavioral) |
|---|---:|---:|---:|---:|---:|---|
| antigravity-1 | 216 | 12 | 66 | 8 | 20 | 50 / 43 |
| antigravity-2 | 220 | 10 | 53 | 8 | 18 | 50 / 43 |
| antigravity-3 | 188 | 10 | 45 | 8 | 18 | 50 / 36 |
| claude-code-1 | 271 | 12 | 77 | 8 | 20 | 49 / 49 |
| claude-code-2 | 300 | 12 | 85 | 8 | 20 | 51 / 49 |
| claude-code-3 | 308 | 12 | 91 | 8 | 20 | 49 / 49 |
| gptoss-1 | 159 | 13 | 40 | **7** | 20 | 49 / 47 |
| gptoss-2 | 104 | 20 | 61 | 8 | 28 | 56 / 107 |
| gptoss-3 | 294 | 10 | 40 | 8 | **37** | 58 / 75 |

Things worth a sentence in the paper:

- The prompt leaves story granularity to the agent, so the number of stories (10–20)
  and of acceptance criteria (40–91) differs a lot; the gold has 15 stories and 62
  criteria. This feeds directly into Requirement Recall and Precision.
- `gptoss-1` has 7 NFRs, one fewer than the 8 given. `gptoss-3` has 37 VMX rows for
  18 requirements. Both are generator behaviour, not grading artefacts.
- `gptoss-2` produced 107 behavioral elements against 39 in the gold, a very different
  size from the other runs.

---

## 8. Reproducing the generation

```bash
uv run main.py --phase gen --run-id RUN_<name>        # ChatDev system only
```

Before the first run: copy `config.example.yaml` to `config.yaml` and set
`agent.model`, `agent.api_base`, `agent.api_key`. Environment: Python ≥ 3.12,
`chatdev` 0.1.0 (resolved in `uv.lock`).

What is **not** reproducible:

- the endpoint serves `gpt-oss:120b` as a moving tag; no seed is passed; temperature
  is 0.7, so two runs of the same command differ (§4.3 shows how much);
- the Claude Code and Antigravity runs were interactive; the models and tool versions
  may have changed since, and sampling parameters were not recorded.

---

## 9. Points to state in the paper

1. Three generator systems × three runs; prompt identical in text (verified
   character-for-character for Antigravity and ChatDev by construction, by file for
   Claude Code).
2. ChatDev: one model on all seven roles, temperature 0.7 (not the 0.2 in
   `config.yaml`), no seed, model tag not pinned.
3. Claude Code: Opus 5.5, CLI v2.1.311; Antigravity: Gemini 3.8 Flash (High);
   sampling parameters unknown for both.
4. The systems differ in more than the model; do not claim a model ranking.
5. The prompt fixes format and clause structure but not granularity, so the
   generated requirement sets differ in size from the gold (70 units) and from each
   other (§7.1).
6. The generator saw only `M1a.json` through the prompt; gold models and grading
   rules were never visible to it.
7. Effort: ChatDev 91–163 s and 276–313 k tokens per run; Claude Code about 5–6
   minutes per run; Antigravity 12–16 minutes and 63–89 steps per run. These are not
   directly comparable (different clocks, different units).

## 10. Implementation notes (not for the paper body)

- `config.yaml` keys `agent.type`, `agent.workflow`, `agent.stream`,
  `agent.max_tokens`, `agent.temperature` and `agent.timeout` have no effect on the
  ChatDev path: `agents/gen.py` hard-codes `ChatDev_v1.yaml`, and the direct-API branch
  after the ChatDev branch is unreachable.
- `materials/M1a-elaboration.json` (30 functional requirements, 8 NFRs) is not
  referenced by the pipeline.
- The earlier reference run `RUN_20261026_GPTOSS120B` (ChatDev, `gpt-oss:120b`,
  114.8 s, 26 calls, 365,887 tokens) is no longer in the working tree. It is in git
  history (commit `507cab9`, "Done empirical runs") and is not one of the nine runs
  reported here.
