import json, csv, io

OUT = "/home/claude"
dom = json.load(open(f"{OUT}/domain_requirements.json"))

def G(g, w, t): return ("given_when_then", g, w, t)
def C(t): return ("condition", t)
ART = {"Customer": "a", "OrderStaff": "an", "Accountant": "an"}

# role, capability, benefit, priority, verification, ACs, FR sources, structural, behavioral
US = [
("Customer", "to have my name, address and phone number recorded",
 "my orders can be delivered to me and I can be contacted about them", "must", "test", [
    C("The system stores a name, an address and a phone number for every customer."),
    C("The system accepts a customer record that has no bank account."),
    C("A customer has at most one bank account."),
    G("a customer record that lacks a name, an address or a phone number", "the record is saved", "the system rejects the record"),
 ], [1, 2, 26],
 ["Customer", "Customer.name", "Customer.address", "Customer.phone", "Customer.bankAccount"],
 []),

("Customer", "to have each product described by a name, a description, a price and an image",
 "I can choose the products I want to order", "must", "test", [
    C("The system stores a name, a description, a price and an image for every product."),
    G("a product record that lacks a name, a description, a price or an image", "the record is saved", "the system rejects the record"),
    C("The price of a product is stored as a decimal number."),
 ], [3, 26, 27],
 ["Product", "Product.name", "Product.description", "Product.price", "Product.image"],
 []),

("Customer", "to submit an order for one or more products",
 "my purchase is registered for fulfilment", "must", "test", [
    G("a known customer and at least one order item that refers to an existing product", "the order is submitted with a payment method", "the system registers an order with the submission date as its order date and the status pending"),
    C("Each order item records a quantity, a unit price and exactly one product, and belongs to exactly one order."),
    C("Each order belongs to exactly one customer, and a customer may have any number of orders."),
    C("The unit price of an order item is stored as a decimal number."),
 ], [4, 9, 10, 11, 27],
 ["Order", "Order.orderDate", "Order.status", "Order.method", "OrderItem", "OrderItem.quantity",
  "OrderItem.unitPrice", "OrderStatus", "PaymentMethod",
  ],
 ["Make an Order", "Receive order"]),

("Customer", "to have an invalid order submission rejected",
 "I find out at once that the order did not go through", "must", "test", [
    G("a customer who is not known to the system", "an order is submitted for that customer", "the system rejects the submission and registers no order"),
    G("an order submission that contains no order item", "the order is submitted", "the system rejects the submission and registers no order"),
    G("an order item that refers to a product that does not exist", "the order is submitted", "the system rejects the submission and registers no order"),
 ], [5, 6, 7],
 ["Customer", "Order", "OrderItem", "Product"],
 ["Make an Order"]),

("Customer", "to know the total amount of my order",
 "I can check what I will be charged", "must", "test", [
    G("an order with one or more order items", "the order is registered", "the system records a total amount for the order"),
    C("The total amount of an order equals the sum over its order items of quantity multiplied by unit price."),
    C("The total amount of an order is stored as a decimal number."),
 ], [8, 27],
 ["Order.totalAmount", "OrderItem.quantity", "OrderItem.unitPrice"],
 ["Make an Order"]),

("OrderStaff", "to decline a pending order",
 "an order that will not be fulfilled is ended without being invoiced or shipped", "must", "test", [
    G("an order with the status pending", "OrderStaff declines the order", "the system sets its status to closed"),
    G("an order whose status is not pending", "OrderStaff attempts to decline the order", "the system rejects the request and leaves the status unchanged"),
    G("a declined order", "an invoice is requested for the order", "the system rejects the request"),
 ], [12, 14, 30],
 ["Order.status", "OrderStatus"],
 ["Close Order"]),

("OrderStaff", "to mark a pending order as filled",
 "the order can proceed to shipping and invoicing", "must", "test", [
    G("an order with the status pending", "OrderStaff marks the order as filled", "the system sets its status to filled"),
    G("an order whose status is not pending", "OrderStaff attempts to mark the order as filled", "the system rejects the request and leaves the status unchanged"),
    C("A filled order can next be set only to shipped or to paid."),
    C("The status of an order is always one of pending, filled, paid, shipped or closed."),
 ], [13, 28, 30],
 ["Order.status", "OrderStatus"],
 ["Fill Order"]),

("OrderStaff", "to mark an order as shipped",
 "the delivery of the goods to the customer is recorded", "must", "test", [
    G("an order with the status filled", "OrderStaff marks the order as shipped", "the system sets its status to shipped"),
    G("an order with the status paid", "OrderStaff marks the order as shipped", "the system sets its status to shipped"),
    G("an order with the status pending or closed", "OrderStaff attempts to mark the order as shipped", "the system rejects the request and leaves the status unchanged"),
 ], [24, 30],
 ["Order.status", "OrderStatus"],
 ["Ship Order"]),

("OrderStaff", "to close a completed order",
 "finished orders are no longer processed", "must", "test", [
    G("an order that has been both shipped and paid", "OrderStaff closes the order", "the system sets its status to closed"),
    G("an order that has been shipped but not paid", "OrderStaff attempts to close the order", "the system rejects the request and leaves the status unchanged"),
    G("an order that has been paid but not shipped", "OrderStaff attempts to close the order", "the system rejects the request and leaves the status unchanged"),
    C("The status of a closed order cannot be changed."),
 ], [25, 30],
 ["Order.status", "OrderStatus"],
 ["Close Order"]),

("Accountant", "to issue an invoice for a filled order",
 "the customer knows the amount to pay", "must", "test", [
    G("an order that has been filled and has no invoice", "the Accountant issues an invoice for the order", "the system records an invoice with a date, a decimal amount, a payment method and the status issued"),
    G("an order that already has an invoice", "the Accountant attempts to issue another invoice for the order", "the system rejects the request"),
    G("an order that has not been filled", "the Accountant attempts to issue an invoice for the order", "the system rejects the request"),
    C("The status of an invoice is always either issued or paid."),
    C("The status of an invoice changes only from issued to paid."),
 ], [14, 15, 27, 28, 31],
 ["Invoice", "Invoice.date", "Invoice.amount", "Invoice.status", "Invoice.method", "InvoiceStatus",
  ],
 ["Send Invoice"]),

("Customer", "to pay an issued invoice",
 "my order can be completed", "must", "test", [
    G("an invoice with the status issued", "the Customer submits a payment against the invoice with a date, an amount and a payment method", "the system records the payment with the status pending"),
    C("Every payment method recorded for an order, an invoice or a payment is one of bank, card or cash."),
    C("The amount of a payment is stored as a decimal number."),
    C("The status of a payment is always one of pending, completed or failed."),
 ], [16, 18, 27, 28, 29],
 ["Payment", "Payment.date", "Payment.amount", "Payment.status", "Payment.method", "PaymentStatus",
  "PaymentMethod"],
 ["Make Payment"]),

("Customer", "to submit a new payment after a previous payment has failed",
 "I can still settle my invoice when a payment does not go through", "should", "test", [
    G("an invoice whose most recent payment has the status failed", "the Customer submits a new payment against the invoice", "the system records a separate payment with the status pending"),
    C("A failed payment keeps the status failed when a new payment is submitted against the same invoice."),
    C("An invoice may have any number of payments."),
 ], [17, 21],
 ["Payment", "Payment.status", "PaymentStatus"],
 ["Make Payment"]),

("Accountant", "to confirm a pending payment",
 "the invoice and its order are recorded as paid", "must", "test", [
    G("a payment with the status pending", "the Accountant confirms the payment", "the system sets the status of the payment to completed"),
    G("a pending payment against an issued invoice", "the Accountant confirms the payment", "the system sets the status of the invoice to paid"),
    G("an invoice that has just been set to paid", "the system records the change", "the system sets the status of the order of that invoice to paid"),
    C("An order is never set to paid while its invoice is not paid."),
    G("a payment whose status is completed or failed", "the Accountant attempts to confirm the payment", "the system rejects the request and leaves the status unchanged"),
 ], [19, 22, 23, 31, 32],
 ["Payment.status", "Invoice.status", "Order.status", "PaymentStatus", "InvoiceStatus", "OrderStatus",
  ],
 ["Accept Payment"]),

("Accountant", "to reject a pending payment",
 "a payment that did not go through is not counted as settling the invoice", "must", "test", [
    G("a payment with the status pending", "the Accountant rejects the payment", "the system sets the status of the payment to failed"),
    G("a payment with the status pending", "the Accountant rejects the payment", "the status of its invoice and of its order remain unchanged"),
    G("a payment whose status is completed or failed", "the Accountant attempts to reject the payment", "the system rejects the request and leaves the status unchanged"),
 ], [20, 31],
 ["Payment.status", "PaymentStatus"],
 []),
]

NFR_SPEC = [
("performance", "The system shall register a submitted order containing up to 50 order items and respond within 2 seconds for at least 95% of submissions under normal operating conditions.", "must", "test", [1],
 ["Order", "OrderItem"], ["Make an Order", "Receive order"]),
("performance", "The system shall support at least 200 concurrent users and at least 20 order submissions per second under normal operating conditions while meeting the response time of NFR-01.", "should", "test", [2],
 ["Order"], ["Make an Order"]),
("availability", "The system shall be available for at least 99.5% of each calendar month, excluding scheduled maintenance announced at least 24 hours in advance.", "must", "analysis", [3],
 [], []),
("availability", "The system shall resume accepting requests within 15 minutes after a server failure without losing any order, invoice or payment recorded before the failure.", "must", "test", [4],
 ["Order", "Invoice", "Payment"], []),
("security", "The system shall authenticate every user before granting access to any customer, order, invoice or payment data, and shall reject 100% of unauthenticated requests.", "must", "test", [5],
 ["Customer", "Order", "Invoice", "Payment"], []),
("security", "The system shall allow only users holding the Accountant role to confirm or reject a payment, and shall reject the same request from any other user.", "must", "test", [6],
 ["Payment.status", "PaymentStatus"], ["Accept Payment"]),
("security", "The system shall encrypt customer personal data and bank account numbers in transit using TLS 1.2 or higher and at rest.", "must", "inspection", [7],
 ["Customer.name", "Customer.address", "Customer.phone", "Customer.bankAccount"], []),
("security", "The system shall record the user and the time of every status change of an order, an invoice or a payment, and shall retain these records for at least 12 months.", "should", "test", [8],
 ["Order.status", "Invoice.status", "Payment.status"],
 ["Fill Order", "Ship Order", "Close Order", "Send Invoice", "Accept Payment"]),
]

reqs, rows = [], []
for n, (role, cap, ben, prio, ver, acs, src, st, bh) in enumerate(US, 1):
    rid = f"US-{n:02d}"
    ac_objs = []
    for k, ac in enumerate(acs, 1):
        aid = f"{rid}-AC{k:02d}"
        if ac[0] == "given_when_then":
            _, g, w, t = ac
            ac_objs.append({"id": aid, "format": "given_when_then",
                            "text": f"Given {g}, When {w}, Then {t}.",
                            "given": g, "when": w, "then": t})
        else:
            ac_objs.append({"id": aid, "format": "condition", "text": ac[1],
                            "given": "", "when": "", "then": ""})
    reqs.append({"id": rid, "type": "functional", "form": "user_story",
                 "statement": f"As {ART[role]} {role}, I want {cap}, so that {ben}.",
                 "role": role, "capability": cap, "acceptance_criteria": ac_objs,
                 "priority": prio, "verification_method": ver})
    rows.append([rid, ";".join(f"REQ-F-{s:02d}" for s in src), ";".join(st), ";".join(bh)])

for n, (typ, stmt, prio, ver, src, st, bh) in enumerate(NFR_SPEC, 1):
    rid = f"NFR-{n:02d}"
    reqs.append({"id": rid, "type": typ, "form": "declarative", "statement": stmt,
                 "role": "", "capability": "", "acceptance_criteria": [],
                 "priority": prio, "verification_method": ver})
    rows.append([rid, ";".join(f"REQ-N-{s:02d}" for s in src), ";".join(st), ";".join(bh)])

with open(f"{OUT}/requirements.json", "w", encoding="utf-8") as f:
    json.dump(reqs, f, indent=2, ensure_ascii=False); f.write("\n")

buf = io.StringIO()
w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
w.writerow(["SRS-Req-ID", "Source-Input-ID", "Structural-Elements", "Behavorial-Elements"])
w.writerows(rows)
open(f"{OUT}/VMX.csv", "w", encoding="utf-8", newline="").write(buf.getvalue())
print("requirements:", len(reqs), "| vmx rows:", len(rows))