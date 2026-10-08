# Order Management System - Domain Requirements

## 1. Introduction & Business Roles

This document outlines the requirements for a standard order management platform. The system interactions revolve around four primary roles:

- **Customer**: The end-user browsing, purchasing, and managing their items.
- **Payment Gateway**: An external third-party service processing financial transactions.
- **Warehouse**: The logistics personnel responsible for physical fulfillment.
- **Sales**: Internal staff handling administration, oversight, and customer support.

## 2. Functional Requirements (FR)

### Ordering & Payment

- **FR01**: A Customer can add multiple distinct items and specify their desired quantities into a digital shopping cart.
- **FR02**: Before finalizing the checkout, the system verifies current inventory levels; if any item is out of stock, the system alerts the Customer and halts the transaction.
- **FR03**: Upon successful checkout confirmation, the system generates a new order in a draft state and calculates the final total amount.
- **FR04**: The system securely transmits the order total and transaction details to the external Payment Gateway for processing.
- **FR05**: If the Payment Gateway confirms a successful transaction, the system transitions the order to a placed state.
- **FR06**: If the Payment Gateway reports a declined transaction, the system updates the order to a payment failed state and notifies the Customer.

### Warehouse Processing

- **FR07**: The Warehouse team retrieves physical items for placed orders from the shelves and updates the order workflow to picked.
- **FR08**: After successfully gathering all required items, the Warehouse team boxes the items and transitions the order to a packed state.
- **FR09**: The Warehouse team hands the packages over to external carriers and updates the order to a shipped state.

### Post-Sale Actions

- **FR10**: A Customer can manually cancel an order only if it is in the placed state and has not yet been marked as picked by the Warehouse.
- **FR11**: When a valid cancellation is triggered, the system voids the order and immediately instructs the Payment Gateway to execute a full reversal of funds.
- **FR12**: A Customer can initiate a formal return request for any shipped order within a 30-day window.
- **FR13**: Once the Warehouse team physically receives and approves the returned items, the system issues a refund to the Customer.

### Administration

- **FR14**: Sales staff can search for any order using its unique identifier to view its current state and historical timeline.
- **FR15**: Sales staff can manually correct a Customer's delivery address on an order prior to it reaching the packed state.
- **FR16**: The system generates a daily summary report detailing total processed revenue and total volume of shipped orders for the Sales staff to review.

## 3. Non-Functional Requirements (NFR)

### Performance

- **NFR01**: The system shall complete order search, cart update, and checkout
  submission requests with a 95th-percentile response time of no more than
  2 seconds, measured at the API boundary under nominal load (≤500 concurrent
  sessions).

- **NFR02**: The system shall sustain 2,000 concurrent user sessions while
  continuing to meet the NFR01 response-time threshold, with a request error
  rate of no more than 0.1%.

### Security

- **NFR03**: The system shall encrypt all customer payment data using TLS 1.2
  or higher in transit and AES-256 at rest, and shall store no unencrypted
  primary account numbers in any log, database, or backup.

- **NFR04**: The system shall record an immutable audit entry for every order
  state change, capturing timestamp (UTC, millisecond precision), the acting
  role, the prior state, and the resulting state, retained for at least
  12 months and modifiable by no role.

### Reliability

- **NFR05**: The system shall achieve at least 99.9% availability measured
  monthly over a calendar month, excluding scheduled maintenance windows
  announced at least 48 hours in advance.

- **NFR06**: The system shall time out payment authorization requests to the
  Payment Gateway after 30 seconds, and shall ensure that a retried
  authorization for the same order results in no more than one charge against
  the customer's payment method.

### Data Integrity

- **NFR07**: The system shall roll back any partially completed order
  transaction in full within 60 seconds of failure detection, leaving no order
  in an intermediate state and no discrepancy between financial records and
  inventory counts.

### Scalability

- **NFR08**: The system shall support a 3× increase in peak daily order volume
  without modification to application code or data model, verified by load test
  against the projected peak.
