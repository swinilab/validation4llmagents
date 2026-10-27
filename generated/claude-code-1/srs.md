# Software Requirements Specification — Order Management System

Version 1.1, based on the domain requirements dated 2026-10-21.

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) specifies the requirements of the Order Management System. It states every functional requirement as a user story with verifiable acceptance criteria and every non-functional requirement as a measurable declarative statement. It is intended for the product owner, the development team, the test team and the stakeholders representing customers, order staff and accountants.

### 1.2 Scope

The Order Management System supports the life cycle of a customer order from submission to closure: keeping customer and product records, submitting orders, receiving, filling, declining and shipping orders, raising invoices, submitting, confirming and rejecting payments, and closing orders once they are both shipped and paid. Delivery logistics, payment gateway processing and the maintenance of the product catalogue by administrators are outside the scope of this SRS.

### 1.3 Definitions and acronyms

- **Customer**: the end user who browses products, submits orders and pays invoices.
- **OrderStaff**: internal staff who receive, validate, fill, decline, ship and close orders. In the acceptance criteria they are referred to as "order staff".
- **Accountant**: internal staff who raise invoices and confirm or reject payments.
- **Order**: a customer's request for one or more products, recorded with an order date, a total amount, a status and a payment method.
- **Order item**: one line of an order, recorded with a quantity, a unit price and a reference to exactly one product.
- **Invoice**: the bill raised for one order, recorded with a date, an amount, a status and a payment method.
- **Payment**: one attempt by a customer to settle an invoice, recorded with a date, an amount, a status and a payment method.
- **Known customer**: a customer whose record is stored by the system.
- **Declined order**: an order that order staff closed from the status pending without filling it.
- **Settlement of an invoice**: the confirmation of a payment that sets the invoice to the status paid.
- **Normal operating conditions**: operation with all servers in service and a load not exceeding the levels stated in NFR-02.
- **AC**: acceptance criterion.
- **FR / NFR**: functional / non-functional requirement.
- **SRS**: Software Requirements Specification.
- **TLS**: Transport Layer Security.
- **US**: user story.

## 2. Overall description

### 2.1 Product perspective

The Order Management System is a self-contained platform used by customers over the internet and by order staff and accountants internally. It holds the records of customers, products, orders, order items, invoices and payments; their attributes, permitted values and relationships are shown in the structural model `structural.puml`. The flow of an order through the system, including the parallel progress of shipping and invoicing and the repetition of failed payments, is shown in the behavioral model `behavioral.puml`, partitioned into one swimlane per role.

### 2.2 Product functions

- Keeping the customer's profile (US-01) and offering the product catalogue (US-02).
- Submitting and validating orders (US-03).
- Invoicing filled orders (US-04).
- Submitting payments against invoices (US-05).
- Receiving, filling, declining and shipping orders (US-06 to US-09).
- Confirming and rejecting payments (US-10, US-11).
- Closing orders that have been both shipped and paid (US-12).

Once an order has been filled, shipping (US-09) and invoicing with payment (US-04, US-05, US-10, US-11) proceed independently and in parallel; the order is closed (US-12) when the later of the two has completed.

### 2.3 User characteristics

- **Customer**: a member of the public with general web literacy and no training in the system. Customers act only on their own profile, orders and invoices.
- **OrderStaff**: trained employees who handle orders daily and are familiar with the order statuses and their permitted changes.
- **Accountant**: trained finance employees who are familiar with invoicing and with reconciling received payments.

### 2.4 Assumptions and dependencies

- Products are created and maintained by an administrative function outside the three roles of this SRS; the system nevertheless enforces the product attribute rules of US-02.
- Payments are made outside the system by bank transfer, card or cash; the system records them and the accountant confirms or rejects them according to whether the money has been received.
- No user story removes orders; the rules on the removal of an order (US-02, US-03) constrain any removal that an administrative function may perform.
- Users are authenticated by an identity service that assigns each user exactly one of the roles Customer, OrderStaff or Accountant.
- The hosting environment provides the redundancy needed to meet the availability and recovery requirements of clause 3.2.3.

## 3. Requirements

### 3.1 Functional requirements

Each functional requirement is a user story representing one unit of business intent in the order process. The granularity follows the business process: each step at which a role moves an order, invoice or payment forward, or obtains information it needs to do so, is one story. Rules that govern several stories (permitted values, permitted status changes, mandatory attributes, multiplicities and lifetimes) are restated, phrased for that story, in the acceptance criteria of each story they govern. Successful and refused outcomes of the same step belong to the same story, because they serve the same intent. The stories are listed in the order in which their capabilities are first reached in the domain requirements; the link from each story to its domain requirements is recorded in `VMX.csv`.

#### US-01 Maintain customer profile

**US-01:** As a Customer, I want to keep my name, address and phone number, and optionally one bank account, on record with the shop, so that my orders can be delivered to me and I can be contacted about them.

Acceptance criteria:

- **US-01-AC01** (Condition): Each customer record holds a name, an address and a phone number.
- **US-01-AC02** (Condition): A customer has at most one bank account, and the bank account is optional.
- **US-01-AC03** (Given-When-Then): Given a customer record in which the name, the address or the phone number is absent, When the record is saved, Then the system rejects the record and stores no customer.
- **US-01-AC04** (Given-When-Then): Given a customer record with a name, an address and a phone number but no bank account, When the record is saved, Then the system stores the customer without a bank account.

#### US-02 Browse products

**US-02:** As a Customer, I want to browse the products on offer with their name, description, price and image, so that I can decide which products to order.

Acceptance criteria:

- **US-02-AC01** (Condition): Each product holds a name, a description, a price and an image.
- **US-02-AC02** (Condition): The price of a product is a decimal number.
- **US-02-AC03** (Given-When-Then): Given a product record in which the name, the description, the price or the image is absent, When the record is saved, Then the system rejects the record and the product does not appear among the products on offer.
- **US-02-AC04** (Condition): A product may be referred to by any number of order items, including none.
- **US-02-AC05** (Given-When-Then): Given a product that is referred to by order items of an order, When that order is removed, Then the product continues to exist.

#### US-03 Submit order

**US-03:** As a Customer, I want to submit an order for one or more products with a payment method of my choice, so that I can purchase the products I need.

Acceptance criteria:

- **US-03-AC01** (Given-When-Then): Given a known customer, one or more order items each referring to an existing product, and a payment method, When the customer submits the order, Then the system registers an order with the submission date as its order date and the status submitted.
- **US-03-AC02** (Given-When-Then): Given an order submission that names a customer not known to the system, When the submission is made, Then the system rejects it and registers no order.
- **US-03-AC03** (Given-When-Then): Given an order submission that contains no order item, When the submission is made, Then the system rejects it and registers no order.
- **US-03-AC04** (Given-When-Then): Given an order submission in which an order item refers to a product that does not exist, When the submission is made, Then the system rejects it and registers no order.
- **US-03-AC05** (Condition): The total amount of a registered order equals the sum over its order items of quantity multiplied by unit price.
- **US-03-AC06** (Condition): Each order records an order date, a total amount, a status and a payment method, none of which may be absent.
- **US-03-AC07** (Condition): Each order item records a quantity, a unit price and a reference to exactly one product, none of which may be absent, and belongs to exactly one order.
- **US-03-AC08** (Condition): An order item exists only as part of the order it belongs to, cannot be moved to another order, and is removed when that order is removed.
- **US-03-AC09** (Condition): Each order belongs to exactly one customer, and a customer may have any number of orders.
- **US-03-AC10** (Condition): The unit price of an order item and the total amount of an order are decimal numbers.
- **US-03-AC11** (Condition): The status of an order takes only the values submitted, pending, filled, shipped or closed.
- **US-03-AC12** (Condition): The payment method of an order takes only the values bank, card or cash.
- **US-03-AC13** (Condition): A newly registered order has the status submitted, from which its status may change only to pending.

#### US-04 Raise invoice

**US-04:** As an Accountant, I want to raise an invoice for an order that has been filled, so that the customer is billed for the goods supplied.

Acceptance criteria:

- **US-04-AC01** (Given-When-Then): Given an order whose status is filled or shipped and that has no invoice, When the accountant raises an invoice for it with a date, an amount and a payment method, Then the system records the invoice for that order with the status issued.
- **US-04-AC02** (Given-When-Then): Given an order that already has an invoice, When the accountant requests a further invoice for it, Then the system rejects the request and the order keeps its single invoice.
- **US-04-AC03** (Given-When-Then): Given an order whose status is submitted, pending or closed, When the accountant requests an invoice for it, Then the system rejects the request and records no invoice.
- **US-04-AC04** (Given-When-Then): Given an order that has been declined, When the accountant requests an invoice for it, Then the system rejects the request and records no invoice.
- **US-04-AC05** (Given-When-Then): Given an order whose status is filled and that has not been shipped, When the accountant raises an invoice for it, Then the system records the invoice without requiring the order to have been shipped.
- **US-04-AC06** (Condition): Each invoice records a date, an amount, a status and a payment method, none of which may be absent.
- **US-04-AC07** (Condition): An order has at most one invoice, and each invoice is associated with exactly one order.
- **US-04-AC08** (Condition): The amount of an invoice is a decimal number.
- **US-04-AC09** (Condition): The status of an invoice takes only the values issued or paid.
- **US-04-AC10** (Condition): The payment method of an invoice takes only the values bank, card or cash.
- **US-04-AC11** (Condition): A newly raised invoice has the status issued, from which its status may change only to paid.

#### US-05 Submit payment

**US-05:** As a Customer, I want to submit a payment against an invoice I have received, so that I can settle the amount I owe for my order.

Acceptance criteria:

- **US-05-AC01** (Given-When-Then): Given an invoice whose status is issued, When the customer submits a payment against it with a date, an amount and a payment method, Then the system records the payment against that invoice with the status pending.
- **US-05-AC02** (Given-When-Then): Given an invoice whose status is paid, When the customer submits a payment against it, Then the system rejects the payment and records no payment.
- **US-05-AC03** (Given-When-Then): Given an invoice whose earlier payment has the status failed, When the customer submits a further payment against it, Then the system records the further payment as a separate payment with the status pending and the earlier payment keeps the status failed.
- **US-05-AC04** (Condition): Each payment records a date, an amount, a status and a payment method, none of which may be absent.
- **US-05-AC05** (Condition): An invoice may have any number of payments, and each payment is recorded against exactly one invoice and never directly against an order.
- **US-05-AC06** (Condition): The amount of a payment is a decimal number.
- **US-05-AC07** (Condition): The status of a payment takes only the values pending, completed or failed.
- **US-05-AC08** (Condition): The payment method of a payment takes only the values bank, card or cash.
- **US-05-AC09** (Condition): A newly submitted payment has the status pending, from which its status may change only to completed or to failed.

#### US-06 Receive order

**US-06:** As an OrderStaff, I want to receive a submitted order, so that I take responsibility for validating and fulfilling it.

Acceptance criteria:

- **US-06-AC01** (Given-When-Then): Given an order whose status is submitted, When order staff receive it, Then the system sets its status to pending.
- **US-06-AC02** (Given-When-Then): Given an order whose status is not submitted, When order staff attempt to receive it, Then the system rejects the attempt and the status of the order is unchanged.
- **US-06-AC03** (Given-When-Then): Given an order whose status is closed, When order staff attempt to receive it, Then the system rejects the attempt and the order keeps the status closed.
- **US-06-AC04** (Condition): Receiving an order changes its status only from submitted to pending.

#### US-07 Fill order

**US-07:** As an OrderStaff, I want to mark a pending order as filled, so that the order is ready to be shipped and invoiced.

Acceptance criteria:

- **US-07-AC01** (Given-When-Then): Given an order whose status is pending, When order staff mark it as filled, Then the system sets its status to filled.
- **US-07-AC02** (Given-When-Then): Given an order whose status is not pending, When order staff attempt to mark it as filled, Then the system rejects the attempt and the status of the order is unchanged.
- **US-07-AC03** (Given-When-Then): Given an order whose status is closed, When order staff attempt to mark it as filled, Then the system rejects the attempt and the order keeps the status closed.
- **US-07-AC04** (Condition): Marking an order as filled changes its status only from pending to filled.

#### US-08 Decline order

**US-08:** As an OrderStaff, I want to decline a pending order, so that an order the business will not fulfil is closed without being shipped or billed.

Acceptance criteria:

- **US-08-AC01** (Given-When-Then): Given an order whose status is pending, When order staff decline it, Then the system sets its status to closed.
- **US-08-AC02** (Given-When-Then): Given an order whose status is not pending, When order staff attempt to decline it, Then the system rejects the attempt and the status of the order is unchanged.
- **US-08-AC03** (Given-When-Then): Given an order whose status is closed, When order staff attempt to decline it, Then the system rejects the attempt and the order keeps the status closed.
- **US-08-AC04** (Given-When-Then): Given an order that has been declined, When an accountant requests an invoice for it, Then the system rejects the request and the order remains without an invoice.
- **US-08-AC05** (Condition): Declining an order changes its status only from pending to closed.

#### US-09 Ship order

**US-09:** As an OrderStaff, I want to set a filled order to shipped, so that it is known that the goods are on their way to the customer.

Acceptance criteria:

- **US-09-AC01** (Given-When-Then): Given an order whose status is filled, When order staff set it to shipped, Then the system sets its status to shipped.
- **US-09-AC02** (Given-When-Then): Given an order whose status is not filled, When order staff attempt to set it to shipped, Then the system rejects the attempt and the status of the order is unchanged.
- **US-09-AC03** (Given-When-Then): Given an order that has an invoice with payments against it, When order staff set the order to shipped, Then the status of the invoice and the status of every payment against it are unchanged.
- **US-09-AC04** (Given-When-Then): Given an order whose status is filled and that has no invoice, When order staff set it to shipped, Then the system sets its status to shipped without requiring an invoice to have been raised.
- **US-09-AC05** (Given-When-Then): Given an order whose status is closed, When order staff attempt to set it to shipped, Then the system rejects the attempt and the order keeps the status closed.
- **US-09-AC06** (Condition): Setting an order to shipped changes its status only from filled to shipped.

#### US-10 Confirm payment

**US-10:** As an Accountant, I want to confirm a pending payment once the money has been received, so that the invoice it settles is recorded as paid.

Acceptance criteria:

- **US-10-AC01** (Given-When-Then): Given a payment whose status is pending, When the accountant confirms it, Then the system sets its status to completed.
- **US-10-AC02** (Given-When-Then): Given a pending payment against an invoice whose status is issued, When the accountant confirms the payment, Then the system sets the status of that invoice to paid.
- **US-10-AC03** (Given-When-Then): Given a pending payment against an invoice whose status is already paid, When the accountant confirms the payment, Then the system sets the payment to completed and the invoice keeps the status paid.
- **US-10-AC04** (Given-When-Then): Given a pending payment against an invoice that bills an order, When the accountant confirms the payment, Then the status of that order is unchanged.
- **US-10-AC05** (Given-When-Then): Given a payment whose status is not pending, When the accountant attempts to confirm it, Then the system rejects the attempt and the status of the payment is unchanged.
- **US-10-AC06** (Condition): Confirming a payment changes the status of the payment only from pending to completed and the status of its invoice only from issued to paid.

#### US-11 Reject payment

**US-11:** As an Accountant, I want to reject a pending payment that has not been honoured, so that the invoice stays open for the customer to pay again.

Acceptance criteria:

- **US-11-AC01** (Given-When-Then): Given a payment whose status is pending, When the accountant rejects it, Then the system sets its status to failed.
- **US-11-AC02** (Given-When-Then): Given a pending payment against an invoice that bills an order, When the accountant rejects the payment, Then the status of the invoice and the status of the order are unchanged.
- **US-11-AC03** (Given-When-Then): Given a payment whose status is not pending, When the accountant attempts to reject it, Then the system rejects the attempt and the status of the payment is unchanged.
- **US-11-AC04** (Condition): Rejecting a payment changes its status only from pending to failed.

#### US-12 Close order

**US-12:** As an OrderStaff, I want to close a shipped order whose invoice has been paid, so that completed orders are set apart from orders that still need work.

Acceptance criteria:

- **US-12-AC01** (Given-When-Then): Given an order whose status is shipped and whose invoice has the status paid, When order staff close it, Then the system sets its status to closed.
- **US-12-AC02** (Given-When-Then): Given an order whose status is shipped and that has no invoice or whose invoice does not have the status paid, When order staff attempt to close it, Then the system rejects the attempt and the status of the order is unchanged.
- **US-12-AC03** (Given-When-Then): Given an order whose invoice has the status paid and whose status is not shipped, When order staff attempt to close it, Then the system rejects the attempt and the status of the order is unchanged.
- **US-12-AC04** (Condition): A filled order is closed only after both its shipping and the settlement of its invoice have completed, whichever of the two finishes last.
- **US-12-AC05** (Condition): Once an order has the status closed, its status never changes again.
- **US-12-AC06** (Condition): Closing an order changes its status only from shipped to closed.

### 3.2 Quality attributes

#### 3.2.1 Performance

- **NFR-01:** When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions.
- **NFR-02:** Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time stated in NFR-01.

#### 3.2.2 Security

- **NFR-03:** The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04:** The system shall allow only users holding the Accountant role to confirm or reject a payment, and shall reject 100% of such requests from users who do not hold that role.
- **NFR-05:** The system shall encrypt customer personal data and bank account numbers in transit using TLS 1.2 or higher and shall store them encrypted at rest.
- **NFR-06:** The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain each such record for at least 12 months.

#### 3.2.3 Availability

- **NFR-07:** The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08:** When a server failure occurs, the system shall resume accepting requests within 15 minutes and shall lose none of the orders, invoices and payments recorded before the failure.

## 4. Verification

Each requirement is verified by the methods below. `VMX.csv` lists, for every requirement, the domain requirements it originates from and the elements of `structural.puml` and `behavioral.puml` that realize it, and serves as the verification matrix.

- **Given-When-Then criteria** are verified by test: each criterion is executed as one acceptance test scenario that establishes the precondition, performs the trigger and observes the outcome, including for refused requests that the status and records are unchanged.
- **Condition criteria** are verified by inspection of `structural.puml` against the criterion (data types, permitted values, multiplicities and lifetimes) and by test: attempts to store a value outside the permitted set, to omit a mandatory attribute, to violate a multiplicity or to perform a status change not permitted by the criterion are each executed and shown to be refused.
- **NFR-01 and NFR-02** are verified by load test in a production-like environment: 200 concurrent simulated users submit orders of up to 50 order items at 20 submissions per second for at least one hour, and the 95th percentile response time is measured.
- **NFR-03 to NFR-06** are verified by test and inspection: unauthenticated requests to every data endpoint are sent and shown to be refused (NFR-03); payment confirmation and rejection are attempted with each non-accountant role and shown to be refused (NFR-04); the transport protocol version and the storage encryption are inspected (NFR-05); and every status change performed during acceptance testing is checked against the audit records, whose retention setting is inspected (NFR-06).
- **NFR-07** is verified by analysis of monitoring records over each calendar month, deducting only maintenance windows announced at least 24 hours in advance.
- **NFR-08** is verified by test: a server is stopped while orders, invoices and payments are being recorded, the time until requests are accepted again is measured, and the records made before the failure are compared with those present after recovery.

The requirement identifiers, statements and acceptance criteria in this document are listed in machine-readable form in `requirements.json`.

## 5. Supporting information

- `structural.puml`: structural model (UML class diagram) of the domain classes, their typed attributes, the enumerations of permitted values and the relationships with their multiplicities.
- `behavioral.puml`: behavioral model (UML activity diagram) of the order process, with one swimlane per role, the parallel shipping and invoicing branches, the payment retry loop and the status reached by each entity after each action.
- `requirements.json`: machine-readable listing of every requirement and acceptance criterion in this document.
- `VMX.csv`: traceability matrix linking every requirement to its domain requirements and to the diagram elements that realize it.
- Source: Order Management System — Domain Requirements, REQ-F-01 to REQ-F-50 and REQ-N-01 to REQ-N-08, dated 2026-10-21.
