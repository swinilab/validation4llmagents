# 1. Introduction

## 1.1 Purpose
This Software Requirements Specification (SRS) defines the functional and non-functional requirements for the Order Management System (OMS). The document establishes a binding specification for software developers, verification engineers, and business stakeholders, ensuring that all domain expectations for order processing, billing, payment handling, and customer record management are rigorously satisfied.

## 1.2 Scope
The Order Management System is an enterprise platform engineered to govern the lifecycle of commercial transactions. The system manages product listings, customer profiles, order fulfillment workflows, invoice issuance, and payment reconciliations across three designated business roles: Customer, OrderStaff, and Accountant. External payment gateways, physical shipping logistics, and warehouse inventory replenishments are outside the direct boundary of the system and interact solely through defined state transitions. The structural domain model is provided in structural.puml, the dynamic end-to-end operational workflow is modeled in behavioral.puml, the complete requirement dataset is cataloged in requirements.json, and cross-cutting traceability is maintained in VMX.csv.

## 1.3 Definitions and acronyms
- **Accountant**: An internal user authorized to raise invoices and verify or reject recorded customer payments.
- **AC**: Acceptance Criterion.
- **Customer**: An end-user who maintains contact information, browses the product catalog, submits purchase orders, and makes payments against invoices.
- **FR**: Functional Requirement.
- **NFR**: Non-Functional Requirement.
- **Order**: A formal purchase request created by a customer containing one or more order items, a payment method, a total monetary sum, and an explicit lifecycle status.
- **OrderItem**: A discrete line item belonging compositionally to an order, referencing a specific product with an associated unit price and quantity.
- **OrderStaff**: Internal personnel responsible for receiving, fulfilling, declining, shipping, and closing customer orders.
- **Invoice**: A billing record linked to a filled or shipped order, specifying the amount due and settlement status.
- **Payment**: A financial transaction submitted against an issued invoice and adjudicated by an accountant.
- **RBAC**: Role-Based Access Control.
- **RTO**: Recovery Time Objective.
- **SRS**: Software Requirements Specification.
- **TLS**: Transport Layer Security.
- **VMX**: Verification Matrix / Traceability Matrix.

# 2. Overall description

## 2.1 Product perspective
The OMS operates as the central transactional backbone within an enterprise digital commerce architecture. It interfaces with front-end user clients for customer self-service and internal management consoles for order fulfillment staff and accountants. All structural entities—Customer, Product, Order, OrderItem, Invoice, and Payment—together with their strict typing, value enumerations, and multiplicities, are formally specified in the domain model structural.puml.

## 2.2 Product functions
The primary operational functions provided by the OMS include:
- **Customer and Catalog Management**: Storing contact information, optional banking details, and product catalog metadata with decimal currency precision.
- **Order Submission and Validation**: Enforcing customer identity validation, product reference existence, line item presence, and deterministic total amount calculations.
- **Order Fulfillment Lifecycle**: Progressive workflow management allowing order receipt, fulfillment assembly, decline termination, and physical shipment dispatch.
- **Invoicing and Financial Settlement**: Generating billing records for fulfilled or shipped orders, accepting single or repeated customer payment submissions, accountant payment review, and automated invoice marking upon payment confirmation.
- **Independent Parallel Processing**: Asynchronous parallel progression of invoicing and shipment once an order is marked filled, converging at order closure when both shipment and invoice settlement are complete.
- **Order Finalization**: Formal archival and closure of completed or declined orders with immutable state guarantees.

The complete operational flow and swimlane interactions are detailed in behavioral.puml.

## 2.3 User characteristics
- **Customer**: External end-users with varying levels of technical proficiency. Requires straightforward product viewing, responsive order placement, and seamless invoice settlement mechanisms.
- **OrderStaff**: Internal warehouse and operations personnel operating desktop or mobile workstation terminals. Proficient with fulfillment workflows, item validation, shipment dispatching, and order closure protocols.
- **Accountant**: Internal finance specialists with thorough knowledge of bookkeeping, auditing principles, and financial compliance. Dedicated to invoice issuance accuracy and payment authorization.

## 2.4 Assumptions and dependencies
- Underlying datastores provide ACID transaction guarantees and decimal precision for monetary calculations.
- Secure transport infrastructure supports TLS 1.2 or higher for all communication channels.
- System operational environments guarantee accurate system clock timestamps for status changes and audit log persistence.
- External banking and credit card processing systems provide reliable transaction validation signals reviewed by accountants.

# 3. Requirements

## 3.1 Functional requirements

### US-01: Customer Profile Management

As a Customer, I want to record and maintain my profile information including my contact details and an optional bank account, so that the system can identify me and associate me with my orders.

- **US-01-AC01**: The system shall store a name, an address and a phone number for each customer.
- **US-01-AC02**: The system shall allow a customer to have at most one bank account, which is optional.
- **US-01-AC03**: The system shall treat the customer name, address and phone number as mandatory attributes, and shall treat the bank account as optional.
- **US-01-AC04**: Given a customer profile submission missing any mandatory attribute, When the customer attempts to save the profile, Then the system shall reject the customer record and register no customer.
- **US-01-AC05**: Given valid customer details including name, address, phone number and an optional bank account, When the customer submits the profile, Then the system shall record the customer profile.

### US-02: Product Catalog Browsing

As a Customer, I want to browse products with their name, description, price and image, so that I can choose items to purchase.

- **US-02-AC01**: The system shall store a name, a description, a price and an image for each product.
- **US-02-AC02**: The system shall allow a product to be referred to by any number of order items, including none, and shall keep a product in existence independently of the order items that refer to it.
- **US-02-AC03**: The system shall treat name, description, price and image as mandatory attributes for every product, and shall reject a product record in which a mandatory attribute is absent.
- **US-02-AC04**: The system shall represent product price as a decimal number.
- **US-02-AC05**: Given products stored in the system, When a customer browses the product catalog, Then the system shall display the name, description, decimal price and image of each available product.

### US-03: Order Submission

As a Customer, I want to submit an order containing one or more items and a selected payment method, so that I can purchase the selected products.

- **US-03-AC01**: The system shall record each order with an order date, a total amount, a status and a payment method.
- **US-03-AC02**: The system shall record each order item with a quantity, a unit price and a reference to exactly one product, and shall associate each order item with exactly one order.
- **US-03-AC03**: The system shall keep an order item in existence only as part of the order it belongs to, shall not allow an order item to be moved to another order, and shall remove the order items of an order when that order is removed.
- **US-03-AC04**: The system shall associate each order with exactly one customer, while a customer may have any number of orders.
- **US-03-AC05**: Given a known customer, one or more order items each referencing an existing product, and a valid payment method, When the customer submits the order, Then the system shall register it as an order with the submission date as its order date, the status submitted, and a total amount equal to the sum over its order items of quantity multiplied by unit price.
- **US-03-AC06**: Given an order submission where the customer is not known to the system, When the customer submits the order, Then the system shall reject the order submission and register no order.
- **US-03-AC07**: Given an order submission that contains no order item, When the customer submits the order, Then the system shall reject the order submission and register no order.
- **US-03-AC08**: Given an order submission where any order item refers to a product that does not exist, When the customer submits the order, Then the system shall reject the order submission and register no order.
- **US-03-AC09**: The system shall represent the unit price and order total amount as decimal numbers.
- **US-03-AC10**: The system shall restrict the status of an order to submitted, pending, filled, shipped or closed.
- **US-03-AC11**: The system shall restrict the payment method recorded on an order to bank, card or cash.

### US-04: Order Receipt

As a OrderStaff, I want to receive a submitted order by transitioning its status to pending, so that our fulfillment team can begin processing it.

- **US-04-AC01**: Given an order whose status is submitted, When order staff receives the order, Then the system shall set the status of the order to pending.
- **US-04-AC02**: Given an order whose status is not submitted, When order staff attempts to receive the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-04-AC03**: The system shall change the status of an order from submitted only to pending.

### US-05: Order Fulfillment

As a OrderStaff, I want to mark a pending order as filled once items are assembled, so that the order is ready for invoicing and shipment.

- **US-05-AC01**: Given an order whose status is pending, When order staff marks the order as filled, Then the system shall set the status of the order to filled.
- **US-05-AC02**: Given an order whose status is not pending, When order staff attempts to mark the order as filled, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-05-AC03**: The system shall change the status of an order from pending only to filled or to closed.

### US-06: Order Decline

As a OrderStaff, I want to decline a pending order by setting its status to closed, so that an unfulfillable order is terminated without raising an invoice.

- **US-06-AC01**: Given an order whose status is pending, When order staff declines the order, Then the system shall set the status of the order to closed.
- **US-06-AC02**: Given an order whose status is not pending, When order staff attempts to decline the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-06-AC03**: Given an order that has been declined, When an accountant requests to raise an invoice for that order, Then the system shall reject the request.
- **US-06-AC04**: The system shall not change the status of an order whose status is closed.

### US-07: Order Shipment

As a OrderStaff, I want to set a filled order to shipped, so that goods can be dispatched to the customer independently of invoicing.

- **US-07-AC01**: Given an order whose status is filled, When order staff sets the status of the order to shipped, Then the system shall set the status of the order to shipped.
- **US-07-AC02**: Given an order whose status is not filled, When order staff attempts to set the order to shipped, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-07-AC03**: Given an order being set to shipped, When the status of the order changes to shipped, Then the system shall leave the status of an invoice and of any payment against that invoice unchanged.
- **US-07-AC04**: The system shall let invoicing and shipping proceed independently of each other once an order has been filled, so that setting the order to shipped does not require an invoice to have been raised.
- **US-07-AC05**: The system shall change the status of an order from filled only to shipped.

### US-08: Invoice Generation

As a Accountant, I want to raise an invoice for a filled or shipped order, so that the customer can be billed for their order.

- **US-08-AC01**: The system shall record each invoice with a date, an amount, a status and a payment method.
- **US-08-AC02**: The system shall allow at most one invoice per order, and shall associate each invoice with exactly one order.
- **US-08-AC03**: Given an order whose status is filled or shipped and that has no invoice, When an accountant raises an invoice for that order, Then the system shall record an invoice for the order with a date, an amount, a payment method and the status issued.
- **US-08-AC04**: Given an order that already has an invoice, When an accountant requests to raise a further invoice for that order, Then the system shall reject the request.
- **US-08-AC05**: Given an order whose status is submitted, pending or closed, When an accountant requests to raise an invoice for that order, Then the system shall reject the request.
- **US-08-AC06**: The system shall let invoicing and shipping proceed independently of each other once an order has been filled, so that raising an invoice does not require the order to have been shipped.
- **US-08-AC07**: The system shall represent the invoice amount as a decimal number.
- **US-08-AC08**: The system shall restrict the status of an invoice to issued or paid.
- **US-08-AC09**: The system shall restrict the payment method recorded on an invoice to bank, card or cash.

### US-09: Payment Submission

As a Customer, I want to submit a payment against an issued invoice, so that I can pay for my order using a supported payment method.

- **US-09-AC01**: The system shall record each payment with a date, an amount, a status and a payment method.
- **US-09-AC02**: The system shall allow any number of payments against one invoice, and shall record each payment against exactly one invoice rather than directly against an order.
- **US-09-AC03**: Given an invoice whose status is issued, When a customer submits a payment against that invoice with a date, an amount and a payment method, Then the system shall record the payment against that invoice with the status pending.
- **US-09-AC04**: Given an invoice whose status is paid, When a customer submits a payment against that invoice, Then the system shall reject the payment.
- **US-09-AC05**: Given an invoice whose earlier payment has the status failed, When a customer submits a further payment against that invoice, Then the system shall record it as a separate payment with the status pending, and shall keep the failed payment at the status failed.
- **US-09-AC06**: The system shall represent the payment amount as a decimal number.
- **US-09-AC07**: The system shall restrict the status of a payment to pending, completed or failed.
- **US-09-AC08**: The system shall restrict the payment method recorded on a payment to bank, card or cash.

### US-10: Payment Confirmation

As a Accountant, I want to confirm a pending payment, so that the received payment is marked completed and the associated invoice is marked paid.

- **US-10-AC01**: Given a payment whose status is pending, When an accountant confirms the payment, Then the system shall set the status of that payment to completed.
- **US-10-AC02**: Given an accountant confirms a pending payment against an invoice whose status is issued, When the confirmation occurs, Then the system shall set the status of that invoice to paid.
- **US-10-AC03**: Given a payment against an invoice being confirmed, When the payment is confirmed, Then the system shall leave the status of the order billed by that invoice unchanged.
- **US-10-AC04**: Given a payment whose status is not pending, When an accountant attempts to confirm the payment, Then the system shall reject the attempt and leave the status of the payment unchanged.
- **US-10-AC05**: The system shall change the status of an invoice only from issued to paid.

### US-11: Payment Rejection

As a Accountant, I want to reject a pending payment that is invalid, so that the customer can submit an alternative payment against the unsettled invoice.

- **US-11-AC01**: Given a payment whose status is pending, When an accountant rejects the payment, Then the system shall set the status of that payment to failed, and shall leave the status of its invoice and of its order unchanged.
- **US-11-AC02**: Given a payment whose status is not pending, When an accountant attempts to reject the payment, Then the system shall reject the attempt and leave the status of the payment unchanged.
- **US-11-AC03**: The system shall change the status of a payment only from pending to completed or to failed.

### US-12: Order Closure

As a OrderStaff, I want to close an order whose status is shipped and whose invoice is paid, so that the fulfilled and paid order is formally completed.

- **US-12-AC01**: Given an order whose status is shipped and whose invoice has the status paid, When order staff closes the order, Then the system shall set the status of the order to closed.
- **US-12-AC02**: Given an order whose status is shipped and whose invoice does not have the status paid, When order staff attempts to close the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-12-AC03**: Given an order whose invoice has the status paid but whose order status is not shipped, When order staff attempts to close the order, Then the system shall reject the attempt and leave the status of the order unchanged.
- **US-12-AC04**: The system shall close a filled order only after both the shipping of the order and the settlement of its invoice have completed, whichever of the two finishes last.
- **US-12-AC05**: The system shall not change the status of an order whose status is closed.

## 3.2 Quality attributes

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
Verification of the requirements specified in this SRS shall be conducted using an integrated suite of testing methodologies:
- **Unit and Automated Integration Testing**: Every acceptance criterion defined under clause 3.1 shall be realized through automated test fixtures. Given-When-Then criteria shall be implemented as automated end-to-end integration test scenarios validating observable responses and state transitions. Condition criteria governing data types, multiplicity constraints, mandatory attributes, and lifecycle state invariants shall be verified through structural unit tests and database schema assertions.
- **Performance and Load Testing**: Requirements NFR-01 and NFR-02 shall be verified through automated stress-testing suites simulating 200 concurrent user sessions and sustained workloads of 20 order submissions per second, measuring 95th percentile response latencies against the 2.0-second threshold.
- **Security and Compliance Auditing**: Requirement NFR-03 shall be verified through penetration testing and automated test harnesses verifying zero access for unauthenticated calls. NFR-04 shall be verified by asserting role-based authorization denials for non-accountant actors attempting payment adjudication. NFR-05 shall be verified via automated cryptographic inspection of network packets (enforcing TLS 1.2+) and static analysis of persistent database encryption keys. NFR-06 shall be verified by inspecting audit trail tables ensuring user identity and timestamp retention for 12 months.
- **Availability and Disaster Recovery Testing**: Requirement NFR-07 shall be monitored continuously using synthetic uptime monitoring probes calculating monthly availability. Requirement NFR-08 shall be verified by performing simulated server failover drills, demonstrating restoration of request handling within 15 minutes with complete transactional data integrity.

All requirements trace back to their originating domain requirements and architectural model elements via the traceability matrix in VMX.csv.

# 5. Supporting information
This specification is supplemented by the following architectural and machine-readable artifacts:
- **structural.puml**: PlantUML domain class diagram detailing all domain entities, attributes, data types, enumerations, and relationships with multiplicities.
- **behavioral.puml**: PlantUML activity diagram depicting end-to-end order execution, swimlane partitioning across Customer, OrderStaff, and Accountant roles, parallel invoice/shipping forks and joins, and repetitive payment loops.
- **requirements.json**: Machine-readable enumeration of every requirement and acceptance criterion, structured in UTF-8 JSON according to specification standards.
- **VMX.csv**: Complete verification matrix establishing bidirectional traceability between SRS requirements, domain requirements, structural elements, and behavioral action elements.
