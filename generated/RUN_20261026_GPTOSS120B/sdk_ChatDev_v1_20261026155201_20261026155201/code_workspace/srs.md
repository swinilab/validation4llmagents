# Software Requirements Specification (SRS)

## 1. Introduction
### 1.1 Purpose
This document defines the functional and non‑functional requirements for the Order Management System (OMS). It is intended for developers, testers, project managers, and stakeholders.

### 1.2 Scope
The OMS supports customers placing orders, staff processing orders, and accountants handling invoicing and payments. It covers data management, order lifecycle, invoicing, payment processing, and related security and availability constraints.

### 1.3 Definitions and acronyms
- **Customer** – end‑user who browses products and submits orders.
- **OrderStaff** – internal employee who receives, validates and fulfills orders.
- **Accountant** – internal employee who creates invoices and records payments.
- **OMS** – Order Management System.
- **DTO** – Data Transfer Object.
- **TLS** – Transport Layer Security.

## 2. Overall description
### 2.1 Product perspective
The OMS is a standalone web‑based application that persists its data in a relational database. It interacts with external payment gateways via secure APIs.

### 2.2 Product functions
- Manage customers, products, orders, invoices and payments.
- Enforce business rules for order lifecycle and invoicing.
- Provide role‑based access control.

### 2.3 User characteristics
- **Customer** – basic web user, able to browse and place orders.
- **OrderStaff** – staff member with permissions to modify order status.
- **Accountant** – staff member with permissions to create invoices and process payments.

### 2.4 Assumptions and dependencies
- The system runs on a modern server stack supporting Python 3.11.
- TLS 1.2+ is available for encrypted communication.
- A relational database (e.g., PostgreSQL) is provisioned.

## 3. Requirements
### 3.1 Functional requirements
| ID | User story |
|----|------------|
| **US-01** | As a **Customer**, I want my personal details (name, address, phone) stored, so that the system can uniquely identify me. |
| **US-02** | As a **Customer**, I want to optionally add a single bank account, so that I can use it for payments. |
| **US-03** | As an **OrderStaff**, I want to maintain product information (name, description, price, image), so that customers can view accurate product data. |
| **US-04** | As a **Customer**, I want to submit an order that references existing products, includes at least one order item, and specifies a payment method, so that I can purchase items. |
| **US-05** | As an **OrderStaff**, I want to change an order’s status according to the allowed workflow, so that the order proceeds through the correct lifecycle. |
| **US-06** | As an **Accountant**, I want to raise a single invoice for a filled or shipped order, so that the customer can be billed. |
| **US-07** | As a **Customer**, I want to submit a payment against an issued invoice, so that I can settle my bill. |
| **US-08** | As an **Accountant**, I want to confirm or reject a pending payment, so that the invoice status reflects the payment outcome. |
| **US-09** | As an **OrderStaff**, I want to close a shipped order whose invoice is paid, so that the order lifecycle ends. |
| **US-10** | As the **system**, I want to enforce data‑integrity rules (mandatory attributes, multiplicities, decimal types, enumerated values), so that the data remains consistent. |

#### Acceptance criteria

**US-01 – As a Customer, I want my personal details stored**
- **US-01-AC01** (condition): Customer name, address and phone number are mandatory and stored as non‑empty strings.
- **US-01-AC02** (condition): The system rejects creation of a customer record when any mandatory attribute is missing.
- **US-01-AC03** (given_when_then): Given a valid customer input, When the customer is created, Then the record persists with the provided attributes.

**US-02 – As a Customer, I want to optionally add a single bank account**
- **US-02-AC01** (condition): A customer may have zero or one bank account; attempts to add a second bank account are rejected.
- **US-02-AC02** (condition): Bank account data is stored encrypted at rest and in transit.
- **US-02-AC03** (given_when_then): Given a customer without a bank account, When the customer adds a bank account, Then the account is linked to the customer.

**US-03 – As an OrderStaff, I want to maintain product information**
- **US-03-AC01** (condition): Product name, description, price and image are mandatory; price is a decimal number.
- **US-03-AC02** (condition): The system rejects creation of a product when any mandatory attribute is missing.
- **US-03-AC03** (given_when_then): Given valid product data, When the product is saved, Then it is persisted and can be referenced by order items.

**US-04 – As a Customer, I want to submit an order**
- **US-04-AC01** (given_when_then): Given a known customer, at least one order item referencing existing products, and a valid payment method, When the order is submitted, Then the system creates an order with status *submitted*, order date set to the submission time, and total amount calculated as Σ(quantity × unit price).
- **US-04-AC02** (given_when_then): Given an unknown customer, When the order is submitted, Then the system rejects the submission and no order is created.
- **US-04-AC03** (given_when_then): Given an order with zero items, When the order is submitted, Then the system rejects the submission and no order is created.
- **US-04-AC04** (given_when_then): Given an order item referencing a non‑existent product, When the order is submitted, Then the system rejects the submission and no order is created.
- **US-04-AC05** (condition): Payment method on the order is restricted to *bank*, *card*, or *cash*.

**US-05 – As an OrderStaff, I want to change an order’s status**
- **US-05-AC01** (given_when_then): Given an order with status *submitted*, When the staff receives the order, Then the status changes to *pending*.
- **US-05-AC02** (given_when_then): Given an order with status *submitted*, When the staff attempts to receive it, Then the system rejects the request and the status remains *submitted*.
- **US-05-AC03** (given_when_then): Given an order with status *pending*, When the staff marks it as *filled*, Then the status changes to *filled*.
- **US-05-AC04** (given_when_then): Given an order with status *pending*, When the staff attempts to mark it as *filled*, Then the system rejects the request and the status remains *pending*.
- **US-05-AC05** (given_when_then): Given an order with status *pending*, When the staff declines the order, Then the status changes to *closed*.
- **US-05-AC06** (given_when_then): Given an order with status *filled*, When the staff ships the order, Then the status changes to *shipped*.
- **US-05-AC07** (given_when_then): Given an order with status *shipped* whose invoice is not *paid*, When the staff attempts to close the order, Then the system rejects the request and the status remains *shipped*.
- **US-05-AC08** (condition): Order status may only transition as follows: submitted → pending → filled → shipped → closed; or submitted → pending → closed.

**US-06 – As an Accountant, I want to raise a single invoice**
- **US-06-AC01** (given_when_then): Given a filled or shipped order without an existing invoice, When the accountant raises an invoice, Then an invoice is created with status *issued*, the supplied date, amount, and payment method.
- **US-06-AC02** (given_when_then): Given an order that already has an invoice, When the accountant attempts to raise another invoice, Then the system rejects the request.
- **US-06-AC03** (given_when_then): Given an order with status *submitted*, *pending* or *closed*, When the accountant attempts to raise an invoice, Then the system rejects the request.
- **US-06-AC04** (condition): Payment method on an invoice is limited to *bank*, *card*, or *cash*.

**US-07 – As a Customer, I want to submit a payment**
- **US-07-AC01** (given_when_then): Given an invoice with status *issued*, When the customer submits a payment with a valid payment method, Then a payment record is created with status *pending*.
- **US-07-AC02** (given_when_then): Given an invoice with status *paid*, When the customer attempts to submit a payment, Then the system rejects the request.
- **US-07-AC03** (given_when_then): Given an invoice whose previous payment has status *failed*, When the customer submits a new payment, Then the new payment is created with status *pending* and the failed payment remains *failed*.

**US-08 – As an Accountant, I want to confirm or reject a pending payment**
- **US-08-AC01** (given_when_then): Given a payment with status *pending*, When the accountant confirms it, Then the payment status becomes *completed* and the related invoice status changes to *paid*.
- **US-08-AC02** (given_when_then): Given a payment with status *pending*, When the accountant rejects it, Then the payment status becomes *failed* and the invoice and order statuses remain unchanged.
- **US-08-AC03** (given_when_then): Given a payment whose status is not *pending*, When the accountant attempts to confirm or reject it, Then the system rejects the request and the status remains unchanged.

**US-09 – As an OrderStaff, I want to close a shipped order whose invoice is paid**
- **US-09-AC01** (given_when_then): Given a shipped order whose associated invoice has status *paid*, When the staff closes the order, Then the order status becomes *closed*.
- **US-09-AC02** (given_when_then): Given a shipped order whose invoice is not *paid*, When the staff attempts to close the order, Then the system rejects the request and the order status remains *shipped*.
- **US-09-AC03** (condition): Once an order reaches status *closed*, no further status changes are allowed.

**US-10 – As the system, I want to enforce data‑integrity rules**
- **US-10-AC01** (condition): All monetary values (product price, unit price, order total, invoice amount, payment amount) are stored as decimal numbers.
- **US-10-AC02** (condition): Order status is restricted to the enum values *submitted*, *pending*, *filled*, *shipped*, *closed*.
- **US-10-AC03** (condition): Invoice status is restricted to *issued* or *paid*.
- **US-10-AC04** (condition): Payment status is restricted to *pending*, *completed*, or *failed*.
- **US-10-AC05** (condition): Payment method on orders, invoices and payments is limited to *bank*, *card*, or *cash*.

### 3.2 Quality attributes
#### 3.2.1 Performance
- **NFR-01**: When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions.
- **NFR-02**: Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time of NFR‑01.

#### 3.2.2 Security
- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04**: The system shall allow only users holding the accountant role to confirm or reject a payment, and shall reject the same request from any other user.
- **NFR-05**: The system shall protect customer personal data and bank account numbers by encrypting them in transit with TLS 1.2 or higher and at rest.
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least 12 months.

#### 3.2.3 Availability
- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08**: When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure.

## 4. Verification
Verification methods include unit tests, integration tests, performance load testing, security penetration testing, and automated compliance audits against the acceptance criteria defined above.

## 5. Supporting information
- Structural diagram: `structural.puml`
- Behavioral diagram: `behavioral.puml`
- Requirements listing: `requirements.json`
- Traceability matrix: `VMX.csv`
