# Software Requirements Specification (SRS)

## 1. Introduction
### 1.1 Purpose
This document specifies the functional and non‑functional requirements for the Order Management System.

### 1.2 Scope
The system enables Customers to browse products, place orders, make payments, and view invoices; OrderStaff to process orders; and Accountants to manage invoicing and payments.

### 1.3 Definitions and acronyms
- **Customer**: End‑user who purchases products.
- **OrderStaff**: Internal staff handling order processing.
- **Accountant**: Internal staff handling invoicing and payments.
- **Order**, **Invoice**, **Payment**, **Product**, **BankAccount**: Domain entities.

## 2. Overall description
### 2.1 Product perspective
The system is a standalone application interfacing with a relational database and exposing a REST API.

### 2.2 Product functions
- Manage customer records.
- Manage product catalogue.
- Process order lifecycle (submission → receipt → fulfillment → shipping → closure).
- Generate invoices and record payments.

### 2.3 User characteristics
- Customers: basic web users, authenticated.
- OrderStaff: staff with order‑processing privileges.
- Accountant: staff with invoicing and payment privileges.

### 2.4 Assumptions and dependencies
- TLS 1.2+ is available for secure communication.
- The database supports decimal types.

## 3. Requirements
### 3.1 Functional requirements
#### US-01
*As a **Customer**, I want to create and maintain my personal profile, so that the system can identify me and contact me when needed.*
- **US-01-AC01** (condition): The profile shall store a name, an address and a phone number (REQ‑F‑01) and may store at most one bank account (REQ‑F‑02).
- **US-01-AC02** (condition): All stored attributes are mandatory except the bank account (REQ‑F‑45).
- **US-01-AC03** (given_when_then): Given a new profile request with all mandatory fields, when the system validates the data, then the profile is created and a confirmation is returned.

#### US-02
*As an **OrderStaff**, I want to add new products to the catalogue, so that customers can order them.*
- **US-02-AC01** (condition): Each product shall have a name, description, price and image (REQ‑F‑03) stored as decimal for price (REQ‑F‑46).
- **US-02-AC02** (condition): All product attributes are mandatory (REQ‑F‑45).
- **US-02-AC03** (given_when_then): Given a product creation request with valid data, when the system stores the product, then the product becomes available for order items.

#### US-03
*As a **Customer**, I want to submit an order containing one or more items and a payment method, so that I can purchase products.*
- **US-03-AC01** (condition): An order shall reference exactly one known customer (REQ‑F‑08) and contain at least one order item (REQ‑F‑15).
- **US-03-AC02** (condition): Every order item shall refer to an existing product (REQ‑F‑16) and store quantity, unit price and a reference to exactly one product (REQ‑F‑06).
- **US-03-AC03** (given_when_then): Given a valid order submission, when the system records the order date as the submission date and computes the total amount as Σ(quantity × unit price) (REQ‑F‑17), then the order status is set to *submitted*.
- **US-03-AC04** (given_when_then): Given an order submission where the customer is unknown, when the system validates the request, then the order is rejected and no record is created (REQ‑F‑14).
- **US-03-AC05** (given_when_then): Given an order submission containing a non‑existent product, when the system validates the items, then the order is rejected and no record is created (REQ‑F‑16).

#### US-04
*As an **OrderStaff**, I want to receive a submitted order, so that it can be processed further.*
- **US-04-AC01** (condition): The status of an order may change from *submitted* to *pending* only (REQ‑F‑49).
- **US-04-AC02** (given_when_then): Given an order with status *submitted*, when OrderStaff selects “receive”, then the order status becomes *pending* (REQ‑F‑18).
- **US-04-AC03** (given_when_then): Given an order whose status is not *submitted*, when OrderStaff attempts to receive it, then the request is rejected and the status remains unchanged (REQ‑F‑19).

#### US-05
*As an **OrderStaff**, I want to mark a pending order as filled, so that the items can be prepared for shipping.*
- **US-05-AC01** (condition): Status may change from *pending* to *filled* (REQ‑F‑49).
- **US-05-AC02** (given_when_then): Given a *pending* order, when OrderStaff selects “fill”, then the order status becomes *filled* (REQ‑F‑20).
- **US-05-AC03** (given_when_then): Given an order whose status is not *pending*, when OrderStaff attempts to fill it, then the request is rejected and the status stays unchanged (REQ‑F‑21).

#### US-06
*As an **OrderStaff**, I want to decline a pending order, so that it does not proceed to fulfillment.*
- **US-06-AC01** (condition): Status may change from *pending* to *closed* (REQ‑F‑49).
- **US-06-AC02** (given_when_then): Given a *pending* order, when OrderStaff selects “decline”, then the order status becomes *closed* (REQ‑F‑22).
- **US-06-AC03** (given_when_then): Given an order not in *pending* status, when OrderStaff attempts to decline it, then the request is rejected and the status remains unchanged (REQ‑F‑23).

#### US-07
*As an **OrderStaff**, I want to ship a filled order, so that the customer receives the goods.*
- **US-07-AC01** (condition): Status may change from *filled* to *shipped* (REQ‑F‑49).
- **US-07-AC02** (given_when_then): Given a *filled* order, when OrderStaff selects “ship”, then the order status becomes *shipped* (REQ‑F‑25).
- **US-07-AC03** (given_when_then): Given an order whose status is not *filled*, when OrderStaff attempts to ship it, then the request is rejected and the status stays unchanged (REQ‑F‑26).

#### US-08
*As an **Accountant**, I want to raise an invoice for a filled or shipped order that has no invoice, so that the customer can be billed.*
- **US-08-AC01** (condition): An invoice may be created only for orders with status *filled* or *shipped* (REQ‑F‑28) and only if the order does not already have an invoice (REQ‑F‑29).
- **US-08-AC02** (condition): Invoice status is initially *issued* (REQ‑F‑28) and may change only to *paid* (REQ‑F‑50).
- **US-08-AC03** (given_when_then): Given an eligible order, when Accountant creates the invoice with date, amount, payment method, then the invoice is linked to the order and its status is *issued*.
- **US-08-AC04** (given_when_then): Given an order that is *declined*, when Accountant attempts to raise an invoice, then the request is rejected (REQ‑F‑24).
- **US-08-AC05** (given_when_then): Given an order whose status is *submitted*, *pending* or *closed*, when Accountant attempts to raise an invoice, then the request is rejected (REQ‑F‑30).

#### US-09
*As an **Accountant**, I want to record a payment against an issued invoice, so that the invoice can be settled.*
- **US-09-AC01** (condition): Payments may be recorded only against invoices with status *issued* (REQ‑F‑32) and the payment status starts as *pending* (REQ‑F‑35).
- **US-09-AC02** (given_when_then): Given an invoice with status *issued*, when Accountant records a payment with date, amount and method, then a payment entity is created with status *pending*.
- **US-09-AC03** (given_when_then): Given an invoice with status *paid*, when a payment is submitted, then the request is rejected (REQ‑F‑33).
- **US-09-AC04** (given_when_then): Given a failed payment, when a further payment is submitted, then the new payment is created with status *pending* while the failed one remains *failed* (REQ‑F‑34).
- **US-09-AC05** (given_when_then): Given a *pending* payment, when Accountant confirms it, then the payment status becomes *completed* (REQ‑F‑35) and the invoice status becomes *paid* (REQ‑F‑36).
- **US-09-AC06** (given_when_then): Given a *pending* payment, when Accountant rejects it, then the payment status becomes *failed* (REQ‑F‑38) and invoice and order statuses remain unchanged.
- **US-09-AC07** (condition): Payment status may change only from *pending* to *completed* or *failed* (REQ‑F‑50).

#### US-10
*As an **OrderStaff**, I want to close a shipped order whose invoice is paid, so that the order lifecycle is finished.*
- **US-10-AC01** (condition): An order may change from *shipped* to *closed* only when its linked invoice status is *paid* (REQ‑F‑40).
- **US-10-AC02** (given_when_then): Given a *shipped* order with a *paid* invoice, when OrderStaff selects “close”, then the order status becomes *closed* (REQ‑F‑40).
- **US-10-AC03** (given_when_then): Given a *shipped* order whose invoice is not *paid*, when OrderStaff attempts to close it, then the request is rejected and the status stays unchanged (REQ‑F‑41).
- **US-10-AC04** (given_when_then): Given an order whose invoice is *paid* but whose status is not *shipped*, when OrderStaff attempts to close it, then the request is rejected (REQ‑F‑42).
- **US-10-AC05** (condition): Once an order reaches status *closed* it never changes again (REQ‑F‑44).

### 3.2 Quality attributes
#### 3.2.1 Performance
- **NFR-01**: When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions. (REQ‑N‑01)
- **NFR-02**: Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time of REQ‑N‑01. (REQ‑N‑02)

#### 3.2.2 Security
- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests. (REQ‑N‑05)
- **NFR-04**: The system shall allow only users holding the accountant role to confirm or reject a payment, and shall reject the same request from any other user. (REQ‑N‑06)
- **NFR-05**: The system shall protect customer personal data and bank account numbers by encrypting them in transit with TLS 1.2 or higher and at rest. (REQ‑N‑07)
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least 12 months. (REQ‑N‑08)

#### 3.2.3 Availability
- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance. (REQ‑N‑03)
- **NFR-08**: When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure. (REQ‑N‑04)

## 4. Verification
Verification methods include unit testing, integration testing, performance testing, security testing and audit of audit‑trail logs.

## 5. Supporting information
Appendices, glossary, and reference documents.

## 1.1 Purpose

The purpose of this Software Requirements Specification (SRS) is to define, in a complete and verifiable manner, the functional and non‑functional requirements for an Order Management System (OMS). The SRS is intended for the development team, quality assurance, and stakeholders.

## 1.2 Scope

The OMS enables customers to browse products, place orders, and make payments; order staff to receive, validate, fulfill, ship, and close orders; and accountants to raise invoices and confirm or reject payments. The system records all business entities (customers, products, orders, invoices, payments) and enforces the business rules described in the domain requirements.

## 1.3 Definitions and acronyms

- **OMS** – Order Management System
- **DTO** – Data Transfer Object
- **TLS** – Transport Layer Security
- **NFR** – Non‑Functional Requirement
- **FR** – Functional Requirement
- **US** – User Story (functional requirement identifier)
- **NFR‑xx** – Non‑functional requirement identifier

# 2. Overall description

## 2.1 Product perspective

The OMS is a standalone web‑based application that stores its data in a relational database. It interacts with external payment gateways via secure APIs and provides role‑based access to three user categories: Customer, OrderStaff, and Accountant.

## 2.2 Product functions

- Manage customers and their optional bank accounts.
- Manage product catalogue.
- Allow customers to submit orders composed of one or more order items.
- Enable order staff to receive, fill, decline, ship, and close orders.
- Enable accountants to raise invoices, record payments, and confirm or reject payments.
- Enforce business rules for status transitions, monetary values, and payment methods.

## 2.3 User characteristics

- **Customer** – end‑users with basic internet browsing skills.
- **OrderStaff** – internal staff trained in order processing.
- **Accountant** – internal staff with authority to handle invoicing and payments.

## 2.4 Assumptions and dependencies

- The system runs on a server that supports Python 3.11 and a PostgreSQL database.
- TLS 1.2 or higher is available for all network communication.
- External payment gateways provide reliable APIs for payment processing.

# 3. Requirements

## 3.1 Functional requirements

### US-01
> As a **Customer**, I want to create and maintain my personal profile with name, address, phone number, and an optional bank account, so that the system can identify me and optionally store my payment details.

- **US-01-AC01** (given_when_then): Given a logged‑in Customer, when they submit a profile containing name, address, and phone number (bank account optional), then the system stores the profile.
- **US-01-AC02** (condition): The system rejects the profile creation if any mandatory attribute (name, address, phone) is missing.
- **US-01-AC03** (condition): The bank account attribute may be null; all other attributes must be non‑null.

### US-02
> As a **OrderStaff**, I want to create and maintain product records with name, description, price, and image, so that customers can browse and order the correct items.

- **US-02-AC01** (given_when_then): Given an OrderStaff, when they submit a product with name, description, price, and image, then the product is stored.
- **US-02-AC02** (condition): The system rejects the product if any mandatory attribute is missing.
- **US-02-AC03** (condition): The price attribute is stored as a decimal number.

### US-03
> As a **Customer**, I want to submit an order that references existing products, includes quantities and unit prices, and specifies a payment method, so that the order can be processed by the business.

- **US-03-AC01** (given_when_then): Given a known Customer, when they submit an order containing at least one order item that references an existing product, then the system creates the order with status *submitted* and records the submission date.
- **US-03-AC02** (given_when_then): Given an unknown Customer, when they attempt to submit an order, then the system rejects the submission and no order is created.
- **US-03-AC03** (given_when_then): Given an order with no order items, when it is submitted, then the system rejects the submission and no order is created.
- **US-03-AC04** (given_when_then): Given an order item that references a non‑existent product, when the order is submitted, then the system rejects the submission and no order is created.
- **US-03-AC05** (condition): The total amount of the order equals the sum of *quantity × unit price* for all its order items.
- **US-03-AC06** (condition): The order status may only be one of *submitted, pending, filled, shipped, closed*.
- **US-03-AC07** (condition): The payment method recorded on the order is limited to *bank, card, cash*.

### US-04
> As an **OrderStaff**, I want to receive a submitted order, so that it moves to the pending state and can be processed further.

- **US-04-AC01** (given_when_then): Given an Order in status *submitted*, when OrderStaff invokes *receive*, then the order status changes to *pending*.
- **US-04-AC02** (given_when_then): Given an Order whose status is not *submitted*, when OrderStaff invokes *receive*, then the system rejects the operation and the status remains unchanged.
- **US-04-AC03** (condition): The status transition *submitted → pending* is the only allowed transition for this action.

### US-05
> As an **OrderStaff**, I want to mark a pending order as filled, so that it can be prepared for shipping.

- **US-05-AC01** (given_when_then): Given an Order in status *pending*, when OrderStaff marks it as *filled*, then the status becomes *filled*.
- **US-05-AC02** (given_when_then): Given an Order not in *pending* status, when OrderStaff attempts to mark it as *filled*, then the operation is rejected and the status stays unchanged.
- **US-05-AC03** (condition): The status transition *pending → filled* is allowed; no other transition is permitted by this action.

### US-06
> As an **OrderStaff**, I want to decline a pending order, so that it is closed without further processing.

- **US-06-AC01** (given_when_then): Given an Order in status *pending*, when OrderStaff declines it, then the status changes to *closed*.
- **US-06-AC02** (given_when_then): Given an Order not in *pending* status, when OrderStaff attempts to decline it, then the operation is rejected and the status remains unchanged.
- **US-06-AC03** (condition): The status transition *pending → closed* is allowed only via the decline action.

### US-07
> As an **OrderStaff**, I want to ship a filled order, so that the customer receives the goods.

- **US-07-AC01** (given_when_then): Given an Order in status *filled*, when OrderStaff sets it to *shipped*, then the status becomes *shipped*.
- **US-07-AC02** (given_when_then): Given an Order not in *filled* status, when OrderStaff attempts to set it to *shipped*, then the operation is rejected and the status stays unchanged.
- **US-07-AC03** (condition): The status transition *filled → shipped* is the only allowed transition for shipping.

### US-08
> As an **Accountant**, I want to raise an invoice for a filled or shipped order that has no existing invoice, so that the order can be billed.

- **US-08-AC01** (given_when_then): Given an Order in status *filled* or *shipped* without an invoice, when Accountant creates an invoice with date, amount, payment method, and status *issued*, then the invoice is stored and linked to the order.
- **US-08-AC02** (given_when_then): Given an Order that already has an invoice, when Accountant attempts to raise another invoice, then the system rejects the request.
- **US-08-AC03** (given_when_then): Given an Order whose status is *submitted*, *pending*, or *closed*, when Accountant attempts to raise an invoice, then the request is rejected.
- **US-08-AC04** (condition): The invoice status may only be *issued* or *paid*.
- **US-08-AC05** (condition): The payment method on the invoice is limited to *bank, card, cash*.

### US-09
> As a **Customer**, I want to submit a payment against an issued invoice, so that the invoice can be settled.

- **US-09-AC01** (given_when_then): Given an Invoice in status *issued*, when the Customer submits a payment with date, amount, and payment method, then the payment is recorded with status *pending*.
- **US-09-AC02** (given_when_then): Given an Invoice in status *paid*, when the Customer attempts to submit a payment, then the system rejects the submission.
- **US-09-AC03** (given_when_then): Given a previously *failed* payment on an invoice, when the Customer submits a new payment, then the new payment is recorded as *pending* while the failed one remains *failed*.
- **US-09-AC04** (condition): The payment method is limited to *bank, card, cash*.
- **US-09-AC05** (condition): The payment amount is stored as a decimal number.

### US-10
> As an **Accountant**, I want to confirm or reject pending payments, so that the invoice and order statuses reflect the true financial state.

- **US-10-AC01** (given_when_then): Given a Payment in status *pending*, when Accountant confirms it, then the payment status becomes *completed* and the related Invoice status changes to *paid*.
- **US-10-AC02** (given_when_then): Given a Payment in status *pending*, when Accountant rejects it, then the payment status becomes *failed* and the Invoice and Order statuses remain unchanged.
- **US-10-AC03** (given_when_then): Given a Payment whose status is not *pending*, when Accountant attempts to confirm or reject it, then the operation is rejected and the status stays unchanged.
- **US-10-AC04** (condition): The payment status may only transition from *pending* to *completed* or *failed*.
- **US-10-AC05** (condition): The invoice status may only transition from *issued* to *paid*.

### US-11
> As an **OrderStaff**, I want to close a shipped order whose invoice is paid, so that the order lifecycle ends.

- **US-11-AC01** (given_when_then): Given an Order in status *shipped* whose linked Invoice is in status *paid*, when OrderStaff closes the order, then the order status becomes *closed*.
- **US-11-AC02** (given_when_then): Given a *shipped* order whose invoice is not *paid*, when OrderStaff attempts to close it, then the operation is rejected and the status remains *shipped*.
- **US-11-AC03** (given_when_then): Given an order whose invoice is *paid* but whose status is not *shipped*, when OrderStaff attempts to close it, then the operation is rejected.
- **US-11-AC04** (condition): An order whose status is *closed* cannot have its status changed thereafter.
- **US-11-AC05** (condition): The system records the timestamp and user for every status change (audit requirement).

## 3.2 Quality attributes

### 3.2.1 Performance

- **NFR-01**: When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions.
- **NFR-02**: Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time of NFR‑01.

### 3.2.2 Security

- **NFR-03**: The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **NFR-04**: The system shall allow only users holding the accountant role to confirm or reject a payment, and shall reject the same request from any other user.
- **NFR-05**: The system shall protect customer personal data and bank account numbers by encrypting them in transit with TLS 1.2 or higher and at rest.
- **NFR-06**: The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least 12 months.

### 3.2.3 Availability

- **NFR-07**: The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **NFR-08**: When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure.

# 4. Verification

Verification of each functional requirement will be performed by executing the acceptance criteria defined for the corresponding user story. Non‑functional requirements will be verified through load‑testing, security‑testing, and availability monitoring as described in the test plan.

# 5. Supporting information

- Structural model: see **structural.puml**.
- Behavioral model: see **behavioral.puml**.
- Full machine‑readable requirement listing: **requirements.json**.
- Traceability matrix: **VMX.csv**.
