# M1 Prompt — SRS Generation with User Stories and Traceability

You are a requirements engineer. Your task is to produce a complete Software
Requirements Specification (SRS) for the system described below, conforming to
IEEE/ISO/IEC 29148-2018, in which every functional requirement is expressed as
a user story with acceptance criteria.

---

## Input: Domain Requirements

### Order Management System — Domain Requirements

#### 1. Introduction & Business Roles

This document outlines the requirements for a standard order management
platform. The system interactions revolve around four primary roles:

- **Customer** — the end-user browsing, purchasing, and managing their items.
- **Payment Gateway** — an external third-party service processing financial
  transactions.
- **Warehouse** — the logistics personnel responsible for physical fulfillment.
- **Sales** — internal staff handling administration, oversight, and customer
  support.

#### 2. Functional Requirements (FR)

{{FR_INPUT}}

#### 3. Non-Functional Requirements (NFR)

{{NFR_INPUT}}

---

## Requirement Style

### Functional requirements — user story form

Every requirement in clause 3.1 shall be stated as a user story in exactly
this template, on a single line:

> As a `<role>`, I want `<capability>`, so that `<benefit>`.

Rules:

- `<role>` shall be one of the roles named in the input domain requirements
  (Customer, Payment Gateway, Warehouse, Sales), or `System Administrator`
  where no business role applies. Do not invent other roles.
- `<capability>` shall describe a single capability. If a requirement would
  need "and" to join two independent capabilities, split it into two
  requirements.
- `<benefit>` shall state why the role wants it, not restate the capability.
- The story line shall not contain the word "shall".

Each user story shall be followed by at least three and at most seven
acceptance criteria. Each acceptance criterion shall be written in one of two
forms, and the form used shall be recorded in the machine-readable listing:

- **Given-When-Then** — `Given <precondition>, When <trigger>, Then <expected
  observable outcome>.`
- **Condition** — a single declarative constraint that is objectively
  decidable, e.g. "The password field accepts a minimum of 8 characters."

Each acceptance criterion shall be independently verifiable: a reader shall be
able to determine, by observing the system, whether it holds. Criteria such as
"the interface is user-friendly" are not acceptable.

### Non-functional requirements — declarative form

Requirements in clauses 3.2 through 3.6 (performance, interface, security,
quality, design constraints) shall **not** be written as user stories. They
shall be written as single declarative statements using "shall", each with a
quantified, measurable threshold where the property admits one.

### Identifiers

- Functional requirements: `US-NN`, numbered from `US-01` upward, no gaps.
- Non-functional requirements: `NFR-NN`, numbered from `NFR-01` upward, no gaps.
- Acceptance criteria: `<requirement-id>-ACNN`, e.g. `US-01-AC01`, numbered from
  `01` within each requirement, no gaps.

Identifiers shall match the regular expressions `^US-\d{2}$`, `^NFR-\d{2}$` and
`^(US|NFR)-\d{2}-AC\d{2}$` respectively, and shall be identical across
`srs.md`, `requirements.json` and `VMX.csv`.

---

## Output Standard

Produce an SRS conforming to IEEE/ISO/IEC 29148-2018. The document must contain
the following clauses:

1. Introduction
   1. Purpose
   2. Scope
   3. Definitions, acronyms and abbreviations
   4. References
2. Overall description
   1. Product perspective
   2. Product functions
   3. User characteristics
   4. Constraints
   5. Assumptions and dependencies
3. Specific requirements
   1. Functional requirements (user stories with acceptance criteria)
   2. Performance requirements
   3. Interface requirements
   4. Security requirements
   5. Software quality attributes
   6. Design constraints
4. Verification
5. Supporting information

---

## Diagrams

The SRS must include two UML diagrams, both expressed in PlantUML source.
Each diagram is delivered as its own file (see "Output Files" below), not
inside the SRS document.

### Diagram 1 — Structural Model

Open with `@startuml classdiagram` and close with `@enduml`. It must show:

- Domain classes with meaningful names
- Attributes with explicit data types
- Relationships between classes (association, aggregation, composition,
  generalization) with multiplicities on both ends

### Diagram 2 — Behavioral Model

Open with `@startuml activity` and close with `@enduml`. It must show:

- Exactly one initial node and at least one final node
- Decision nodes, each with an explicit guard condition on every outgoing flow
- Actions with meaningful names, each connected to the control flow

Swimlanes are not required. The diagram may be written without any swimlane
(`|...|`) declaration; if swimlanes are used they are optional and carry no
additional requirement.

---

## Output Files

Write exactly the following five files, using exactly these file names, in the
current working directory. Do not create any other files, and do not rename,
add prefixes or suffixes, or place them in subfolders.

| File name | Content |
| --- | --- |
| `srs.md` | The SRS document in Markdown, following the clause structure above. It is prose only: it shall not contain the traceability matrix, the PlantUML source or the JSON listing. Where the SRS refers to the diagrams, the traceability matrix or the requirements listing, refer to them by file name (`structural.puml`, `behavioral.puml`, `VMX.csv`, `requirements.json`). |
| `structural.puml` | The complete Diagram 1 source, from `@startuml classdiagram` to `@enduml`. Raw PlantUML only: no Markdown fences, no prose. |
| `behavioral.puml` | The complete Diagram 2 source, from `@startuml activity` to `@enduml`. Raw PlantUML only: no Markdown fences, no comments. |
| `requirements.json` | A machine-readable listing of every requirement you specified in `srs.md`. Raw JSON only: no Markdown fences, no comments. |
| `VMX.csv` | The traceability matrix (see "Traceability"). Raw CSV only: no Markdown fences, no comments, no prose. |

### Format of `requirements.json`

The file content is a single JSON array of requirement objects, encoded in
UTF-8 without a byte-order mark. The array is the top-level value: it is not
wrapped in an enclosing object.
 
Each requirement object has exactly the following members. Every member is
mandatory and shall be present on every object. Where no value applies, use an
empty string or an empty array — never `null`, and never omit the member.

| Field | JSON type | Description |
| --- | --- | --- |
| `id` | string | The requirement identifier as used in `srs.md`. Matches `^US-\d{2}$` or `^NFR-\d{2}$`. Unique across the array. |
| `type` | string | Exactly one of: `functional`, `performance`, `interface`, `security`, `quality`, `constraint`. Every requirement whose `id` matches `^US-` has type `functional`; no requirement whose `id` matches `^NFR-` has type `functional`. |
| `form` | string | Exactly one of: `user_story`, `declarative`. `user_story` if and only if `type` is `functional`. |
| `statement` | string | The full requirement statement exactly as it appears in `srs.md`, verbatim, on one line. For a user story this is the complete "As a ..., I want ..., so that ..." sentence. |
| `role` | string | For `form` = `user_story`: the `<role>` segment only, without the leading "As a". For `form` = `declarative`: the empty string. |
| `capability` | string | For `form` = `user_story`: the `<capability>` segment only, without the leading "I want". For `form` = `declarative`: the empty string. |
| `benefit` | string | For `form` = `user_story`: the `<benefit>` segment only, without the leading "so that" and without the trailing full stop. For `form` = `declarative`: the empty string. |
| `acceptance_criteria` | array | An array of acceptance criterion objects (see below). At least three and at most seven elements for `form` = `user_story`; may be empty for `form` = `declarative`. |
| `source_ids` | array of strings | The FR or NFR identifiers from the input domain requirements from which this requirement originates. Empty array if the requirement is derived rather than traced to an input. |
| `priority` | string | Exactly one of: `must`, `should`, `could`. |
| `verification_method` | string | Exactly one of: `test`, `analysis`, `inspection`, `demonstration`. |

Each acceptance criterion object has exactly the following members:

| Field | JSON type | Description |
| --- | --- | --- |
| `id` | string | Matches `^(US\|NFR)-\d{2}-AC\d{2}$`. Its requirement-id prefix equals the `id` of the enclosing requirement. Unique across the whole file. |
| `format` | string | Exactly one of: `given_when_then`, `condition`. |
| `text` | string | The complete criterion as a single line, verbatim as it appears in `srs.md`. |
| `given` | string | For `format` = `given_when_then`: the precondition only, without the leading "Given". Otherwise the empty string. |
| `when` | string | For `format` = `given_when_then`: the trigger only, without the leading "When". Otherwise the empty string. |
| `then` | string | For `format` = `given_when_then`: the expected outcome only, without the leading "Then". Otherwise the empty string. |

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
to its source input requirement and to the corresponding diagram element(s).

### Format of `VMX.csv`

- The first row is the header, exactly: `SRS-Req-ID,Source-Input-ID,Structural-Elements,Behavorial-Elements`
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
| `Source-Input-ID` | The FR or NFR identifier(s) given in the input domain requirements from which the requirement originates |
| `Structural-Elements` | The names of the classes, attributes (written `Class.attribute`) or relationships in `structural.puml` that realize the requirement |
| `Behavorial-Elements` | The names of the actions or decisions in `behavorial.puml` that realize the requirement |

The `Source-Input-ID` cell of each row shall list the same identifiers as the
`source_ids` member of the corresponding requirement object in
`requirements.json`.