# M1 Prompt — SRS Generation with Traceability

You are a requirements engineer. Your task is to produce a complete Software
Requirements Specification (SRS) for the system described below, conforming to
IEEE/ISO/IEC 29148-2018.

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
   1. Functional requirements
   2. Performance requirements
   3. Interface requirements
   4. Security requirements
   5. Software quality attributes
   6. Design constraints
4. Verification
5. Supporting information

Each requirement shall have a unique identifier and shall be verifiable. Use
"shall" for mandatory requirements. State each requirement as a single,
unambiguous, testable statement.

---

## Diagrams

The SRS must include two UML diagrams, both expressed in PlantUML source.
Each diagram is delivered as its own file (see "Output Files" below), not
inside the SRS document.

### Diagram 1 — Domain class diagram (structural view)

Open with `@startuml classdiagram` and close with `@enduml`. It must show:

- Domain classes with meaningful names
- Attributes with explicit data types
- Relationships between classes (association, aggregation, composition,
  generalization) with multiplicities on both ends

### Diagram 2 — Activity diagram (behavioral view)

Open with `@startuml activity` and close with `@enduml`. It must show:

- Swimlanes / partitions representing the roles involved
- Exactly one initial node and at least one final node
- Decision nodes, each with an explicit guard condition on every outgoing flow
- Every action placed inside exactly one swimlane

---

## Output Files

Write exactly the following five files, using exactly these file names, in the
current working directory. Do not create any other files, and do not rename,
add prefixes or suffixes, or place them in subfolders.

| File name | Content |
| --- | --- |
| `srs.md` | The SRS document in Markdown, following the clause structure above. It is prose only: it shall not contain the traceability matrix, the PlantUML source or the JSON listing. Where the SRS refers to the diagrams, the traceability matrix or the requirements listing, refer to them by file name (`class.puml`, `activity.puml`, `VMX.csv`, `requirements.json`). |
| `class.puml` | The complete Diagram 1 source, from `@startuml classdiagram` to `@enduml`. Raw PlantUML only: no Markdown fences, no prose. |
| `activity.puml` | The complete Diagram 2 source, from `@startuml activity` to `@enduml`. Raw PlantUML only: no Markdown fences, no prose. |
| `requirements.json` | A machine-readable listing of every requirement you specified in `srs.md`. Raw JSON only: no Markdown fences, no comments. |
| `VMX.csv` | The traceability matrix (see "Traceability"). Raw CSV only: no Markdown fences, no comments, no prose. |

### Format of `requirements.json`

The file content is a single JSON array of objects with these fields:

| Field | Description |
| --- | --- |
| `id` | The requirement identifier as used in `srs.md` |
| `statement` | The full requirement statement, verbatim |
| `type` | One of: `functional`, `performance`, `interface`, `security`, `quality`, `constraint` |
| `verification_method` | One of: `test`, `analysis`, `inspection`, `demonstration` |

The listing must contain exactly the requirements specified in `srs.md` — no
more, no fewer. Requirement identifiers in the listing must match `srs.md`
exactly.

Produce all five files in a single response. Do not repeat the contents of the
files in your reply.

---

## Traceability

Write the traceability matrix to `VMX.csv`. It maps each
specified requirement to its source input requirement and to the corresponding
diagram element(s).

### Format of `VMX.csv`

- The first row is the header, exactly: `SRS-Req-ID,Source-Input-ID,Class-Elements,Activity-Elements`
- Each following row describes exactly one requirement specified in `srs.md`.
  There shall be exactly one row per requirement, and the `SRS-Req-ID` values
  shall match the identifiers in `srs.md` and `requirements.json` exactly.
- Separate the columns with commas. Enclose a cell in double quotes when it
  contains a comma or a double quote.
- When a cell lists several values, separate the values with semicolons.
- If no value applies to a cell, leave it empty.

| Column | Description |
| --- | --- |
| `SRS-Req-ID` | The identifier of the requirement as used in `srs.md` |
| `Source-Input-ID` | The FR or NFR identifier(s) given in the input domain requirements from which the requirement originates |
| `Class-Elements` | The names of the classes, attributes (written `Class.attribute`) or relationships in `class.puml` that realize the requirement |
| `Activity-Elements` | The names of the actions, decisions or swimlanes in `activity.puml` that realize the requirement |