# M3 Prompt Pack B — SRS Generation with Traceability

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

##### Ordering & Payment

- **FR01** — A Customer can add multiple distinct items and specify their
  desired quantities into a digital shopping cart.
- **FR02** — Before finalizing the checkout, the system verifies current
  inventory levels; if any item is out of stock, the system alerts the Customer
  and halts the transaction.
- **FR03** — Upon successful checkout confirmation, the system generates a new
  order in a draft state and calculates the final total amount.
- **FR04** — The system securely transmits the order total and transaction
  details to the external Payment Gateway for processing.
- **FR05** — If the Payment Gateway confirms a successful transaction, the
  system transitions the order to a placed state.
- **FR06** — If the Payment Gateway reports a declined transaction, the system
  updates the order to a payment failed state and notifies the Customer.

##### Warehouse Processing

- **FR07** — The Warehouse team retrieves physical items for placed orders from
  the shelves and updates the order workflow to picked.
- **FR08** — After successfully gathering all required items, the Warehouse team
  boxes the items and transitions the order to a packed state.
- **FR09** — The Warehouse team hands the packages over to external carriers and
  updates the order to a shipped state.

##### Post-Sale Actions

- **FR10** — A Customer can manually cancel an order only if it is in the placed
  state and has not yet been marked as picked by the Warehouse.
- **FR11** — When a valid cancellation is triggered, the system voids the order
  and immediately instructs the Payment Gateway to execute a full reversal of
  funds.
- **FR12** — A Customer can initiate a formal return request for any shipped
  order within a 30-day window.
- **FR13** — Once the Warehouse team physically receives and approves the
  returned items, the system issues a refund to the Customer.

##### Administration

- **FR14** — Sales staff can search for any order using its unique identifier to
  view its current state and historical timeline.
- **FR15** — Sales staff can manually correct a Customer's delivery address on an
  order prior to it reaching the packed state.
- **FR16** — The system generates a daily summary report detailing total
  processed revenue and total volume of shipped orders for the Sales staff to
  review.

#### 3. Non-Functional Requirements (NFR)

##### Performance

- **NFR01** — The system shall complete order search, cart update, and checkout
  submission requests with a 95th-percentile response time of no more than 2
  seconds, measured at the API boundary under nominal load (<= 500 concurrent
  sessions).
- **NFR02** — The system shall sustain 2,000 concurrent user sessions while
  continuing to meet the NFR01 response-time threshold, with a request error
  rate of no more than 0.1%.

##### Security

- **NFR03** — The system shall encrypt all customer payment data using TLS 1.2 or
  higher in transit and AES-256 at rest, and shall store no unencrypted primary
  account numbers in any log, database, or backup.
- **NFR04** — The system shall record an immutable audit entry for every order
  state change, capturing timestamp (UTC, millisecond precision), the acting
  role, the prior state, and the resulting state, retained for at least 12
  months and modifiable by no role.

##### Reliability

- **NFR05** — The system shall achieve at least 99.9% availability measured
  monthly over a calendar month, excluding scheduled maintenance windows
  announced at least 48 hours in advance.
- **NFR06** — The system shall time out payment authorization requests to the
  Payment Gateway after 30 seconds, and shall ensure that a retried
  authorization for the same order results in no more than one charge against
  the customer's payment method.

##### Data Integrity

- **NFR07** — The system shall roll back any partially completed order
  transaction in full within 60 seconds of failure detection, leaving no order
  in an intermediate state and no discrepancy between financial records and
  inventory counts.

##### Scalability

- **NFR08** — The system shall support a 3x increase in peak daily order volume
  without modification to application code or data model, verified by load test
  against the projected peak.

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

The SRS must include two UML diagrams, both expressed in PlantUML source inside
fenced code blocks marked `plantuml`.

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

Both diagrams must be syntactically valid PlantUML that parses without error.

---

## Output Format

Output the SRS document first, in Markdown, following the clause structure
above.

After the SRS body, output a machine-readable listing of every requirement you
specified, in a fenced code block marked `json`, as an array of objects with
these fields:

| Field | Description |
| --- | --- |
| `id` | The requirement identifier as used in the SRS body |
| `statement` | The full requirement statement, verbatim |
| `type` | One of: `functional`, `performance`, `interface`, `security`, `quality`, `constraint` |
| `verification_method` | One of: `test`, `analysis`, `inspection`, `demonstration` |

The listing must contain exactly the requirements specified in the SRS body —
no more, no fewer. Requirement identifiers in the listing must match the SRS
body exactly.

Produce the complete document in a single response.

---

## Traceability

Include a traceability matrix in the SRS mapping each specified requirement to
its source input requirement and to the corresponding diagram element(s).
Present it as a table with these columns:

| SRS-Req-ID | Source-Input-ID | Class-Elements | Activity-Elements |
| --- | --- | --- | --- |

`Source-Input-ID` refers to the FR or NFR identifiers given in the input domain
requirements. `Class-Elements` and `Activity-Elements` refer to the names of
classes, attributes, relationships, actions, or swimlanes in the two diagrams.
