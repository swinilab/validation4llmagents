# 1. Introduction

## 1.1 Purpose

This Software Requirements Specification (SRS) establishes the complete functional and non-functional requirements for the Order Management System (OMS). It provides a precise, contractual foundation for software engineers, testers, operations personnel, and system stakeholders, defining domain entities, operational lifecycles, business constraints, and verification procedures.

## 1.2 Scope

The Order Management System manages the end-to-end purchasing and fulfillment lifecycle. The system coordinates customer registration and order submission, order validation and fulfillment by internal order staff, invoicing and financial settlement by accounting personnel, and final order closure. External and internal system artifacts including domain models (`structural.puml`), behavioral workflows (`behavioral.puml`), machine-readable requirements listings (`requirements.json`), and bidirectional traceability matrices (`VMX.csv`) supplement this specification to ensure rigorous governance and full lifecycle traceability.

## 1.3 Definitions and acronyms

- **AC**: Acceptance Criterion
- **FR**: Functional Requirement
- **NFR**: Non-Functional Requirement
- **OMS**: Order Management System
- **SRS**: Software Requirements Specification
- **TLS**: Transport Layer Security
- **UML**: Unified Modeling Language
- **VMX**: Verification Matrix / Traceability Matrix

# 2. Overall description

## 2.1 Product perspective

The OMS operates as a centralized commercial engine supporting multi-user transactional operations. It interfaces with customer client interfaces and internal administrative consoles. The domain structure is formally specified in the external structural model (`structural.puml`), defining entity attributes, data types, enumerations, and multiplicities. The operational dynamics are captured in the external activity model (`behavioral.puml`), which models swimlanes, state transitions, parallel forks and joins, and iterative payment retry loops.

## 2.2 Product functions

The principal functional capabilities provided by the system include:
- Customer profile management and identification as an eligible ordering party.
- Product catalog referencing and item quantity configuration.
- Order submission with validation of customer identity, product existence, and payment method.
- Order processing workflows: order reception, filling, shipping, declining, and closure.
- Independent parallel progression of order shipment and invoice billing upon fulfillment.
- Invoicing issuance, payment submission against issued invoices, payment confirmation, and payment rejection with iterative retry capability.
- Synchronized order closure contingent upon both verified order shipment and invoice payment settlement.

## 2.3 User characteristics

The system serves three primary business roles:
- **Customer**: External end-users who browse products, submit orders, and submit payments against issued invoices.
- **OrderStaff**: Internal operational staff responsible for receiving submitted orders, validating and filling items, dispatching shipments, declining unfulfillable orders, and closing completed orders.
- **Accountant**: Internal financial specialists responsible for raising invoices for fulfilled or shipped orders, validating received payments, confirming settlements, and rejecting failed transactions.

## 2.4 Assumptions and dependencies

- Network communications between client applications and server endpoints support secure TLS 1.2 or higher protocols.
- Customers possess unique identification within the system prior to submitting orders.
- Products are created and maintained with valid names, descriptions, decimal prices, and image references prior to inclusion in order items.
- System clocks across server instances are synchronized to UTC to support immutable chronological audit logging.

# 3. Requirements

## 3.1 Functional requirements

This clause specifies every functional requirement as a user story conforming strictly to the template `As a <role>, I want <capability>, so that <benefit>.` Each user story is accompanied by independently verifiable acceptance criteria expressed in Given-When-Then or Condition formats. Complete traceability between these requirements and domain requirements is maintained in `VMX.csv`, and machine-readable specifications are cataloged in `requirements.json`.

### US-01: Order Submission

As a Customer, I want to submit an order naming my account, containing one or more order items referring to existing products, and carrying a payment method, so that my order is registered for fulfillment.

- **US-01-AC01**: Given a known customer, one or more order items each referring to an existing product, and a valid payment method, When the customer submits the order, Then the system shall register the order with the submission date as its order date and the status submitted.
- **US-01-AC02**: Given an order submission where the customer is not known to the system, When the customer attempts to submit the order, Then the system shall reject the order submission and register no order.
- **US-01-AC03**: Given an order submission containing no order items, When the customer attempts to submit the order, Then the system shall reject the order submission and register no order.
- **US-01-AC04**: Given an order submission where any order item refers to a product that does not exist, When the customer attempts to submit the order, Then the system shall reject the order submission and register no order.
- **US-01-AC05**: The system shall record for each registered order a total amount equal to the sum over its order items of quantity multiplied by unit price, represented as a decimal number.
- **US-01-AC06**: The system shall store a name, an address, and a phone number for each customer, and shall allow a customer to have at most one optional bank account.
- **US-01-AC07**: The system shall store a name, a description, a price represented as a decimal number, and an image for each product, and shall allow a product to be referred to by any number of order items, including none, while keeping the product in existence independently of the order items that refer to it.
- **US-01-AC08**: The system shall record each order item with a quantity, a unit price represented as a decimal number, and a reference to exactly one product, shall associate each order item with exactly one order, shall keep an order item in existence only as part of the order it belongs to without allowing it to be moved to another order, and shall remove the order items of an order when that order is removed.
- **US-01-AC09**: The system shall associate each order with exactly one customer, while a customer may have any number of orders.
- **US-01-AC10**: The system shall treat every attribute as mandatory, except the bank account of a customer, and shall reject a customer record or a product record in which a mandatory attribute is absent.
- **US-01-AC11**: The system shall restrict the payment method recorded on an order to bank, card, or cash.


### US-02: Order Reception

As a OrderStaff, I want to receive a submitted order by setting its status to pending, so that the order is formally acknowledged and queued for processing.

- **US-02-AC01**: Given an order whose status is submitted, When order staff receives the order, Then the system shall set the status of the order to pending.
- **US-02-AC02**: Given an order whose status is not submitted, When order staff attempts to receive the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-02-AC03**: The system shall not change the status of an order whose status is closed.
- **US-02-AC04**: The system shall change the status of an order from submitted only to pending.


### US-03: Order Fulfillment

As a OrderStaff, I want to mark a pending order as filled, so that fulfillment preparation is complete and the order can proceed to shipping and invoicing.

- **US-03-AC01**: Given an order whose status is pending, When order staff marks the order as filled, Then the system shall set the status of the order to filled.
- **US-03-AC02**: Given an order whose status is not pending, When order staff attempts to mark the order as filled, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-03-AC03**: The system shall change the status of an order from pending only to filled or to closed.
- **US-03-AC04**: The system shall not change the status of an order whose status is closed.


### US-04: Order Declination

As a OrderStaff, I want to decline a pending order by setting its status to closed, so that invalid or unfulfillable orders are terminated without further processing.

- **US-04-AC01**: Given an order whose status is pending, When order staff declines the order, Then the system shall set the status of the order to closed.
- **US-04-AC02**: Given an order whose status is not pending, When order staff attempts to decline the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-04-AC03**: Given an order that has been declined, When a request is made to raise an invoice for the order, Then the system shall reject the request.
- **US-04-AC04**: The system shall not change the status of an order whose status is closed.


### US-05: Order Shipping

As a OrderStaff, I want to set the status of a filled order to shipped, so that the items are dispatched to the customer.

- **US-05-AC01**: Given an order whose status is filled, When order staff sets the status of the order to shipped, Then the system shall set the status of the order to shipped.
- **US-05-AC02**: Given an order whose status is not filled, When order staff attempts to set the order to shipped, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-05-AC03**: The system shall leave the status of an invoice and of any payment against that invoice unchanged when an order is set to shipped.
- **US-05-AC04**: The system shall let invoicing and shipping proceed independently of each other once an order has been filled, so that setting the order to shipped does not require an invoice to have been raised.
- **US-05-AC05**: The system shall change the status of an order from filled only to shipped.


### US-06: Invoice Issuance

As a Accountant, I want to raise an invoice for a filled or shipped order that has no invoice, so that billing is established for customer settlement.

- **US-06-AC01**: Given an order whose status is filled or shipped and that has no invoice, When an accountant raises an invoice for the order, Then the system shall record an invoice associated with the order with a date, an amount represented as a decimal number, a payment method, and the status issued.
- **US-06-AC02**: Given an order that already has an invoice, When a request is made to raise a further invoice for the order, Then the system shall reject the request.
- **US-06-AC03**: Given an order whose status is submitted, pending, or closed, When a request is made to raise an invoice for the order, Then the system shall reject the request.
- **US-06-AC04**: The system shall allow at most one invoice per order, and shall associate each invoice with exactly one order.
- **US-06-AC05**: The system shall let invoicing and shipping proceed independently of each other once an order has been filled, so that raising an invoice does not require the order to have been shipped.
- **US-06-AC06**: The system shall restrict the status of an invoice to issued or paid, shall change the status of an invoice only from issued to paid, and shall restrict the payment method recorded on an invoice to bank, card, or cash.


### US-07: Payment Submission

As a Customer, I want to submit a payment against an issued invoice, so that my payment is recorded for validation and settlement.

- **US-07-AC01**: Given an invoice whose status is issued, When a customer submits a payment against the invoice with a date, an amount, and a payment method, Then the system shall record the payment against exactly that invoice with the status pending.
- **US-07-AC02**: Given an invoice whose status is paid, When a customer attempts to submit a payment against the invoice, Then the system shall reject the payment.
- **US-07-AC03**: Given an invoice whose earlier payment has the status failed, When a customer submits a further payment against the invoice, Then the system shall record the further payment as a separate payment with the status pending, and shall keep the failed payment at the status failed.
- **US-07-AC04**: The system shall allow any number of payments against one invoice, and shall record each payment against exactly one invoice rather than directly against an order.
- **US-07-AC05**: The system shall represent payment amount as a decimal number, and shall restrict the payment method recorded on a payment to bank, card, or cash.


### US-08: Payment Confirmation

As a Accountant, I want to confirm a pending payment, so that the payment is completed and the corresponding invoice is marked as paid.

- **US-08-AC01**: Given a payment whose status is pending against an invoice whose status is issued, When an accountant confirms the payment, Then the system shall set the status of the payment to completed and the status of that invoice to paid.
- **US-08-AC02**: Given a payment whose status is not pending, When an accountant attempts to confirm the payment, Then the system shall reject the attempt and leave the status of the payment unchanged.
- **US-08-AC03**: The system shall leave the status of the order billed by an invoice unchanged when a payment against that invoice is confirmed.
- **US-08-AC04**: The system shall change the status of a payment only from pending to completed or to failed, and shall change the status of an invoice only from issued to paid.


### US-09: Payment Rejection

As a Accountant, I want to reject a pending payment, so that invalid payment attempts are marked as failed while retaining the invoice for further payment.

- **US-09-AC01**: Given a payment whose status is pending, When an accountant rejects the payment, Then the system shall set the status of the payment to failed, and shall leave the status of its invoice and of its order unchanged.
- **US-09-AC02**: Given a payment whose status is not pending, When an accountant attempts to reject the payment, Then the system shall reject the attempt and leave the status of the payment unchanged.
- **US-09-AC03**: Given an invoice whose payment has been rejected with status failed, When a subsequent payment is submitted against the invoice, Then the system shall keep the failed payment at status failed and record the subsequent payment separately.
- **US-09-AC04**: The system shall change the status of a payment only from pending to completed or to failed.


### US-10: Order Closure

As a OrderStaff, I want to close an order whose status is shipped and whose invoice has the status paid, so that fully fulfilled and settled orders are concluded.

- **US-10-AC01**: Given an order whose status is shipped and whose invoice has the status paid, When order staff closes the order, Then the system shall set the status of the order to closed.
- **US-10-AC02**: Given an order whose status is shipped and whose invoice does not have the status paid, When order staff attempts to close the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-10-AC03**: Given an order whose invoice has the status paid and whose status is not shipped, When order staff attempts to close the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-10-AC04**: The system shall close a filled order only after both the shipping of the order and the settlement of its invoice have completed, whichever of the two finishes last.
- **US-10-AC05**: The system shall not change the status of an order whose status is closed.
- **US-10-AC06**: The system shall change the status of an order only from submitted to pending, from pending to filled or to closed, from filled to shipped, and from shipped to closed.


## 3.2 Quality attributes

This clause specifies the non-functional quality attributes of the system. Requirements are categorized by quality attribute and stated as declarative constraints using 'shall', each establishing a measurable and verifiable threshold.

### 3.2.1 Performance

- **NFR-01**: When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions.
- **NFR-02**: Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time of NFR-01.


### 3.2.2 Security

- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04**: The system shall allow only users holding the accountant role to confirm or reject a payment, and shall reject the same request from any other user.
- **NFR-05**: The system shall protect customer personal data and bank account numbers by encrypting them in transit with TLS 1.2 or higher and at rest.
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least 12 months.


### 3.2.3 Availability

- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08**: When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure.


# 4. Verification

Verification of system requirements is conducted using four standardized methods: Testing (T), Inspection (I), Demonstration (D), and Analysis (A).

1. **Functional User Stories (US-01 through US-10)**: Verified via automated testing (unit, integration, and end-to-end test suites) evaluating the preconditions, triggers, and expected outcomes defined in each Given-When-Then and Condition acceptance criterion. State transitions conform strictly to the lifecycle defined in `behavioral.puml`.
2. **Performance Requirements (NFR-01, NFR-02)**: Verified via automated performance and load testing measuring latency percentiles (95th percentile <= 2 seconds for up to 50 items) and sustained concurrency thresholds (200 concurrent users at 20 submissions per second) under simulated production workloads.
3. **Security Requirements (NFR-03, NFR-04, NFR-05, NFR-06)**: Verified through automated penetration tests, role-based access control test matrices (enforcing 100% rejection of unauthenticated access and non-accountant payment approvals), static security analysis, cryptographic inspection of network packets and persistent storage (TLS 1.2+ and rest encryption), and audit log inspection confirming 12-month timestamped retention.
4. **Availability Requirements (NFR-07, NFR-08)**: Verified through continuous uptime monitoring calculations over calendar months (99.5% threshold) and disaster recovery failover simulations confirming resumption of request processing within 15 minutes with zero transactional data loss.

Complete requirement-to-test mapping and verification traceability is documented in `VMX.csv`.

# 5. Supporting information

The following deliverables and external specifications constitute integral elements of the system baseline:
- `structural.puml`: Raw PlantUML source specification defining the structural domain model, entity classes, attributes, explicit data types, enums, multiplicities, and compositions.
- `behavioral.puml`: Raw PlantUML source specification defining the activity model, role swimlanes, control flow, decision guards, parallel forks and joins, payment retry loops, and entity status object nodes.
- `requirements.json`: Machine-readable UTF-8 JSON listing cataloging every requirement identifier, type, verbatim statement, and acceptance criterion.
- `VMX.csv`: Comprehensive traceability matrix mapping every specified requirement to originating domain requirements, structural elements, and behavioral actions.

### Document History

| Version | Date | Description | Author |
| --- | --- | --- | --- |
| 1.0 | 2026-10-21 | Initial domain requirements compilation | Systems Engineering |
| 1.1 | 2026-10-21 | Complete SRS baseline with user stories, acceptance criteria, and traceability | Requirements Engineer |
