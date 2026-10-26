# Domain requirements (read-only)

Generated from `prompts/prompt_inputs.json`. Rubric traceability only (spec §2).

## Functional

- **REQ-F-01** — The system shall store a name, an address and a phone number for each customer.
- **REQ-F-02** — The system shall allow a customer to have an optional bank account.
- **REQ-F-03** — The system shall store a name, a description, a price and an image for each product.
- **REQ-F-04** — The system shall allow an order to be submitted for a customer, containing one or more order items and a payment method.
- **REQ-F-05** — The system shall reject an order submission if the customer is not known to the system.
- **REQ-F-06** — The system shall reject an order submission that contains no order item.
- **REQ-F-07** — The system shall reject an order submission if any order item refers to a product that does not exist.
- **REQ-F-08** — The system shall determine the total amount of each order.
- **REQ-F-09** — The system shall register a valid order submission as an order with an order date and the status pending.
- **REQ-F-10** — The system shall record each order item with a quantity, a unit price and a reference to exactly one product.
- **REQ-F-11** — The system shall associate each order with exactly one customer, while a customer may have any number of orders.
- **REQ-F-12** — The system shall allow the status of an order to be set to accepted.
- **REQ-F-13** — The system shall allow an invoice to be raised for an order, with a date, an amount, a payment method and the status pending.
- **REQ-F-14** — The system shall allow at most one invoice per order.
- **REQ-F-15** — The system shall allow the status of an invoice to be set to issued.
- **REQ-F-16** — The system shall prevent an invoice that has already been issued from being issued again.
- **REQ-F-17** — The system shall allow a payment to be submitted against an invoice, with a date, an amount and a payment method.
- **REQ-F-18** — The system shall allow any number of payments against one invoice.
- **REQ-F-19** — The system shall record each submitted payment with the status pending, awaiting confirmation.
- **REQ-F-20** — The system shall allow a pending payment to be confirmed by setting its status to completed.
- **REQ-F-21** — The system shall allow a pending payment to be rejected by setting its status to failed, without changing the status of its invoice or order.
- **REQ-F-22** — When a payment is confirmed, the system shall set the status of its invoice to paid.
- **REQ-F-23** — After the invoice has been set to paid, the system shall set the status of its order to paid.
- **REQ-F-24** — The system shall allow the status of an order to be set to shipped.
- **REQ-F-25** — The system shall allow the status of an order to be set to closed.
- **REQ-F-26** — The system shall treat every attribute as mandatory, except the bank account of a customer.
- **REQ-F-27** — The system shall represent monetary values (product price, unit price, order total, invoice amount, payment amount) as decimal numbers.
- **REQ-F-28** — The system shall restrict the status of an order to pending, accepted, paid, shipped or closed; of an invoice to pending, issued or paid; and of a payment to pending, completed or failed.
- **REQ-F-29** — The system shall restrict the payment method to bank, card or cash.
- **REQ-F-30** — The system shall change the status of an order only in the sequence pending, accepted, paid, shipped, closed.
- **REQ-F-31** — The system shall change the status of an invoice only in the sequence pending, issued, paid, and the status of a payment only from pending to completed or to failed.
- **REQ-F-32** — The system shall not set an order to paid unless its invoice has been set to paid.

## Non-functional

- **REQ-N-01** — When a user submits an order containing up to 50 order items under normal operating conditions, the system shall register the order and respond within 2 seconds for at least 95% of submissions.
- **REQ-N-02** — Under normal operating conditions, the system shall support at least 200 concurrent users and at least 20 order submissions per second while meeting the response time of REQ-N-01.
- **REQ-N-03** — The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.
- **REQ-N-04** — When a server failure occurs, the system shall resume accepting requests within 15 minutes without losing any order, invoice or payment recorded before the failure.
- **REQ-N-05** — The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.
- **REQ-N-06** — The system shall allow only users holding the accountant role to confirm or reject a payment, and shall reject the same request from any other user.
- **REQ-N-07** — The system shall protect customer personal data and bank account numbers by encrypting them in transit with TLS 1.2 or higher and at rest.
- **REQ-N-08** — The system shall record the user and the time of every status change of an order, an invoice and a payment, and shall retain these records for at least 12 months.
