# Software Requirements Specification (SRS)
## Order Management System

---

## 1. Introduction

### 1.1 Purpose
This Software Requirements Specification (SRS) defines the functional, structural, behavioral, and quality requirements for the Order Management System (OMS). It serves as the authoritative technical and contract baseline for system engineers, software architects, developers, and quality assurance personnel responsible for constructing, validating, and maintaining the platform.

### 1.2 Scope
The Order Management System provides core order management, fulfillment, invoicing, and payment reconciliation capabilities. The system supports three primary business actors: Customers, OrderStaff, and Accountants. The scope includes customer profile management, product browsing and item selection, order submission and lifecycle state transitions, independent fulfillment and invoicing workflows, payment capture and accountant verification, and final order closure. Excluded from this release are external payment gateway processing protocols, complex warehouse inventory routing, and external enterprise resource planning (ERP) ledger synchronizations.

### 1.3 Definitions and acronyms
- **OMS**: Order Management System.
- **SRS**: Software Requirements Specification.
- **Customer**: The end-user browsing products, placing purchase orders, and managing their payment submissions.
- **OrderStaff**: Internal enterprise personnel responsible for receiving, evaluating, preparing, and shipping customer orders.
- **Accountant**: Internal enterprise finance personnel responsible for issuing billing invoices and confirming or rejecting incoming payment submissions.
- **Order**: A formal commercial request submitted by a known customer to purchase one or more items referring to existing products.
- **OrderItem**: A distinct line item belonging exclusively to an order, specifying a product reference, quantity, and unit price.
- **Invoice**: A billing record generated for a filled or shipped order, specifying the amount due and accepted payment methods.
- **Payment**: A monetary transaction record submitted by a customer against an issued invoice.
- **TLS**: Transport Layer Security protocol.

---

## 2. Overall description

### 2.1 Product perspective
The Order Management System functions as a central transactional platform governing the lifecycle of commercial purchase requests. The structural architecture of domain entities, relationships, attributes, and permitted enumerations is specified in the domain model file `structural.puml`. The end-to-end control flow, concurrency forks and joins, and status transitions across actor swimlanes are specified in the behavioral model file `behavioral.puml`. Requirements trace back to source domain requirements and model elements through the traceability matrix file `VMX.csv`, while the machine-readable requirement specifications are maintained in `requirements.json`.

### 2.2 Product functions
The primary functions provided by the platform encompass:
- Customer and product data management with mandatory attribute integrity validation.
- Validated order submission ensuring known customer identities, non-empty order items, and referenced product existence.
- Order fulfillment lifecycle management, allowing OrderStaff to receive submitted orders, mark valid orders as filled, or decline unfulfillable orders.
- Concurrent, decoupled processing of order dispatch (shipping) and invoice generation once an order reaches the filled state.
- Payment processing, allowing customers to submit payments against issued invoices and resubmit alternative payments upon failure.
- Accountant verification, enabling formal confirmation (marking invoices paid) or rejection of pending payments.
- Order termination, ensuring an order is formally closed only after both physical shipment and invoice settlement have completed.

### 2.3 User characteristics
The system serves three designated human user roles:
- **Customer**: End-users who may have varying degrees of technical literacy. They access the platform to browse catalog offerings, configure order items, submit purchase orders, and execute payments against outstanding invoices.
- **OrderStaff**: Operational internal staff who possess domain knowledge of order validation, warehouse fulfillment, packaging, and logistical shipping procedures.
- **Accountant**: Financial specialists responsible for accounting compliance, invoice generation accuracy, and bank/card/cash payment receipt verification.

### 2.4 Assumptions and dependencies
- Customers and catalog products are pre-registered or established in the system before orders referencing them can be accepted.
- All monetary transactions and line-item arithmetic operate using high-precision decimal representation to prevent rounding errors.
- Network communication channels between client applications and server APIs provide TLS 1.2 or higher encryption.
- System persistence infrastructure supports ACID transactions to guarantee that order items remain strictly bound to their parent orders and cannot be orphaned.

---

## 3. Requirements

### 3.1 Functional requirements

#### US-01
As a Customer, I want to submit an order containing items for existing products with a selected payment method, so that the system can register my purchase request and initiate order processing.

- **US-01-AC01**: Given a customer is known to the system, When the customer submits an order containing one or more order items each referencing an existing product and carrying a valid payment method, Then the system registers the order with the submission date as its order date and the status submitted.
- **US-01-AC02**: Given an order submission, When the customer named in the submission is not known to the system, Then the system rejects the submission and registers no order.
- **US-01-AC03**: Given an order submission naming a known customer, When the submission contains no order item, Then the system rejects the submission and registers no order.
- **US-01-AC04**: Given an order submission naming a known customer and containing order items, When any order item refers to a product that does not exist, Then the system rejects the submission and registers no order.
- **US-01-AC05**: The system shall record for each registered order a total amount equal to the sum over its order items of quantity multiplied by unit price, represented as a decimal number.
- **US-01-AC06**: Each order item shall record a quantity, a unit price as a decimal number, and a reference to exactly one product, shall exist only as part of the exactly one order it is associated with, shall not be moved to another order, and shall be removed when that order is removed.
- **US-01-AC07**: Each order shall be associated with exactly one customer, while a customer may have any number of orders.
- **US-01-AC08**: The payment method recorded on an order shall be restricted to bank, card, or cash, and the initial status of an order shall be submitted from the permitted set of submitted, pending, filled, shipped, or closed.
- **US-01-AC09**: The system shall store a name, an address, and a phone number for each customer, and shall allow a customer to have at most one bank account, which is optional, rejecting any customer record missing a mandatory attribute.
- **US-01-AC10**: The system shall store a name, a description, a price as a decimal number, and an image for each product, keeping each product in existence independently of any order items referring to it, and rejecting any product record missing a mandatory attribute.

#### US-02
As an OrderStaff, I want to receive a submitted order, so that the order can transition to pending status for fulfillment review.

- **US-02-AC01**: Given an order with status submitted, When order staff receives the order, Then the system sets the status of the order to pending.
- **US-02-AC02**: Given an order whose status is not submitted, When order staff attempts to receive the order, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-02-AC03**: The system shall change the status of an order to pending only from submitted, restricting order status to the permitted set of submitted, pending, filled, shipped, or closed.

#### US-03
As an OrderStaff, I want to mark a pending order as filled, so that the items are confirmed as prepared and ready for shipping and invoicing.

- **US-03-AC01**: Given an order with status pending, When order staff marks the order as filled, Then the system sets the status of the order to filled.
- **US-03-AC02**: Given an order whose status is not pending, When order staff attempts to mark the order as filled, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-03-AC03**: The system shall change the status of an order to filled only from pending, restricting order status to the permitted set of submitted, pending, filled, shipped, or closed.

#### US-04
As an OrderStaff, I want to decline a pending order, so that an unfulfillable order is closed and prevented from further processing or invoicing.

- **US-04-AC01**: Given an order with status pending, When order staff declines the order, Then the system sets the status of the order to closed.
- **US-04-AC02**: Given an order whose status is not pending, When order staff attempts to decline the order, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-04-AC03**: The system shall reject any request to raise an invoice for an order that has been declined.
- **US-04-AC04**: The system shall not change the status of an order whose status is closed, restricting order status to the permitted set of submitted, pending, filled, shipped, or closed.

#### US-05
As an OrderStaff, I want to set a filled order to shipped, so that the dispatch of goods is recorded independently of invoice generation.

- **US-05-AC01**: Given an order with status filled, When order staff sets the status of the order to shipped, Then the system sets the order status to shipped.
- **US-05-AC02**: Given an order whose status is not filled, When order staff attempts to set the order to shipped, Then the system rejects the attempt and leaves the order status unchanged.
- **US-05-AC03**: When an order is set to shipped, the system shall leave the status of any associated invoice and of any payment against that invoice unchanged.
- **US-05-AC04**: The system shall allow setting the order to shipped independently of whether an invoice has been raised, and shall change the order status to shipped only from filled.

#### US-06
As an Accountant, I want to raise an invoice for a filled or shipped order, so that the customer is billed for payment settlement.

- **US-06-AC01**: Given an order whose status is filled or shipped and that has no invoice, When an accountant raises an invoice for the order, Then the system records an invoice associated with the order carrying the date, the amount as a decimal number, the payment method, and the status issued.
- **US-06-AC02**: Given an order that already has an invoice, When an accountant attempts to raise a further invoice for that order, Then the system rejects the request.
- **US-06-AC03**: Given an order whose status is submitted, pending, or closed, When an accountant attempts to raise an invoice for that order, Then the system rejects the request.
- **US-06-AC04**: The system shall allow at most one invoice per order, shall associate each invoice with exactly one order, and shall restrict the payment method to bank, card, or cash.
- **US-06-AC05**: The system shall allow raising an invoice once an order has been filled independently of whether the order has been shipped, restricting the initial invoice status to issued.

#### US-07
As a Customer, I want to submit a payment against an issued invoice, so that I can settle my outstanding balance.

- **US-07-AC01**: Given an invoice whose status is issued, When a customer submits a payment against the invoice, Then the system records the payment against that invoice with the given date, amount as a decimal number, payment method, and the status pending.
- **US-07-AC02**: Given an invoice whose status is paid, When a customer attempts to submit a payment against the invoice, Then the system rejects the payment.
- **US-07-AC03**: Given an invoice whose earlier payment has the status failed, When a customer submits a further payment against the invoice, Then the system records it as a separate payment with the status pending and keeps the earlier payment at the status failed.
- **US-07-AC04**: The system shall allow any number of payments against one invoice, shall record each payment against exactly one invoice rather than directly against an order, and shall restrict the payment method to bank, card, or cash.

#### US-08
As an Accountant, I want to confirm a pending payment, so that valid funds are accepted and the invoice is marked as paid.

- **US-08-AC01**: Given a payment with status pending recorded against an invoice with status issued, When an accountant confirms the payment, Then the system sets the status of the payment to completed and the status of the invoice to paid.
- **US-08-AC02**: Given a payment whose status is not pending, When an accountant attempts to confirm the payment, Then the system rejects the attempt and leaves the status of the payment unchanged.
- **US-08-AC03**: When a payment against an invoice is confirmed, the system shall leave the status of the order billed by that invoice unchanged.
- **US-08-AC04**: The system shall change the status of an invoice to paid only from issued, and the status of a payment to completed only from pending.

#### US-09
As an Accountant, I want to reject a pending payment, so that invalid funds are declined and the customer can provide an alternative payment.

- **US-09-AC01**: Given a payment with status pending, When an accountant rejects the payment, Then the system sets the status of the payment to failed and leaves the status of its invoice and order unchanged.
- **US-09-AC02**: Given a payment whose status is not pending, When an accountant attempts to reject the payment, Then the system rejects the attempt and leaves the status of the payment unchanged.
- **US-09-AC03**: The system shall change the status of a payment to failed only from pending, restricting payment status to the permitted set of pending, completed, or failed.

#### US-10
As an OrderStaff, I want to close an order that is both shipped and paid, so that the fulfilled and settled order completes its lifecycle.

- **US-10-AC01**: Given an order with status shipped whose invoice has the status paid, When order staff closes the order, Then the system sets the status of the order to closed.
- **US-10-AC02**: Given an order with status shipped whose invoice does not have the status paid, When order staff attempts to close the order, Then the system rejects the attempt and leaves the order status unchanged.
- **US-10-AC03**: Given an order whose invoice has the status paid but whose order status is not shipped, When order staff attempts to close the order, Then the system rejects the attempt and leaves the order status unchanged.
- **US-10-AC04**: The system shall close a filled order only after both the shipping of the order and the settlement of its invoice have completed, whichever of the two finishes last.
- **US-10-AC05**: The system shall not change the status of an order whose status is closed, and shall change the status of an order to closed only from pending or from shipped.

---

### 3.2 Quality attributes

#### 3.2.1 Performance
- **NFR-01**: When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions.
- **NFR-02**: Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time of REQ-N-01.

#### 3.2.2 Security
- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04**: The system shall allow only users holding the accountant role to confirm or reject a payment, and shall reject the same request from any other user.
- **NFR-05**: The system shall protect customer personal data and bank account numbers by encrypting them in transit with TLS 1.2 or higher and at rest.
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least 12 months.

#### 3.2.3 Availability
- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08**: When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure.

---

## 4. Verification

Verification of each specified requirement is established through standard verification methods: Inspection (I), Demonstration (D), Test (T), and Analysis (A).

1. **Functional Requirements Verification**:
   - Each acceptance criterion in Section 3.1 represents an independently verifiable condition.
   - Criteria written in Given-When-Then format (`given_when_then`) are verified through automated end-to-end and integration test suites that set up preconditions, execute API triggers, and assert observable outcomes.
   - Criteria written in declarative Condition format (`condition`) are verified through database schema validation, data type and constraint testing, invariant assertions, and unit tests.

2. **Quality Attributes Verification**:
   - **Performance (NFR-01, NFR-02)**: Verified via automated load and stress testing simulating 200 concurrent users generating at least 20 submissions per second with up to 50 items, measuring 95th percentile latency against the 2.0-second threshold.
   - **Security (NFR-03, NFR-04, NFR-05, NFR-06)**: Verified via penetration testing, role-based authorization test suites confirming accountant-only payment confirmation/rejection, SSL/TLS configuration analysis verifying TLS 1.2+ cipher suites and database encryption at rest, and audit trail retention inspection.
   - **Availability (NFR-07, NFR-08)**: Verified through continuous uptime monitoring and automated failover disaster recovery simulations measuring Mean Time to Recovery (MTTR) within 15 minutes and validating zero data loss of committed transactions.

---

## 5. Supporting information

The complete specification baseline includes the following accompanying technical artifacts located in the root repository directory:
- `structural.puml`: Raw PlantUML source for the domain structural model defining entity classes, attributes, explicit types, enums, multiplicities, and compositions.
- `behavioral.puml`: Raw PlantUML source for the domain behavioral activity diagram defining swimlanes, initial/final nodes, decision guards, actions, parallel fork/join execution, retry loops, and entity state transitions.
- `requirements.json`: Machine-readable UTF-8 JSON catalog specifying all functional requirements with their structured acceptance criteria and non-functional quality attributes.
- `VMX.csv`: Traceability matrix mapping every specified requirement identifier (`SRS-Req-ID`) to its input domain requirement (`Domain-Req-ID`), structural model realization (`Structural-Elements`), and behavioral action realization (`Behavorial-Elements`).
