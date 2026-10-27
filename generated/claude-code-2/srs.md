# Software Requirements Specification — Order Management System

Version 1.1, based on the domain requirements dated 2026-10-21.

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) specifies the Order Management System. It states every functional requirement as a user story with acceptance criteria, and every quality attribute as a declarative, measurable requirement. It is written for the business stakeholders who accept the system, for the developers who build it, and for the testers who verify it.

### 1.2 Scope

The Order Management System supports the sales cycle of a business that sells products to registered customers. It covers:

- the customer and product records the cycle relies on;
- submission of orders by customers, with validation of the customer, the order items and the referenced products;
- fulfilment of orders by order staff: receiving, filling or declining, shipping and closing;
- invoicing of filled orders by accountants;
- submission of payments by customers and their confirmation or rejection by accountants.

Delivery logistics, the transfer of money between banks, and the maintenance of user accounts and roles are outside the scope of the system; the system records their outcome only where this specification says so.

### 1.3 Definitions and acronyms

| Term | Definition |
| --- | --- |
| Customer | Role: the end user who browses products, submits orders and pays invoices. |
| OrderStaff | Role: internal staff who receive, validate and fulfil orders. Also called order staff. |
| Accountant | Role: internal staff who raise invoices and record the payments received. |
| Order | A request by one customer for one or more products, with a payment method. |
| Order item | One line of an order: a quantity and a unit price of exactly one product. |
| Invoice | The bill raised for one order. |
| Payment | One attempt by a customer to settle an invoice. |
| Payment method | The means of payment: bank, card or cash. |
| Known customer | A customer whose record has been accepted by the system. |
| Declined order | An order that order staff have closed from the status pending without filling it. |
| Settlement | The confirmation of a payment, which sets the invoice to paid. |
| AC | Acceptance criterion. |
| GWT | Given-When-Then, the form of an acceptance criterion that describes the outcome of a trigger. |
| NFR | Non-functional requirement. |
| SRS | Software Requirements Specification. |
| TLS | Transport Layer Security. |
| US | User story. |

## 2. Overall description

### 2.1 Product perspective

The Order Management System is a self-contained, multi-user system that holds the records of customers, products, orders, order items, invoices and payments and controls the status of orders, invoices and payments. Its information structure is given in the structural model `structural.puml`, and the flow of an order from submission to closure, partitioned by role, is given in the behavioral model `behavioral.puml`.

An order passes through the statuses submitted, pending, filled, shipped and closed. Once an order is filled, two independent strands proceed in parallel: order staff ship the order, while the accountant raises an invoice that the customer pays, possibly after one or more failed payments. The order is closed when both strands have completed. An order that cannot be fulfilled is declined from pending straight to closed and is never invoiced.

### 2.2 Product functions

The system provides the following functions, each specified by one user story in clause 3.1:

- register a customer record (US-01);
- browse the product catalogue (US-02);
- submit an order (US-03);
- raise an invoice (US-04);
- submit a payment (US-05);
- receive an order (US-06);
- mark an order as filled (US-07);
- decline an order (US-08);
- set an order to shipped (US-09);
- confirm a payment (US-10);
- reject a payment (US-11);
- close an order (US-12).

### 2.3 User characteristics

- **Customer**: a member of the public with no knowledge of the internal process. A customer registers once, then browses, orders and pays through the system.
- **OrderStaff**: trained internal staff who handle orders daily and know the fulfilment process.
- **Accountant**: trained internal staff who know invoicing and the reconciliation of payments. Only accountants confirm or reject payments.

### 2.4 Assumptions and dependencies

- Every user has been assigned exactly one of the roles Customer, OrderStaff or Accountant before using the system; role assignment is performed outside the system.
- Products are recorded in the system before customers order them; the product records are maintained outside the scope of the stories, but the system enforces the product rules of US-02 whenever a product record is stored.
- Whether a payment has actually been received is established by the accountant outside the system, for example from a bank statement; the system records the accountant's decision.
- The date of an order is the date on the system clock at the moment of submission.
- The quality attributes of clause 3.2 assume the normal operating conditions agreed with the operator of the system.

## 3. Requirements

### 3.1 Functional requirements

Each functional requirement is stated as one user story, followed by its acceptance criteria. Each criterion is either in Given-When-Then form, describing what happens when something occurs, or in Condition form, stating a constraint that holds independently of any trigger.

**Granularity.** A story is one unit of business intent: one thing a role does in the sales cycle that moves it forward. The cycle consists of twelve such steps: the customer registers, browses, orders and pays; order staff receive, fill or decline, ship and close; the accountant invoices and confirms or rejects payments. Each step is one story. The rules that govern a step, namely its refusals, the attributes and value sets it reads or writes, the multiplicities and lifetimes of the entities it relates, and its effect on other entities, are acceptance criteria of that step's story rather than stories of their own, because none of them is something a role wants for its own sake. A rule that governs several steps, such as the permitted status changes, the permitted payment methods or the rule that a closed order never changes, is repeated in each story it governs, phrased for that story.

**Order.** The stories are numbered in the order in which the capability each one specifies is first reached in the input functional requirements: the customer and product records come first, followed by the order, the invoice and the payment, whose records are introduced before the steps that change their status, and finally the fulfilment, settlement and closing steps.

#### US-01 Register customer record

As a Customer, I want to register my name, address and phone number, and optionally one bank account, so that the business knows who I am and can deliver my orders and contact me about them.

Acceptance criteria:

- **US-01-AC01** (Condition): A customer record holds a name, an address and a phone number, and each of these attributes is mandatory.
- **US-01-AC02** (Given-When-Then): Given a customer record in which the name, the address or the phone number is absent, When the record is submitted, Then the system rejects the record and records no customer.
- **US-01-AC03** (Given-When-Then): Given a customer record with a name, an address and a phone number, When the record is submitted, Then the system records the customer and the customer becomes known to the system.
- **US-01-AC04** (Condition): A customer has at most one bank account, and the bank account is optional.
- **US-01-AC05** (Given-When-Then): Given a customer record that contains no bank account, When the record is submitted, Then the system records the customer without a bank account.
- **US-01-AC06** (Given-When-Then): Given a customer who already has a bank account, When a second bank account is added for that customer, Then the system rejects the addition and the customer keeps exactly one bank account.
- **US-01-AC07** (Condition): A customer may have any number of orders, including none.

#### US-02 Browse product catalogue

As a Customer, I want to browse the products on offer with their name, description, price and image, so that I can choose what to order.

Acceptance criteria:

- **US-02-AC01** (Condition): A product record holds a name, a description, a price and an image, and each of these attributes is mandatory.
- **US-02-AC02** (Given-When-Then): Given a product record in which the name, the description, the price or the image is absent, When the record is submitted for storage, Then the system rejects the record and records no product.
- **US-02-AC03** (Given-When-Then): Given a stored product, When the customer browses the products, Then the system shows the name, the description, the price and the image of that product.
- **US-02-AC04** (Condition): The price of a product is a decimal number.
- **US-02-AC05** (Condition): A product may be referred to by any number of order items, including none.
- **US-02-AC06** (Condition): A product exists independently of the order items that refer to it and remains stored when an order item that refers to it is removed.

#### US-03 Submit order

As a Customer, I want to submit an order for one or more products with a payment method of my choice, so that the business can fulfil my purchase.

Acceptance criteria:

- **US-03-AC01** (Given-When-Then): Given a known customer, one or more order items each referring to an existing product, and a payment method, When the customer submits the order, Then the system registers an order with the submission date as its order date and the status submitted.
- **US-03-AC02** (Given-When-Then): Given an order submission that names a customer not known to the system, When the submission is made, Then the system rejects the submission and registers no order.
- **US-03-AC03** (Given-When-Then): Given an order submission that contains no order item, When the submission is made, Then the system rejects the submission and registers no order.
- **US-03-AC04** (Given-When-Then): Given an order submission in which any order item refers to a product that does not exist, When the submission is made, Then the system rejects the submission and registers no order.
- **US-03-AC05** (Condition): The total amount of a registered order equals the sum over its order items of quantity multiplied by unit price.
- **US-03-AC06** (Condition): An order records an order date, a total amount, a status and a payment method, and each of these attributes is mandatory.
- **US-03-AC07** (Condition): An order item records a quantity, a unit price and a reference to exactly one product, and each of these is mandatory.
- **US-03-AC08** (Condition): An order contains one or more order items.
- **US-03-AC09** (Condition): Each order item is associated with exactly one order.
- **US-03-AC10** (Condition): An order item cannot be moved from the order it belongs to into another order.
- **US-03-AC11** (Condition): An order item exists only as part of its order, and the order items of an order are removed when that order is removed.
- **US-03-AC12** (Condition): Each order is associated with exactly one customer, and a customer may have any number of orders.
- **US-03-AC13** (Condition): The unit price of an order item and the total amount of an order are decimal numbers.
- **US-03-AC14** (Condition): The payment method of an order is one of bank, card or cash.
- **US-03-AC15** (Condition): The status of an order is one of submitted, pending, filled, shipped or closed.
- **US-03-AC16** (Condition): A newly registered order has the status submitted, from which the only permitted status change is to pending.

#### US-04 Raise invoice

As an Accountant, I want to raise an invoice for an order that has been filled, so that the customer is billed for the goods and the money owed can be collected.

Acceptance criteria:

- **US-04-AC01** (Given-When-Then): Given an order whose status is filled or shipped and that has no invoice, When the accountant raises an invoice with a date, an amount and a payment method, Then the system records the invoice against that order with the status issued.
- **US-04-AC02** (Given-When-Then): Given an order that already has an invoice, When the accountant requests a further invoice for that order, Then the system rejects the request and records no further invoice.
- **US-04-AC03** (Given-When-Then): Given an order whose status is submitted, pending or closed, When the accountant requests an invoice for that order, Then the system rejects the request and records no invoice.
- **US-04-AC04** (Given-When-Then): Given an order that has been declined, When the accountant requests an invoice for that order, Then the system rejects the request and records no invoice.
- **US-04-AC05** (Given-When-Then): Given an order whose status is filled and that has not been set to shipped, When the accountant raises an invoice for that order, Then the system records the invoice without requiring the order to have been shipped and leaves the status of the order at filled.
- **US-04-AC06** (Condition): An invoice records a date, an amount, a status and a payment method, and each of these attributes is mandatory.
- **US-04-AC07** (Condition): An order has at most one invoice, and each invoice is associated with exactly one order.
- **US-04-AC08** (Condition): The amount of an invoice is a decimal number.
- **US-04-AC09** (Condition): The payment method of an invoice is one of bank, card or cash.
- **US-04-AC10** (Condition): The status of an invoice is one of issued or paid.
- **US-04-AC11** (Condition): A newly raised invoice has the status issued, from which the only permitted status change is to paid.

#### US-05 Submit payment

As a Customer, I want to pay an invoice that has been issued to me, so that I settle what I owe for my order.

Acceptance criteria:

- **US-05-AC01** (Given-When-Then): Given an invoice whose status is issued, When the customer submits a payment against it with a date, an amount and a payment method, Then the system records the payment against that invoice with the status pending.
- **US-05-AC02** (Given-When-Then): Given an invoice whose status is paid, When the customer submits a payment against it, Then the system rejects the payment and records no payment.
- **US-05-AC03** (Given-When-Then): Given an invoice whose earlier payment has the status failed, When the customer submits a further payment against that invoice, Then the system records the further payment as a separate payment with the status pending and keeps the earlier payment at the status failed.
- **US-05-AC04** (Condition): A payment records a date, an amount, a status and a payment method, and each of these attributes is mandatory.
- **US-05-AC05** (Condition): An invoice may have any number of payments, including none, and each payment is recorded against exactly one invoice.
- **US-05-AC06** (Condition): A payment is recorded against an invoice and never directly against an order.
- **US-05-AC07** (Condition): The amount of a payment is a decimal number.
- **US-05-AC08** (Condition): The payment method of a payment is one of bank, card or cash.
- **US-05-AC09** (Condition): The status of a payment is one of pending, completed or failed.
- **US-05-AC10** (Condition): A newly submitted payment has the status pending, from which the only permitted status changes are to completed or to failed.

#### US-06 Receive order

As an OrderStaff, I want to receive a submitted order, so that it enters fulfilment and is not overlooked.

Acceptance criteria:

- **US-06-AC01** (Given-When-Then): Given an order whose status is submitted, When order staff receive the order, Then the system sets the status of the order to pending.
- **US-06-AC02** (Given-When-Then): Given an order whose status is not submitted, When order staff attempt to receive the order, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-06-AC03** (Condition): Receiving an order changes its status only from submitted to pending.
- **US-06-AC04** (Condition): Receiving never changes the status of an order whose status is closed.

#### US-07 Mark order filled

As an OrderStaff, I want to mark a pending order as filled once its goods have been assembled, so that it is ready to be shipped and invoiced.

Acceptance criteria:

- **US-07-AC01** (Given-When-Then): Given an order whose status is pending, When order staff mark the order as filled, Then the system sets the status of the order to filled.
- **US-07-AC02** (Given-When-Then): Given an order whose status is not pending, When order staff attempt to mark the order as filled, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-07-AC03** (Condition): Marking an order as filled changes its status only from pending to filled.
- **US-07-AC04** (Condition): Marking an order as filled never changes the status of an order whose status is closed.

#### US-08 Decline order

As an OrderStaff, I want to decline a pending order that cannot be fulfilled, so that it is closed without being shipped or billed.

Acceptance criteria:

- **US-08-AC01** (Given-When-Then): Given an order whose status is pending, When order staff decline the order, Then the system sets the status of the order to closed.
- **US-08-AC02** (Given-When-Then): Given an order whose status is not pending, When order staff attempt to decline the order, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-08-AC03** (Given-When-Then): Given an order that has been declined, When the accountant requests an invoice for that order, Then the system rejects the request and records no invoice.
- **US-08-AC04** (Condition): Declining an order changes its status only from pending to closed.
- **US-08-AC05** (Condition): A declined order keeps the status closed and its status is never changed again.

#### US-09 Ship order

As an OrderStaff, I want to set a filled order to shipped when it leaves for delivery, so that it is known that the goods are on their way to the customer.

Acceptance criteria:

- **US-09-AC01** (Given-When-Then): Given an order whose status is filled, When order staff set the order to shipped, Then the system sets the status of the order to shipped.
- **US-09-AC02** (Given-When-Then): Given an order whose status is not filled, When order staff attempt to set the order to shipped, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-09-AC03** (Given-When-Then): Given an order whose status is filled and that has an invoice, When order staff set the order to shipped, Then the system leaves the status of that invoice and of every payment against it unchanged.
- **US-09-AC04** (Given-When-Then): Given an order whose status is filled and that has no invoice, When order staff set the order to shipped, Then the system sets the status of the order to shipped without requiring an invoice to have been raised.
- **US-09-AC05** (Condition): Shipping an order changes its status only from filled to shipped.
- **US-09-AC06** (Condition): Shipping never changes the status of an order whose status is closed.

#### US-10 Confirm payment

As an Accountant, I want to confirm a pending payment once its money has been received, so that the invoice it settles is recorded as paid.

Acceptance criteria:

- **US-10-AC01** (Given-When-Then): Given a payment whose status is pending, When the accountant confirms the payment, Then the system sets the status of the payment to completed.
- **US-10-AC02** (Given-When-Then): Given a pending payment against an invoice whose status is issued, When the accountant confirms the payment, Then the system sets the status of that invoice to paid.
- **US-10-AC03** (Given-When-Then): Given a pending payment against an invoice that bills an order, When the accountant confirms the payment, Then the system leaves the status of that order unchanged.
- **US-10-AC04** (Given-When-Then): Given a payment whose status is not pending, When the accountant attempts to confirm the payment, Then the system rejects the attempt and leaves the status of the payment unchanged.
- **US-10-AC05** (Condition): Confirming a payment changes the status of the payment only from pending to completed.
- **US-10-AC06** (Condition): Confirming a payment changes the status of its invoice only from issued to paid.

#### US-11 Reject payment

As an Accountant, I want to reject a pending payment whose money has not been received, so that the invoice stays open and the customer can pay it again.

Acceptance criteria:

- **US-11-AC01** (Given-When-Then): Given a payment whose status is pending, When the accountant rejects the payment, Then the system sets the status of the payment to failed.
- **US-11-AC02** (Given-When-Then): Given a pending payment against an invoice that bills an order, When the accountant rejects the payment, Then the system leaves the status of that invoice and of that order unchanged.
- **US-11-AC03** (Given-When-Then): Given a payment whose status is not pending, When the accountant attempts to reject the payment, Then the system rejects the attempt and leaves the status of the payment unchanged.
- **US-11-AC04** (Condition): Rejecting a payment changes its status only from pending to failed.

#### US-12 Close order

As an OrderStaff, I want to close an order once it has been shipped and its invoice has been paid, so that completed orders are separated from those that still need attention.

Acceptance criteria:

- **US-12-AC01** (Given-When-Then): Given an order whose status is shipped and whose invoice has the status paid, When order staff close the order, Then the system sets the status of the order to closed.
- **US-12-AC02** (Given-When-Then): Given an order whose status is shipped and whose invoice does not have the status paid, When order staff attempt to close the order, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-12-AC03** (Given-When-Then): Given an order whose invoice has the status paid and whose status is not shipped, When order staff attempt to close the order, Then the system rejects the attempt and leaves the status of the order unchanged.
- **US-12-AC04** (Condition): A filled order is closed only after both the shipping of the order and the settlement of its invoice have completed, whichever of the two finishes last.
- **US-12-AC05** (Condition): Closing an order changes its status only from shipped to closed.
- **US-12-AC06** (Condition): An order whose status is closed is never changed again.

### 3.2 Quality attributes

The quality attributes are stated as declarative requirements with measurable thresholds. They carry no acceptance criteria; their verification is described in clause 4.

#### 3.2.1 Performance

- **NFR-01**: The system shall register an order containing up to 50 order items and respond to its submission within 2 seconds for at least 95% of submissions under normal operating conditions.
- **NFR-02**: The system shall support at least 200 concurrent users and at least 20 order submissions per second under normal operating conditions while meeting the response time of NFR-01.

#### 3.2.2 Security

- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04**: The system shall allow only users holding the Accountant role to confirm or reject a payment, and shall reject 100% of such requests from users not holding that role.
- **NFR-05**: The system shall encrypt customer personal data and bank account numbers in transit using TLS 1.2 or higher, and shall store them encrypted at rest.
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain each such record for at least 12 months.

#### 3.2.3 Availability

- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08**: The system shall resume accepting requests within 15 minutes after a server failure without losing any order, invoice or payment recorded before the failure.

## 4. Verification

Every requirement of clause 3 is verified, and the result is recorded against its identifier.

- **Functional requirements.** Each acceptance criterion is verified independently, by test. A Given-When-Then criterion is verified by establishing the precondition, performing the trigger as the named role and observing the outcome, including, for every refusal, that the status and the records concerned are unchanged. A Condition criterion is verified by inspection of the stored data and the structural model, and by tests that attempt to violate it: storing an absent mandatory attribute, a value outside the permitted set or a non-decimal amount, exceeding a multiplicity, or requesting a status change that is not permitted. A story is accepted when all of its criteria pass.
- **Performance requirements** are verified by load tests under the normal operating conditions: NFR-01 by measuring the response time of submissions of orders with up to 50 order items and checking the 95th percentile; NFR-02 by sustaining 200 concurrent users and 20 order submissions per second while measuring the same percentile.
- **Security requirements** are verified by test and inspection: NFR-03 by sending requests without valid authentication to every data function and checking that each is rejected; NFR-04 by attempting to confirm and reject payments as Customer and as OrderStaff; NFR-05 by inspecting the negotiated TLS version and the stored data; NFR-06 by performing status changes and inspecting the recorded user and time, and by inspecting the retention configuration.
- **Availability requirements** are verified by analysis of the monthly availability measurements against the announced maintenance windows (NFR-07) and by a failover test that stops a server under load and measures the time until requests are accepted again and the completeness of the recorded orders, invoices and payments (NFR-08).

The requirements specified here are listed in machine-readable form in `requirements.json`. The traceability of every requirement to the domain requirements it originates from, and to the elements of the structural and behavioral models that realize it, is recorded in `VMX.csv`.

## 5. Supporting information

- `structural.puml` is the structural model: the classes Customer, BankAccount, Product, Order, OrderItem, Invoice and Payment with their typed attributes, the enumerations OrderStatus, InvoiceStatus, PaymentStatus and PaymentMethod, and the relationships between the classes with their multiplicities. An order item and a bank account are modelled by composition, because neither has meaning apart from the order or the customer it belongs to; a product is only referred to by order items and exists independently of them.
- `behavioral.puml` is the behavioral model: an activity diagram, partitioned into the swimlanes Customer, OrderStaff and Accountant, of an order from registration of the customer to closure. It shows the decisions with their guards, the parallel shipping and invoicing strands between a fork and a join, the loop in which a customer pays again after a failed payment, and an object node for every status an action leaves an entity in.
- `requirements.json` lists every requirement of clause 3 with its statement and acceptance criteria.
- `VMX.csv` is the traceability matrix.
