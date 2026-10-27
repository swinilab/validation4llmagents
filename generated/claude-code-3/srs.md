# Software Requirements Specification — Order Management System

Version 1.1, based on the domain requirements dated 2026-10-21.

## 1. Introduction

### 1.1 Purpose

This document specifies the software requirements of the Order Management System. It states every functional requirement as a user story with acceptance criteria and every quality attribute as a measurable declarative requirement. It is written for the people who design, build, test and accept the system, and it is the reference against which the delivered system is verified.

### 1.2 Scope

The Order Management System supports the life of a customer order from submission to closure. It holds customer and product data, lets customers submit orders and pay invoices, lets order staff receive, fill, decline, ship and close orders, and lets accountants raise invoices and confirm or reject payments. Product catalogue administration, delivery logistics, the processing of payments by banks or card networks, and reporting are outside the scope of this document.

### 1.3 Definitions and acronyms

| Term | Definition |
| --- | --- |
| Customer | The end user who browses products, submits orders and pays invoices. |
| OrderStaff | Internal staff who receive, validate and fulfil orders. Referred to in criteria as "the order staff". |
| Accountant | Internal staff who raise invoices and record the payments received. |
| Order | A customer's request for one or more products, made of order items. |
| Order item | One line of an order: a quantity of exactly one product at a unit price. It exists only as part of its order. |
| Invoice | The bill raised for exactly one order. An order has at most one invoice. |
| Payment | One attempt by a customer to settle an invoice. An invoice may have several payments. |
| Declined order | An order that order staff set from pending to closed without filling it. |
| Settlement | The confirmation of a payment that sets the invoice to paid. |
| Decimal number | An exact base-10 number used for every monetary value. |
| AC | Acceptance criterion. |
| FR, NFR | Functional requirement, non-functional requirement. |
| SRS | Software Requirements Specification. |
| TLS | Transport Layer Security. |
| US | User story. |

## 2. Overall description

### 2.1 Product perspective

The Order Management System is a self-contained, multi-user system that holds the records of customers, products, orders, order items, invoices and payments. Its domain classes, attributes, enumerations and relationships are given in `structural.puml`. The flow of an order through the three roles, including the parallel shipping and invoicing branches and the payment retry loop, is given in `behavioral.puml`.

### 2.2 Product functions

The system provides the following functions, each specified as one user story in clause 3.1:

- Register customer details (US-01)
- Browse products (US-02)
- Submit order (US-03)
- Raise invoice (US-04)
- Submit payment (US-05)
- Receive order (US-06)
- Mark order as filled (US-07)
- Decline order (US-08)
- Ship order (US-09)
- Confirm payment (US-10)
- Reject payment (US-11)
- Close order (US-12)

### 2.3 User characteristics

- Customers are members of the public with no training in the system. They act only on their own customer details, orders and invoices.
- Order staff are trained employees who handle orders daily and know the order statuses and the permitted status changes.
- Accountants are trained employees who handle invoices and payments and know the invoice and payment statuses.

### 2.4 Assumptions and dependencies

- Product records exist in the system before customers browse them. How they are entered is outside the scope of this document; whatever enters them is subject to the product criteria of US-02.
- The date of an order is the date on which the system registers its submission.
- The system records payments but does not move money. Whether a payment was received is determined by the accountant outside the system and recorded through US-10 or US-11.
- The decision to decline an order is taken by order staff outside the system and recorded through US-08.
- The system exposes no operation that removes an order. The lifetime rules for order items and products state what holds if one is introduced.
- "Normal operating conditions" means the load stated in NFR-02 on the production infrastructure with no component failed.

## 3. Requirements

### 3.1 Functional requirements

Each user story below is one unit of business intent: one thing that one role does in the order process for a reason of its own. The granularity follows the business process, with one story per step a role takes: registering, browsing, ordering, invoicing, paying, and each step order staff and accountants take on an order or a payment. The stories are numbered in the order in which their capabilities are first reached in the domain requirements, which is why raising an invoice (first reached in the invoice data requirements) precedes receiving an order. A rule that the domain requirements state once but that governs several steps, such as the permitted status values and status changes, the permitted payment methods and the use of decimal numbers for money, appears in the acceptance criteria of every story it governs, phrased for that story. Data rules (attributes, multiplicities and lifetimes) are placed in the story that creates the data they constrain. A retried payment is the same intent as a first payment and is therefore part of US-05 rather than a story of its own. The domain requirements realized by each story are recorded in `VMX.csv`, and the stories and criteria are listed in `requirements.json`.

#### US-01 Register customer details

**US-01**: As a Customer, I want to register my customer details, so that my orders can be delivered to me and I can be contacted about them.

Acceptance criteria:

- **US-01-AC01** (Condition): Each customer record holds a name, an address and a phone number, each of which is mandatory.
- **US-01-AC02** (Condition): A customer has zero or one bank account, and the bank account is the only optional attribute of a customer.
- **US-01-AC03** (Given-When-Then): Given a customer registration in which the name, the address or the phone number is absent, When the customer submits it, Then the system rejects the registration and stores no customer record.
- **US-01-AC04** (Given-When-Then): Given a customer registration that holds a name, an address and a phone number but no bank account, When the customer submits it, Then the system stores the customer record without a bank account.
- **US-01-AC05** (Given-When-Then): Given a customer registration that holds a name, an address, a phone number and one bank account, When the customer submits it, Then the system stores the customer record with that bank account.
- **US-01-AC06** (Given-When-Then): Given a customer registration that names more than one bank account, When the customer submits it, Then the system rejects the registration and stores no customer record.

#### US-02 Browse products

**US-02**: As a Customer, I want to browse the products on offer, so that I can choose which products to order.

Acceptance criteria:

- **US-02-AC01** (Condition): Each product record holds a name, a description, a price and an image, each of which is mandatory.
- **US-02-AC02** (Condition): The price of a product is a decimal number.
- **US-02-AC03** (Given-When-Then): Given a product record in which the name, the description, the price or the image is absent, When it is submitted for storage, Then the system rejects it and the product does not appear among the products on offer.
- **US-02-AC04** (Given-When-Then): Given stored products, When the customer browses the products on offer, Then the system shows the name, the description, the price and the image of each product.
- **US-02-AC05** (Condition): A product may be referred to by any number of order items, including none.
- **US-02-AC06** (Given-When-Then): Given a product that is referred to by the order items of an order, When that order and its order items are removed, Then the product still exists and remains among the products on offer.

#### US-03 Submit order

**US-03**: As a Customer, I want to submit an order for one or more products, so that I receive the products I have chosen.

Acceptance criteria:

- **US-03-AC01** (Given-When-Then): Given a known customer, one or more order items that each refer to an existing product, and a payment method, When the customer submits the order, Then the system registers an order associated with that customer, with the submission date as its order date and the status submitted.
- **US-03-AC02** (Given-When-Then): Given an order submission that names a customer not known to the system, When the customer submits it, Then the system rejects the submission and registers no order.
- **US-03-AC03** (Given-When-Then): Given an order submission that contains no order item, When the customer submits it, Then the system rejects the submission and registers no order.
- **US-03-AC04** (Given-When-Then): Given an order submission in which at least one order item refers to a product that does not exist, When the customer submits it, Then the system rejects the submission and registers no order.
- **US-03-AC05** (Given-When-Then): Given an order submission whose payment method is not bank, card or cash, When the customer submits it, Then the system rejects the submission and registers no order.
- **US-03-AC06** (Condition): The total amount of a registered order equals the sum over its order items of quantity multiplied by unit price.
- **US-03-AC07** (Condition): Each order holds an order date, a total amount, a status and a payment method, each of which is mandatory.
- **US-03-AC08** (Condition): Each order item holds a quantity, a unit price and a reference to exactly one product, each of which is mandatory.
- **US-03-AC09** (Condition): Each order item belongs to exactly one order and cannot be moved to another order.
- **US-03-AC10** (Condition): An order item exists only as part of the order it belongs to, and the order items of an order are removed when that order is removed.
- **US-03-AC11** (Condition): Each order is associated with exactly one customer, and a customer may have any number of orders.
- **US-03-AC12** (Condition): The total amount of an order and the unit price of an order item are decimal numbers.
- **US-03-AC13** (Condition): The payment method of an order is one of bank, card or cash.
- **US-03-AC14** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.

#### US-04 Raise invoice

**US-04**: As an Accountant, I want to raise an invoice for a filled order, so that the customer is billed for the goods supplied.

Acceptance criteria:

- **US-04-AC01** (Given-When-Then): Given an order whose status is filled or shipped and that has no invoice, When the accountant raises an invoice for it with a date, an amount and a payment method, Then the system records the invoice for that order with the status issued.
- **US-04-AC02** (Given-When-Then): Given an order that already has an invoice, When the accountant raises a further invoice for it, Then the system rejects the request and records no further invoice.
- **US-04-AC03** (Given-When-Then): Given an order whose status is submitted, pending or closed, When the accountant raises an invoice for it, Then the system rejects the request and records no invoice.
- **US-04-AC04** (Given-When-Then): Given an order that has been declined, When the accountant raises an invoice for it, Then the system rejects the request and records no invoice.
- **US-04-AC05** (Given-When-Then): Given a filled order that has not been shipped, When the accountant raises an invoice for it, Then the system records the invoice without requiring the order to have been shipped.
- **US-04-AC06** (Condition): Raising the invoice of a filled order and setting that order to shipped may occur in either order or at the same time.
- **US-04-AC07** (Condition): Each invoice holds a date, an amount, a status and a payment method, each of which is mandatory.
- **US-04-AC08** (Condition): Each invoice is associated with exactly one order, and an order has at most one invoice.
- **US-04-AC09** (Condition): The amount of an invoice is a decimal number.
- **US-04-AC10** (Condition): The payment method of an invoice is one of bank, card or cash.
- **US-04-AC11** (Condition): The status of an invoice is one of issued or paid.
- **US-04-AC12** (Condition): The status of an invoice changes only from issued to paid.

#### US-05 Submit payment

**US-05**: As a Customer, I want to pay an issued invoice, so that I settle what I owe for my order.

Acceptance criteria:

- **US-05-AC01** (Given-When-Then): Given an invoice whose status is issued, When the customer submits a payment against it with a date, an amount and a payment method, Then the system records the payment against that invoice with the status pending.
- **US-05-AC02** (Given-When-Then): Given an invoice whose status is paid, When the customer submits a payment against it, Then the system rejects the payment and records no payment.
- **US-05-AC03** (Given-When-Then): Given an invoice whose earlier payment has the status failed, When the customer submits a further payment against it, Then the system records the further payment as a separate payment with the status pending and keeps the earlier payment at the status failed.
- **US-05-AC04** (Condition): Each payment is recorded against exactly one invoice and never directly against an order, and an invoice may have any number of payments.
- **US-05-AC05** (Condition): Each payment holds a date, an amount, a status and a payment method, each of which is mandatory.
- **US-05-AC06** (Condition): The amount of a payment is a decimal number.
- **US-05-AC07** (Condition): The payment method of a payment is one of bank, card or cash.
- **US-05-AC08** (Condition): The status of a payment is one of pending, completed or failed.
- **US-05-AC09** (Condition): The status of a payment changes only from pending to completed or from pending to failed.

#### US-06 Receive order

**US-06**: As an OrderStaff, I want to receive a submitted order, so that I can take it in hand for validation and fulfilment.

Acceptance criteria:

- **US-06-AC01** (Given-When-Then): Given an order whose status is submitted, When the order staff receives it, Then the system sets the status of the order to pending.
- **US-06-AC02** (Given-When-Then): Given an order whose status is not submitted, When the order staff attempts to receive it, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-06-AC03** (Given-When-Then): Given an order whose status is closed, When the order staff attempts to receive it, Then the system leaves the status of the order at closed.
- **US-06-AC04** (Condition): Receiving an order changes its status only from submitted to pending.
- **US-06-AC05** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.

#### US-07 Mark order as filled

**US-07**: As an OrderStaff, I want to mark a pending order as filled, so that everyone knows the goods are ready for shipping and invoicing.

Acceptance criteria:

- **US-07-AC01** (Given-When-Then): Given an order whose status is pending, When the order staff marks it as filled, Then the system sets the status of the order to filled.
- **US-07-AC02** (Given-When-Then): Given an order whose status is not pending, When the order staff attempts to mark it as filled, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-07-AC03** (Given-When-Then): Given an order whose status is closed, When the order staff attempts to mark it as filled, Then the system leaves the status of the order at closed.
- **US-07-AC04** (Condition): Marking an order as filled changes its status only from pending to filled.
- **US-07-AC05** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.

#### US-08 Decline order

**US-08**: As an OrderStaff, I want to decline a pending order, so that an order the business cannot fulfil is ended.

Acceptance criteria:

- **US-08-AC01** (Given-When-Then): Given an order whose status is pending, When the order staff declines it, Then the system sets the status of the order to closed.
- **US-08-AC02** (Given-When-Then): Given an order whose status is not pending, When the order staff attempts to decline it, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-08-AC03** (Given-When-Then): Given an order that the order staff has declined, When an invoice is requested for that order, Then the system rejects the request and records no invoice.
- **US-08-AC04** (Given-When-Then): Given an order whose status is closed, When the order staff attempts to decline it, Then the system leaves the status of the order at closed.
- **US-08-AC05** (Condition): Declining an order changes its status only from pending to closed.
- **US-08-AC06** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.

#### US-09 Ship order

**US-09**: As an OrderStaff, I want to set a filled order to shipped, so that the dispatch of the customer's goods is on record.

Acceptance criteria:

- **US-09-AC01** (Given-When-Then): Given an order whose status is filled, When the order staff sets it to shipped, Then the system sets the status of the order to shipped.
- **US-09-AC02** (Given-When-Then): Given an order whose status is not filled, When the order staff attempts to set it to shipped, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-09-AC03** (Given-When-Then): Given a filled order that has an invoice with payments against it, When the order staff sets the order to shipped, Then the system leaves the status of the invoice and of every payment against it unchanged.
- **US-09-AC04** (Given-When-Then): Given a filled order that has no invoice, When the order staff sets it to shipped, Then the system sets the status of the order to shipped without requiring an invoice to have been raised.
- **US-09-AC05** (Condition): Setting a filled order to shipped and raising its invoice may occur in either order or at the same time.
- **US-09-AC06** (Given-When-Then): Given an order whose status is closed, When the order staff attempts to set it to shipped, Then the system leaves the status of the order at closed.
- **US-09-AC07** (Condition): Setting an order to shipped changes its status only from filled to shipped.
- **US-09-AC08** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.

#### US-10 Confirm payment

**US-10**: As an Accountant, I want to confirm a pending payment, so that money actually received is recorded as settling the invoice.

Acceptance criteria:

- **US-10-AC01** (Given-When-Then): Given a payment whose status is pending, When the accountant confirms it, Then the system sets the status of the payment to completed.
- **US-10-AC02** (Given-When-Then): Given a pending payment against an invoice whose status is issued, When the accountant confirms the payment, Then the system sets the status of that invoice to paid.
- **US-10-AC03** (Given-When-Then): Given a pending payment against an invoice, When the accountant confirms the payment, Then the system leaves the status of the order billed by that invoice unchanged.
- **US-10-AC04** (Given-When-Then): Given a payment whose status is not pending, When the accountant attempts to confirm it, Then the system rejects the attempt and leaves the status of the payment unchanged.
- **US-10-AC05** (Condition): Confirming a payment changes its status only from pending to completed.
- **US-10-AC06** (Condition): Confirming a payment changes the status of its invoice only from issued to paid.
- **US-10-AC07** (Condition): The status of a payment is one of pending, completed or failed.
- **US-10-AC08** (Condition): The status of an invoice is one of issued or paid.

#### US-11 Reject payment

**US-11**: As an Accountant, I want to reject a pending payment, so that a payment that was not received does not count towards settling the invoice.

Acceptance criteria:

- **US-11-AC01** (Given-When-Then): Given a payment whose status is pending, When the accountant rejects it, Then the system sets the status of the payment to failed.
- **US-11-AC02** (Given-When-Then): Given a pending payment against an invoice, When the accountant rejects the payment, Then the system leaves the status of that invoice and of the order billed by it unchanged.
- **US-11-AC03** (Given-When-Then): Given a payment whose status is not pending, When the accountant attempts to reject it, Then the system rejects the attempt and leaves the status of the payment unchanged.
- **US-11-AC04** (Condition): Rejecting a payment changes its status only from pending to failed.
- **US-11-AC05** (Condition): The status of a payment is one of pending, completed or failed.

#### US-12 Close order

**US-12**: As an OrderStaff, I want to close a shipped order whose invoice has been paid, so that a completed order is finished and protected from further change.

Acceptance criteria:

- **US-12-AC01** (Given-When-Then): Given an order whose status is shipped and whose invoice has the status paid, When the order staff closes it, Then the system sets the status of the order to closed.
- **US-12-AC02** (Given-When-Then): Given an order whose status is shipped and that has no invoice or an invoice whose status is not paid, When the order staff attempts to close it, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-12-AC03** (Given-When-Then): Given an order whose invoice has the status paid and whose status is not shipped, When the order staff attempts to close it, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-12-AC04** (Given-When-Then): Given a filled order, When its shipping and the settlement of its invoice complete in either order, Then the system allows the order to be closed only after the later of the two has completed.
- **US-12-AC05** (Condition): The status of an order whose status is closed is never changed.
- **US-12-AC06** (Condition): Closing an order changes its status only from shipped to closed.
- **US-12-AC07** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.

### 3.2 Quality attributes

#### 3.2.1 Performance

- **NFR-01**: The system shall register a submitted order containing up to 50 order items and respond within 2 seconds for at least 95% of such submissions under normal operating conditions.
- **NFR-02**: The system shall support at least 200 concurrent users and at least 20 order submissions per second under normal operating conditions while meeting the response time of NFR-01.

#### 3.2.2 Security

- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04**: The system shall allow only users holding the Accountant role to confirm or reject a payment, and shall reject 100% of such requests from users who do not hold that role.
- **NFR-05**: The system shall encrypt customer personal data and bank account numbers in transit using TLS 1.2 or higher and at rest, so that none of this data is transmitted or stored in plaintext.
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain each such record for at least 12 months.

#### 3.2.3 Availability

- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08**: The system shall resume accepting requests within 15 minutes of a server failure without losing any order, invoice or payment recorded before the failure.

## 4. Verification

Each requirement is verified as follows. The traceability of each requirement to the domain requirements it originates from, and to the elements of `structural.puml` and `behavioral.puml` that realize it, is recorded in `VMX.csv`.

- Given-When-Then criteria are verified by test: the precondition is set up, the trigger is performed through the role named in the story, and the outcome is observed in the stored records. Every rejection criterion is also verified by checking that no record was created or changed.
- Condition criteria are verified by inspection of the data model against `structural.puml` and by test: an attempt to store a value outside the permitted set, to omit a mandatory attribute, to break a multiplicity or to perform a status change that is not permitted is made and shown to be refused.
- NFR-01 and NFR-02 are verified by load test at 200 concurrent users and 20 order submissions per second with orders of up to 50 order items, measuring the 95th percentile of the submission response time.
- NFR-03 and NFR-04 are verified by test: authenticated and unauthenticated requests are issued against every operation, and payment confirmation and rejection are attempted by users holding each role.
- NFR-05 is verified by inspection of the transport configuration and of the stored data, and by test that a connection offering only a TLS version below 1.2 is refused.
- NFR-06 is verified by test that every status change specified in US-06 to US-12 produces a record of user and time, and by inspection of the retention configuration.
- NFR-07 is verified by monitoring the availability of the system over each calendar month in operation.
- NFR-08 is verified by a failover test in which a server is stopped after orders, invoices and payments have been recorded, measuring the time until requests are accepted again and comparing the records before and after.

## 5. Supporting information

This specification is accompanied by the following files:

| File | Content |
| --- | --- |
| `structural.puml` | Structural model: the domain classes, their typed attributes, the enumerations of permitted values and the relationships with their multiplicities. |
| `behavioral.puml` | Behavioral model: an activity diagram, partitioned into the Customer, OrderStaff and Accountant swimlanes, of an order from submission to closure. |
| `requirements.json` | Machine-readable listing of every requirement and acceptance criterion in this document. |
| `VMX.csv` | Traceability matrix from each requirement to its domain requirements and to the diagram elements that realize it. |

The permitted status changes specified across clause 3.1 are summarized below.

| Entity | From | To | Story |
| --- | --- | --- | --- |
| Order | submitted | pending | US-06 |
| Order | pending | filled | US-07 |
| Order | pending | closed | US-08 |
| Order | filled | shipped | US-09 |
| Order | shipped | closed | US-12 |
| Invoice | issued | paid | US-10 |
| Payment | pending | completed | US-10 |
| Payment | pending | failed | US-11 |
