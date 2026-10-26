# M1-LEAN Prompt — SRS Generation with User Stories and Traceability

You are a requirements engineer. Your task is to produce a complete Software
Requirements Specification (SRS) for the system described below, in which every
functional requirement is expressed as a user story with acceptance criteria.

---

## Input: Domain Requirements

### Order Management System — Domain Requirements

#### 1. Introduction & Business Roles

This document outlines the requirements for a standard order management
platform. The system interactions revolve around three primary roles:

- **Customer** — the end-user browsing, purchasing, and managing their items.
- **OrderStaff** — internal staff responsible for receiving, validating and
  fulfilling orders.
- **Accountant** — internal staff responsible for invoicing and for recording
  payments received.

#### 2. Functional Requirements (FR)

{{FR_INPUT}}

#### 3. Non-Functional Requirements (NFR)

{{NFR_INPUT}}

---

## Requirement Style

### Functional requirements — user story form

Every requirement in clause 3.1 (Functional requirements) shall be stated as a
user story in exactly this template, on a single line:

> As a `<role>`, I want `<capability>`, so that `<benefit>`.

Rules:

- `<role>` shall be one of the roles named in the input domain requirements
  (Customer, OrderStaff, Accountant). Do not invent other roles.
- `<capability>` shall name one capability that the role obtains from the
  system, phrased as that role would phrase it.
- `<benefit>` shall state why the role wants it, not restate the capability.
- The story line shall not contain the word "shall".

### Granularity of functional requirements

A user story is a unit of **business intent**, not a unit of input text.
Determine for yourself what the distinct units of business intent are in the
input functional requirements, and state one story for each. Justify the
granularity you choose by the business process, not by the number of input
requirements: one input requirement may be realized by several stories, and one
story may realize several input requirements.

Everything that governs a story — the conditions under which the capability is
refused, the attributes and permitted value sets it reads or writes, the
multiplicities and lifetimes of the entities it relates, and its consequences
for other entities — belongs in the acceptance criteria of that story.

Where an input requirement states a rule that governs several stories (for
example a table of permitted status changes, or the permitted set of payment
methods), place it in the acceptance criteria of each story it governs, phrased
for that story.

### Acceptance criteria

Each user story shall be followed by at least three acceptance criteria, with
no upper limit. Each acceptance criterion shall be written in one of two
forms, and the form used shall be recorded in the machine-readable listing:

- **Given-When-Then** — `Given <precondition>, When <trigger>, Then <expected
  observable outcome>.` Use this form for a criterion that describes what
  happens when something occurs.
- **Condition** — a single declarative constraint that holds independently of
  any trigger. Use this form for a criterion that states a permitted value set,
  a data type, a multiplicity, a lifetime, or a permitted status change.

One criterion states one rule. A rule whose statement needs several clauses
stays in one criterion; two rules that govern different triggers stay in two.

Each acceptance criterion shall be independently verifiable: a reader shall be
able to determine, by observing the system, whether it holds. Criteria such as
"the interface is user-friendly" are not acceptable.

### Non-functional requirements — declarative form

Requirements in clause 3.2 (quality attributes) shall **not** be written as
user stories. They shall be written as single declarative statements using
"shall", each with a quantified, measurable threshold where the property admits
one. A non-functional requirement carries no acceptance criteria.

### Identifiers

- Functional requirements: `US-NN`, numbered from `US-01` upward, no gaps.
- Non-functional requirements: `NFR-NN`, numbered from `NFR-01` upward, no gaps.
- Acceptance criteria: `<requirement-id>-ACNN`, e.g. `US-01-AC01`, numbered from
  `01` within each requirement, no gaps.

Identifiers shall match the regular expressions `^US-\d{2}$`, `^NFR-\d{2}$` and
`^US-\d{2}-AC\d{2}$` respectively, and shall be identical across `srs.md`,
`requirements.json` and `VMX.csv`.

### Order of requirements

Functional requirements shall appear in clause 3.1 in the order in which the
capabilities they specify are first reached in the input functional
requirements, and shall be numbered `US-01` upward in that order.

Non-functional requirements shall be grouped by the quality attribute that
governs them and shall appear in clause 3.2 in the order of its subclauses:
first every performance requirement (3.2.1), then every security requirement
(3.2.2), then every availability requirement (3.2.3). Within one subclause they
shall keep the relative order of the input non-functional requirements they
originate from. They shall be numbered `NFR-01` upward across the whole of
clause 3.2 in that order, so that the numbering follows the subclauses and
**not** the order of the input non-functional requirements.

Every requirement originating from an input FR shall be specified in clause 3.1
with a `US-` identifier. Every requirement originating from an input NFR shall
be specified in clause 3.2 with an `NFR-` identifier.

---

## Output Standard

`srs.md` shall contain the following clauses, in this order, with these
headings:

1. Introduction
   1. Purpose
   2. Scope
   3. Definitions and acronyms
2. Overall description
   1. Product perspective
   2. Product functions
   3. User characteristics
   4. Assumptions and dependencies
3. Requirements
   1. Functional requirements
   2. Quality attributes
      1. Performance
      2. Security
      3. Availability
4. Verification
5. Supporting information

Clause 3.1 holds every functional requirement. Clause 3.2 holds every
non-functional requirement, each placed in the one subclause that names its
quality attribute.

---

## Diagrams

The SRS must include two UML diagrams, both expressed in PlantUML source.
Each diagram is delivered as its own file (see "Output Files" below), not
inside the SRS document.

### Diagram 1 — Structural Model

Open with `@startuml structural` and close with `@enduml`. It must show:

- Domain classes with meaningful names
- Attributes with explicit data types
- `enum` declarations where they are appropriate, each declaring one literal per
  permitted value, with the attributes they govern typed by the enum rather than
  by a general-purpose type such as `String`. Decide for yourself which
  attributes these are.
- Relationships between classes with multiplicities on both ends. Choose for
  yourself, for each relationship, which kind of relationship (association,
  aggregation, composition, generalization) correctly models it.

### Diagram 2 — Behavioral Model

Open with `@startuml behavioral` and close with `@enduml`. It must show:

- Exactly one initial node and at least one final node
- Decision nodes, each with an explicit guard condition on every outgoing flow
- Actions with meaningful names, each connected to the control flow
- At least one fork with a matching join, placed where the control flow
  warrants it. Determine for yourself from the input requirements where that is.
- At least one loop, placed where the control flow warrants it. Determine for
  yourself from the input requirements where that is.
- An object node after each action that leaves an entity in a new status,
  written as the entity name followed by the status in square brackets

The diagram shall be partitioned into swimlanes, declared with the `|...|`
syntax. Every action shall lie within the swimlane of the role that performs it.

---

## Output Files

Write exactly the following five files, using exactly these file names, in the
current working directory. Do not create any other files, and do not rename,
add prefixes or suffixes, or place them in subfolders.

| File name | Content |
| --- | --- |
| `srs.md` | The SRS document in Markdown, following the clause structure above. It is prose only: it shall not contain the traceability matrix, the PlantUML source or the JSON listing. Where the SRS refers to the diagrams, the traceability matrix or the requirements listing, refer to them by file name (`structural.puml`, `behavioral.puml`, `VMX.csv`, `requirements.json`). |
| `structural.puml` | The complete Diagram 1 source, from `@startuml structural` to `@enduml`. Raw PlantUML only: no Markdown fences, no prose. |
| `behavioral.puml` | The complete Diagram 2 source, from `@startuml behavioral` to `@enduml`. Raw PlantUML only: no Markdown fences, no comments. |
| `requirements.json` | A machine-readable listing of every requirement you specified in `srs.md`. Raw JSON only: no Markdown fences, no comments. |
| `VMX.csv` | The traceability matrix (see "Traceability"). Raw CSV only: no Markdown fences, no comments, no prose. |

### Format of `requirements.json`

The file content is a single JSON object, encoded in UTF-8 without a
byte-order mark. The object has exactly the following members:

| Field | JSON type | Description |
| --- | --- | --- |
| `version` | string | The version of this listing. Use `1.1`. |
| `updated` | string | The date of the input domain requirements, as `YYYY-MM-DD`. Use `2026-10-21`. |
| `requirements` | array | Every requirement specified in `srs.md`, as requirement objects (see below). |

Each requirement object has exactly the following members. Every member is
mandatory and shall be present on every object. Where no value applies, use an
empty string or an empty array — never `null`, and never omit the member. Do
not add any member that is not listed here.

| Field | JSON type | Description |
| --- | --- | --- |
| `id` | string | The requirement identifier as used in `srs.md`. Matches `^US-\d{2}$` or `^NFR-\d{2}$`. Unique across the array. |
| `type` | string | Exactly one of: `functional` (clause 3.1), `performance` (3.2.1), `security` (3.2.2), `availability` (3.2.3). The value shall name the clause of `srs.md` in which the requirement appears. Every requirement whose `id` matches `^US-` has type `functional`; no requirement whose `id` matches `^NFR-` has type `functional`. |
| `statement` | string | The full requirement statement exactly as it appears in `srs.md`, verbatim, on one line. For a functional requirement this is the complete "As a ..., I want ..., so that ..." sentence. |
| `acceptance_criteria` | array | An array of acceptance criterion objects (see below). At least three elements where `type` is `functional`, with no upper limit; the empty array for every other type. |

Each acceptance criterion object has exactly the following members, and no
others:

| Field | JSON type | Description |
| --- | --- | --- |
| `id` | string | Matches `^US-\d{2}-AC\d{2}$`. Its requirement-id prefix equals the `id` of the enclosing requirement. Unique across the whole file. |
| `format` | string | Exactly one of: `given_when_then`, `condition`. |
| `text` | string | The complete criterion as a single line, verbatim as it appears in `srs.md`. Where `format` is `given_when_then`, the text begins with `Given `, and contains `, When ` and `, Then `. |

This listing records no traceability: the link from a specified requirement
back to its domain requirement identifier is held only in `VMX.csv`.

Further constraints on the listing:

- The `requirements` array shall contain exactly the requirements specified in
  `srs.md` — no more, no fewer — and in the same order in which they appear in
  `srs.md`.
- Identifiers, statements and criterion texts in the listing shall be byte-identical
  to their occurrences in `srs.md`, apart from Markdown emphasis markers.
- No member shall contain a newline character.
- The file shall parse as valid JSON on the first attempt. Do not emit trailing
  commas, comments, or any text before or after the top-level object.

---

## Traceability

Write the traceability matrix to `VMX.csv`. It maps each specified requirement
to the domain requirement(s) it originates from and to the corresponding
diagram element(s). `VMX.csv` is the only file that records the link between a
specified requirement and the domain requirement it originates from.

### Format of `VMX.csv`

- The first row is the header, exactly: `SRS-Req-ID,Domain-Req-ID,Structural-Elements,Behavorial-Elements`
- Each following row describes exactly one requirement specified in `srs.md`.
  There shall be exactly one row per requirement, and the `SRS-Req-ID` values
  shall match the identifiers in `srs.md` and `requirements.json` exactly, in
  the same order.
- Separate the columns with commas. Enclose a cell in double quotes when it
  contains a comma or a double quote.
- When a cell lists several values, separate the values with semicolons.
- If no value applies to a cell, leave it empty.

| Column | Description |
| --- | --- |
| `SRS-Req-ID` | The identifier of the requirement as used in `srs.md` |
| `Domain-Req-ID` | The identifier(s) of the domain requirement(s) from which the requirement originates, copied character for character from the input domain requirements. Each identifier shall match `^REQ-F-\d{2}$` or `^REQ-N-\d{2}$`. Do not abbreviate, renumber or reformat them. One domain requirement may appear in several rows, and one row may list several domain requirements. Leave the cell empty if the requirement is derived rather than traced to a domain requirement. |
| `Structural-Elements` | The names of the classes, enums or attributes (written `Class.attribute`) declared in `structural.puml` that realize the requirement. Write each name exactly as it is declared in `structural.puml`. Do not list relationships here. |
| `Behavorial-Elements` | The names of the actions declared in `behavioral.puml` that realize the requirement. Write each name exactly as it is declared in `behavioral.puml`. Do not list decisions, object nodes, or control nodes (initial, final, fork, join, merge) here. |