# 1. Introduction

## 1.1 Purpose
The purpose of this Software Requirements Specification (SRS) is to define, in a complete and verifiable way, the functional and non‑functional requirements for the **Order Management System (OMS)**. The OMS supports customers, order staff and accountants in managing customers, products, orders, invoices and payments.

## 1.2 Scope
The OMS enables:
* Management of customer records (including optional bank account).
* Management of product catalog.
* Creation, processing and fulfilment of orders.
* Generation of invoices and handling of payments.
* Role‑based access control, audit logging and data protection.

## 1.3 Definitions and acronyms
* **Customer** – end‑user who purchases items.
* **OrderStaff** – internal staff that processes orders.
* **Accountant** – internal staff that creates invoices and handles payments.
* **Order** – a collection of order items submitted by a customer.
* **Invoice** – a billing document linked to a single order.
* **Payment** – a monetary transaction linked to an invoice.
* **TLS** – Transport Layer Security.

# 2. Overall description

## 2.1 Product perspective
The OMS is a standalone web‑based application that persists data in a relational database and exposes RESTful services to front‑end clients.

## 2.2 Product functions
* Customer registration and optional bank‑account registration.
* Product catalog maintenance (view‑only for customers).
* Order submission, validation, status transitions (submitted → pending → filled → shipped → closed).
* Invoice creation (issued → paid) and payment handling (pending → completed/failed).
* Role‑based authentication and audit logging.

## 2.3 User characteristics
* **Customers** are external users with basic web browsing capabilities.
* **OrderStaff** are internal employees with privileges to change order status.
* **Accountants** are internal employees with privileges to manage invoices and payments.

## 2.4 Assumptions and dependencies
* The system runs on a server that supports Python 3.12 and a PostgreSQL database.
* TLS 1.2+ is available for encrypted communication.

# 3. Requirements

## 3.1 Functional requirements

| ID | Requirement |
|----|-------------|
| **US-01** | As a **Customer**, I want to register my personal details (name, address, phone), so that the system can uniquely identify me. |
| **US-02** | As a **Customer**, I want to optionally add a bank account, so that I can use it as a payment method. |
| **US-03** | As a **Customer**, I want to view product information (name, description, price, image), so that I can decide what to buy. |
| **US-04** | As a **Customer**, I want to submit an order that contains one or more order items, each referencing an existing product and a payment method, so that I can purchase the items. |
| **US-05** | As **OrderStaff**, I want to receive a submitted order and set its status to *pending*, so that the order enters the processing workflow. |
| **US-06** | As **OrderStaff**, I want to mark a *pending* order as *filled*, so that it is ready for shipping. |
| **US-07** | As **OrderStaff**, I want to ship a *filled* order, so that it is dispatched to the customer. |
| **US-08** | As **OrderStaff**, I want to decline a *pending* order, so that it is closed without further processing. |
| **US-09** | As **OrderStaff**, I want to close a *shipped* order whose invoice is *paid*, so that the transaction is completed. |
| **US-10** | As an **Accountant**, I want to raise an invoice for a *filled* or *shipped* order that has no invoice, so that the customer can be billed. |
| **US-11** | As a **Customer**, I want to submit a payment against an *issued* invoice, so that the invoice can be settled. |
| **US-12** | As an **Accountant**, I want to confirm a *pending* payment, so that the related invoice becomes *paid*. |
| **US-13** | As an **Accountant**, I want to reject a *pending* payment, so that the failure is recorded and the invoice remains unchanged. |

### Acceptance criteria

#### US‑01
* **US-01-AC01** – `condition` – All of name, address and phone must be provided and non‑empty.
* **US-01-AC02** – `condition` – The system assigns a unique identifier to each customer record.
* **US-01-AC03** – `given_when_then` – Given a registration request, when the data passes validation, then the system stores the customer and returns a success response.

#### US‑02
* **US-02-AC01** – `condition` – A bank account may be associated with a customer at most once.
* **US-02-AC02** – `given_when_then` – Given a customer who has no bank account, when the customer adds a bank account, then the system stores the account and links it to the customer.
* **US-02-AC03** – `condition` – The bank‑account field is optional; the customer record remains valid without it.

#### US‑03
* **US-03-AC01** – `condition` – Each product must have name, description, price and image URL; all are mandatory.
* **US-03-AC02** – `condition` – Product price is stored as a decimal number.
* **US-03-AC03** – `given_when_then` – Given a request to view the catalog, when the request is authenticated, then the system returns the list of products with the required attributes.

#### US‑04
* **US-04-AC01** – `given_when_then` – Given a known customer, when the customer submits an order containing at least one order item that references existing products and a valid payment method, then the system creates an order with status *submitted*, order‑date = submission date, and total‑amount = Σ(quantity × unitPrice).
* **US-04-AC02** – `given_when_then` – Given an unknown customer, when the customer attempts to submit an order, then the system rejects the submission and no order is recorded.
* **US-04-AC03** – `condition` – An order must contain at least one order item; otherwise the submission is rejected.
* **US-04-AC04** – `condition` – All referenced products must exist; otherwise the submission is rejected.

#### US‑05
* **US-05-AC01** – `given_when_then` – Given an order with status *submitted*, when OrderStaff receives the order, then the system changes the status to *pending*.
* **US-05-AC02** – `condition` – The status transition *submitted → pending* is allowed; any other transition is rejected.
* **US-05-AC03** – `condition` – The order’s status cannot be changed after it reaches *closed*.

#### US‑06
* **US-06-AC01** – `given_when_then` – Given a *pending* order, when OrderStaff marks it as *filled*, then the system changes the status to *filled*.
* **US-06-AC02** – `condition` – The status transition *pending → filled* is allowed; any other transition is rejected.
* **US-06-AC03** – `condition` – When an order becomes *filled*, its order items remain attached (composition).

#### US‑07
* **US-07-AC01** – `given_when_then` – Given a *filled* order, when OrderStaff ships the order, then the system changes the status to *shipped*.
* **US-07-AC02** – `condition` – The status transition *filled → shipped* is allowed; any other transition is rejected.
* **US-07-AC03** – `condition` – Shipping does not alter the status of any associated invoice or payment.

#### US‑08
* **US-08-AC01** – `given_when_then` – Given a *pending* order, when OrderStaff declines it, then the system changes the status to *closed*.
* **US-08-AC02** – `condition` – The status transition *pending → closed* is allowed; any other transition is rejected.
* **US-08-AC03** – `condition` – A declined order cannot later have an invoice raised.

#### US‑09
* **US-09-AC01** – `given_when_then` – Given a *shipped* order whose linked invoice has status *paid*, when OrderStaff closes the order, then the system changes the order status to *closed*.
* **US-09-AC02** – `condition` – The system rejects an attempt to close a *shipped* order whose invoice is not *paid*.
* **US-09-AC03** – `condition` – Once an order is *closed* its status cannot be changed further.

#### US‑10
* **US-10-AC01** – `given_when_then` – Given a *filled* (or *shipped*) order with no invoice, when Accountant raises an invoice with date, amount, payment method and status *issued*, then the system creates the invoice linked to the order.
* **US-10-AC02** – `condition` – An order can have at most one invoice; a second attempt is rejected.
* **US-10-AC03** – `condition` – Invoices can be raised only when the order status is *filled* or *shipped*.

#### US‑11
* **US-11-AC01** – `given_when_then` – Given an *issued* invoice, when a Customer submits a payment with date, amount and payment method, then the system creates a payment with status *pending* linked to the invoice.
* **US-11-AC02** – `condition` – Payments cannot be submitted against an invoice whose status is *paid*.
* **US-11-AC03** – `condition` – The system permits multiple payments per invoice; each payment is recorded separately.

#### US‑12
* **US-12-AC01** – `given_when_then` – Given a *pending* payment, when Accountant confirms it, then the system changes the payment status to *completed* and sets the linked invoice status to *paid*.
* **US-12-AC02** – `condition` – The status transition *pending → completed* is allowed; any other transition is rejected.
* **US-12-AC03** – `condition` – Confirming a payment does not alter the status of the associated order.

#### US‑13
* **US-13-AC01** – `given_when_then` – Given a *pending* payment, when Accountant rejects it, then the system changes the payment status to *failed* and leaves the invoice and order statuses unchanged.
* **US-13-AC02** – `condition` – The status transition *pending → failed* is allowed; any other transition is rejected.
* **US-13-AC03** – `condition` – After a payment is *failed*, further payments may be submitted (see US‑11).

### Traceability
All functional requirements are traced to the original domain requirements in **VMX.csv** and are realized by elements in **structural.puml** and **behavioral.puml**.

## 3.2 Quality attributes

### 3.2.1 Performance

* **NFR-01** – The system shall register an order containing up to 50 order items and respond within 2 seconds for at least 95 % of submissions (REQ‑N‑01).
* **NFR-02** – The system shall support at least 200 concurrent users and process at least 20 order submissions per second while meeting the response time of NFR‑01 (REQ‑N‑02).

### 3.2.2 Security

* **NFR-03** – The system shall authenticate every user before granting access to any customer, order, invoice or payment data and shall reject 100 % of unauthenticated requests (REQ‑N‑05).
* **NFR-04** – The system shall allow only users holding the accountant role to confirm or reject a payment and shall reject the same request from any other user (REQ‑N‑06).
* **NFR-05** – The system shall protect customer personal data and bank‑account numbers by encrypting them in transit with TLS 1.2 or higher and at rest (REQ‑N‑07).

### 3.2.3 Availability

* **NFR-06** – The system shall be available for at least 99.5 % of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance (REQ‑N‑03).
* **NFR-07** – When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure (REQ‑N‑04).

# 4. Verification
Each functional requirement shall be verified by automated acceptance‑test scripts that implement the listed acceptance criteria. Non‑functional requirements shall be verified by performance‑testing tools, security‑audit scans and availability monitoring dashboards.

# 5. Supporting information
* Glossary of terms (Section 1.3).
* UML diagrams (see **structural.puml** and **behavioral.puml**).
* Traceability matrix (**VMX.csv**).
* Machine‑readable requirement listing (**requirements.json**).