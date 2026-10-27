# 1. Introduction

## 1.1 Purpose
The purpose of this Software Requirements Specification (SRS) is to define, in a complete and traceable manner, the functional and non‑functional requirements for the **Order Management System** (OMS). The document is intended for the development team, testers, project managers and any other stakeholder who needs a clear, unambiguous description of the system’s behaviour.

## 1.2 Scope
The OMS supports the complete lifecycle of a commercial order: customer registration, product catalog management, order submission, order processing, invoicing, payment handling and order closure. The system is used by three roles – **Customer**, **OrderStaff**, and **Accountant** – each of which interacts with the system through a web‑based UI or API.

## 1.3 Definitions and acronyms

| Term | Definition |
|------|------------|
| Customer | End‑user who purchases products. |
| OrderStaff | Internal staff that receives, validates and fulfills orders. |
| Accountant | Internal staff that creates invoices and records payments. |
| OMS | Order Management System. |
| UI | User Interface. |
| API | Application Programming Interface. |
| TLS | Transport Layer Security. |

# 2. Overall description

## 2.1 Product perspective
The OMS is a standalone web application that persists data in a relational database. It exposes RESTful services for integration with external systems (e.g., payment gateways). The product is independent of any legacy order system.

## 2.2 Product functions
* Manage customers, products, orders, invoices and payments.
* Enforce business rules concerning status transitions, multiplicities and monetary values.
* Provide audit logging of all status changes.
* Secure data in transit (TLS 1.2+) and at rest (encryption of personal data).

## 2.3 User characteristics

| Role | Typical characteristics |
|------|--------------------------|
| Customer | Familiar with web browsers, expects fast response times (< 2 s). |
| OrderStaff | Needs to view pending orders, change order status, raise invoices. |
| Accountant | Needs to raise invoices, record payments, confirm or reject payments. |

## 2.4 Assumptions and dependencies
* A relational database supporting decimal data types is available.
* TLS 1.2+ termination is handled by the web server.
* All monetary values are expressed in a single currency.

# 3. Requirements

## 3.1 Functional requirements

| ID | User story | Acceptance criteria |
|----|------------|---------------------|
| **US-01** | As a **Customer**, I want to **register my personal details (name, address, phone) and optionally a bank account**, so that **the system can identify me for future orders**. | • **US-01‑AC01** – `condition` – Name, address and phone are mandatory strings; bank account is optional.<br>• **US-01‑AC02** – `condition` – Bank account numbers are stored encrypted at rest.<br>• **US-01‑AC03** – `given_when_then` – Given a new customer record with all mandatory fields, when the record is saved, then the system assigns a unique Customer‑ID. |
| **US-02** | As a **Customer**, I want to **browse the product catalog**, so that **I can decide what to buy**. | • **US-02‑AC01** – `condition` – Each product has a name, description, price (decimal) and image URL.<br>• **US-02‑AC02** – `condition` – Price values are stored with two decimal places.<br>• **US-02‑AC03** – `given_when_then` – Given a request for the product list, when the system returns the list, then every product includes all four attributes. |
| **US-03** | As a **Customer**, I want to **submit an order that contains at least one order item, each referencing an existing product, and select a payment method**, so that **my purchase request can be processed**. | • **US-03‑AC01** – `given_when_then` – Given a known Customer‑ID, at least one order item and a valid payment method, when the order is submitted, then an Order is created with status **submitted** and the current date as order‑date.<br>• **US-03‑AC02** – `condition` – Payment method must be one of {bank, card, cash}.<br>• **US-03‑AC03** – `given_when_then` – Given an unknown Customer‑ID, when an order is submitted, then the system rejects the submission and no Order is created. |
| **US-04** | As a **Customer**, I want the **system to calculate the total amount of my order automatically**, so that **I know how much I will be charged**. | • **US-04‑AC01** – `condition` – Order total = Σ (order‑item.quantity × order‑item.unit‑price).<br>• **US-04‑AC02** – `given_when_then` – Given a successfully created Order, when the total is queried, then the returned total equals the calculated sum.<br>• **US-04‑AC03** – `condition` – Unit price is stored as a decimal. |
| **US-05** | As an **OrderStaff**, I want to **receive a submitted order**, so that **it can move to the pending state for further processing**. | • **US-05‑AC01** – `given_when_then` – Given an Order with status **submitted**, when OrderStaff clicks *Receive*, then the Order status becomes **pending**.<br>• **US-05‑AC02** – `condition` – The status transition *submitted → pending* is the only allowed transition from **submitted**.<br>• **US-05‑AC03** – `given_when_then` – Given an Order whose status is **filled**, when OrderStaff attempts to receive it, then the system rejects the request and leaves the status unchanged. |
| **US-06** | As an **OrderStaff**, I want to **mark a pending order as filled**, so that **the items can be prepared for shipping**. | • **US-06‑AC01** – `given_when_then` – Given an Order with status **pending**, when OrderStaff selects *Mark as Filled*, then the Order status becomes **filled**.<br>• **US-06‑AC02** – `condition` – No transition is allowed from **pending** to any status other than **filled** or **closed**.<br>• **US-06‑AC03** – `given_when_then` – Given an Order with status **submitted**, when OrderStaff attempts to fill it, then the request is rejected and the status stays **submitted**. |
| **US-07** | As an **OrderStaff**, I want to **decline a pending order**, so that **the order is closed without further processing**. | • **US-07‑AC01** – `given_when_then` – Given an Order with status **pending**, when OrderStaff selects *Decline*, then the Order status becomes **closed**.<br>• **US-07‑AC02** – `condition` – Decline is only permitted from **pending**.<br>• **US-07‑AC03** – `given_when_then` – Given an Order with status **filled**, when OrderStaff attempts to decline, then the system rejects the request. |
| **US-08** | As an **OrderStaff**, I want to **ship a filled order**, so that **the customer receives the goods**. | • **US-08‑AC01** – `given_when_then` – Given an Order with status **filled**, when OrderStaff selects *Ship*, then the Order status becomes **shipped**.<br>• **US-08‑AC02** – `condition` – Transition *filled → shipped* is the only allowed transition from **filled**.<br>• **US-08‑AC03** – `given_when_then` – Given an Order with status **pending**, when OrderStaff attempts to ship, then the request is rejected and the status remains **pending**. |
| **US-09** | As an **Accountant**, I want to **raise an invoice for a filled or shipped order that has no invoice yet**, so that **the customer can be billed**. | • **US-09‑AC01** – `given_when_then` – Given an Order with status **filled** or **shipped** and no existing Invoice, when Accountant creates an Invoice (date, amount, payment method), then an Invoice with status **issued** is linked to the Order.<br>• **US-09‑AC02** – `condition` – Only one Invoice may exist per Order.<br>• **US-09‑AC03** – `given_when_then` – Given an Order whose status is **submitted**, **pending** or **closed**, when Accountant tries to raise an Invoice, then the request is rejected. |
| **US-10** | As an **Accountant**, I want to **record a payment against an issued invoice**, so that **the invoice can be settled**. | • **US-10‑AC01** – `given_when_then` – Given an Invoice with status **issued**, when a Customer submits a Payment (date, amount, payment method), then a Payment record with status **pending** is created and linked to the Invoice.<br>• **US-10‑AC02** – `condition` – Payment method must be one of {bank, card, cash}.<br>• **US-10‑AC03** – `given_when_then` – Given an Invoice with status **paid**, when a Payment is submitted, then the system rejects the submission. |
| **US-11** | As an **Accountant**, I want to **confirm a pending payment**, so that **the related invoice becomes paid**. | • **US-11‑AC01** – `given_when_then` – Given a Payment with status **pending**, when Accountant marks it **completed**, then the Payment status becomes **completed** and the linked Invoice status becomes **paid**.<br>• **US-11‑AC02** – `condition` – Payment status may only change from **pending** to **completed** or **failed**.<br>• **US-11‑AC03** – `given_when_then` – Given a Payment whose status is **failed**, when Accountant attempts to confirm it, then the request is rejected and the status stays **failed**. |
| **US-12** | As an **Accountant**, I want to **reject a pending payment**, so that **the customer can try again**. | • **US-12‑AC01** – `given_when_then` – Given a Payment with status **pending**, when Accountant marks it **failed**, then the Payment status becomes **failed**; the Invoice status remains unchanged.<br>• **US-12‑AC02** – `condition` – Only payments in **pending** may be rejected.<br>• **US-12‑AC03** – `given_when_then` – Given a Payment with status **completed**, when Accountant attempts to reject it, then the request is rejected. |
| **US-13** | As an **OrderStaff**, I want to **close a shipped order whose invoice is paid**, so that **the order lifecycle ends**. | • **US-13‑AC01** – `given_when_then` – Given an Order with status **shipped** and a linked Invoice with status **paid**, when OrderStaff selects *Close*, then the Order status becomes **closed**.<br>• **US-13‑AC02** – `condition` – Closing is only allowed from **shipped** when the Invoice is **paid**.<br>• **US-13‑AC03** – `given_when_then` – Given a shipped Order whose Invoice is not **paid**, when OrderStaff attempts to close, then the request is rejected and the status stays **shipped**. |
| **US-14** | As a **Customer**, **OrderStaff**, or **Accountant**, I want the **system to enforce mandatory attributes and allowed value sets**, so that **data integrity is guaranteed**. | • **US-14‑AC01** – `condition` – All attributes except `Customer.bankAccount` are mandatory.<br>• **US-14‑AC02** – `condition` – `Order.status` ∈ {submitted, pending, filled, shipped, closed}.<br>• **US-14‑AC03** – `condition` – `Invoice.status` ∈ {issued, paid}.<br>• **US-14‑AC04** – `condition` – `Payment.status` ∈ {pending, completed, failed}. |
| **US-15** | As a **Customer**, I want **all monetary values to be stored as decimals**, so that **calculations are exact**. | • **US-15‑AC01** – `condition` – `Product.price`, `OrderItem.unitPrice`, `Order.totalAmount`, `Invoice.amount`, `Payment.amount` are of type **decimal(12,2)**.<br>• **US-15‑AC02** – `given_when_then` – Given any monetary input, when it is persisted, then the stored value retains two fractional digits.<br>• **US-15‑AC03** – `condition` – No monetary field may be null. |
| **US-16** | As a **System**, I want to **record every status change together with user and timestamp**, so that **an audit trail is available for at least 12 months**. | • **US-16‑AC01** – `condition` – Every status transition creates an audit record (entity, oldStatus, newStatus, userId, timestamp).<br>• **US-16‑AC02** – `given_when_then` – Given a status change, when the audit log is queried, then the record appears with correct user and time.<br>• **US-16‑AC03** – `condition` – Audit records are retained for a minimum of 12 months. |
| **US-17** | As a **System**, I want to **prevent any modification of a closed order**, so that **its final state is immutable**. | • **US-17‑AC01** – `condition` – No status transition is allowed from **closed**.<br>• **US-17‑AC02** – `given_when_then` – Given a closed Order, when any staff attempts to change its status, then the request is rejected.<br>• **US-17‑AC03** – `condition` – The Order entity becomes read‑only after reaching **closed**. |
| **US-18** | As a **System**, I want to **enforce authentication for every request**, so that **only authorised users can access data**. | • **US-18‑AC01** – `condition` – Every API call must contain a valid authentication token.<br>• **US-18‑AC02** – `given_when_then` – Given a request without a token, when the request reaches the server, then the system returns HTTP 401 Unauthorized.<br>• **US-18‑AC03** – `condition` – Unauthenticated requests are logged and rejected 100 % of the time. |
| **US-19** | As a **System**, I want to **restrict payment‑related actions to the Accountant role**, so that **only authorised staff can confirm or reject payments**. | • **US-19‑AC01** – `condition` – Only users with role **Accountant** may invoke the *Confirm Payment* or *Reject Payment* actions.<br>• **US-19‑AC02** – `given_when_then` – Given a non‑Accountant user attempting to confirm a payment, when the request is processed, then the system returns HTTP 403 Forbidden.<br>• **US-19‑AC03** – `condition` – All attempts by unauthorized roles are logged. |
| **US-20** | As a **System**, I want to **support the performance, security and availability requirements**, so that **the OMS meets the service‑level expectations**. | • **US-20‑AC01** – `condition` – The system shall handle at least 200 concurrent users and at least 20 order submissions per second.<br>• **US-20‑AC02** – `condition` – 95 % of order submissions with ≤ 50 items shall complete within 2 seconds.<br>• **US-20‑AC03** – `condition` – Availability shall be ≥ 99.5 % per calendar month, with scheduled maintenance announced ≥ 24 h in advance. |

## 3.2 Quality attributes

### 3.2.1 Performance

| ID | Statement |
|----|-----------|
| **NFR-01** | When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within **2 seconds** for at least **95 %** of submissions. |
| **NFR-02** | Under normal operating conditions, the system shall support at least **200 concurrent users** and at least **20 order submissions per second** while meeting the response time of NFR‑01. |

### 3.2.2 Security

| ID | Statement |
|----|-----------|
| **NFR-03** | The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject **100 %** of unauthenticated requests. |
| **NFR-04** | The system shall allow only users holding the **accountant** role to confirm or reject a payment, and shall reject the same request from any other user. |
| **NFR-05** | The system shall protect customer personal data and bank account numbers by encrypting them in transit with **TLS 1.2 or higher** and at rest. |
| **NFR-06** | The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least **12 months**. |

### 3.2.3 Availability

| ID | Statement |
|----|-----------|
| **NFR-07** | When a server failure occurs, the system shall resume accepting requests within **15 minutes** without losing any order, invoice or payment recorded before the failure. |
| **NFR-08** | The system shall be available for at least **99.5 %** of each calendar month, excluding scheduled maintenance announced at least **24 hours** in advance. |

# 4. Verification
Each functional requirement shall be verified by automated acceptance‑test scripts that exercise the given‑when‑then scenarios and check the condition‑type constraints. Non‑functional requirements shall be verified by performance‑testing tools (e.g., JMeter), security scans (e.g., OWASP ZAP) and availability monitoring (e.g., Prometheus + Grafana).

# 5. Supporting information
* PlantUML structural diagram – **`structural.puml`**
* PlantUML behavioral diagram – **`behavioral.puml`**
* Machine‑readable requirement listing – **`requirements.json`**
* Traceability matrix – **`VMX.csv`**
