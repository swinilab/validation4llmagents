"""Builds M4 gold v0.2: requirements CSV, tier map, element CSVs (via extractor), traceability.
Traceability is declared by element NAME and resolved to extractor IDs here, so it
survives any change in element order."""
import csv, subprocess, sys, yaml
from collections import Counter

import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = f"{ROOT}/gold"
ONT = yaml.safe_load(open(f"{ROOT}/ontology/orderman-ontology.yaml"))
VERBS = set(ONT["action_verbs"])

COLS = ["gold_req_id", "tier", "statement", "actor", "action", "object", "condition",
        "qualifier", "req_type", "verification_method", "source_input_ids"]

# (tier, statement, actor, action, object, condition, qualifier, type, verif, sources,
#  class refs, activity refs)
R = [
("C","The system shall allow the Customer to add multiple distinct products to a shopping cart.",
 "customer","add","product","","to shopping_cart; multiple distinct products","functional","test","FR01",
 "class:Customer;class:ShoppingCart;class:CartItem;class:Product;rel:Customer-ShoppingCart;rel:ShoppingCart-CartItem;rel:CartItem-Product",
 "lane:Customer;add product to=shopping cart"),
("C","The system shall allow the Customer to specify the desired quantity of each item in the shopping cart.",
 "customer","specify","quantity","","per cart item","functional","test","FR01",
 "attr:CartItem.quantity","specify quantity"),
("C","Before finalizing checkout, the system shall verify the current inventory availability of every item in the shopping cart.",
 "system","verify","inventory","before checkout finalization","availability of every cart item","functional","test","FR02",
 "class:Inventory;attr:Inventory.quantity_on_hand;rel:Product-Inventory","initiate checkout;verify inventory availability;branch:all items in stock?"),
("C","If any cart item is out of stock, the system shall alert the Customer of the stock shortage.",
 "system","alert","customer","if any cart item out of stock","stock shortage","functional","test","FR02",
 "class:Customer","branch:all items in stock?;alert customer of stock shortage"),
("C","If any cart item is out of stock, the system shall halt the checkout transaction.",
 "system","halt","checkout","if any cart item out of stock","","functional","test","FR02",
 "","branch:all items in stock?;halt checkout"),
("C","Upon successful checkout confirmation, the system shall generate a new order in the draft state.",
 "system","generate","order","upon checkout confirmation","to_state=draft","functional","test","FR03",
 "class:Order;rel:Customer-Order;attr:Order.status;class:OrderStatus;attr:OrderStatus.DRAFT","generate order"),
("C","The system shall calculate the final total amount of each new order.",
 "system","calculate","total_amount","upon order generation","","functional","test","FR03",
 "attr:Order.total_amount;class:OrderLine;attr:OrderLine.quantity;attr:Product.unit_price;rel:Order-OrderLine;rel:OrderLine-Product","calculate total amount"),
("C","The system shall securely transmit the order total and transaction details to the external Payment Gateway for processing.",
 "system","transmit","payment","after order generation","request to PaymentGateway; securely; order total + transaction details","functional","test","FR04",
 "class:Payment;attr:Payment.amount;rel:Order-Payment","transmit payment request;lane:PaymentGateway;approve payment"),
("C","If the Payment Gateway confirms a successful transaction, the system shall transition the order to the placed state.",
 "system","transition","order","if payment approved","to_state=placed","functional","test","FR05",
 "attr:Order.status;attr:OrderStatus.PLACED;attr:Payment.status","branch:payment approved?;transition order to=placed"),
("C","If the Payment Gateway reports a declined transaction, the system shall transition the order to the payment failed state.",
 "system","transition","order","if payment declined","to_state=payment_failed","functional","test","FR06",
 "attr:Order.status;attr:OrderStatus.PAYMENT_FAILED;attr:Payment.status","branch:payment approved?;transition order to=payment_failed"),
("C","If the Payment Gateway reports a declined transaction, the system shall alert the Customer of the payment failure.",
 "system","alert","customer","if payment declined","payment failure","functional","test","FR06",
 "class:Customer","branch:payment approved?;alert customer of payment failure"),
("C","The system shall allow Warehouse staff to mark a placed order as picked once its items have been retrieved from the shelves.",
 "warehouse","transition","order","if order in placed state; items retrieved","to_state=picked","functional","test","FR07",
 "attr:Order.status;attr:OrderStatus.PICKED","lane:Warehouse;retrieve items;transition order to=picked"),
("C","The system shall allow Warehouse staff to mark a picked order as packed once all required items have been boxed.",
 "warehouse","transition","order","if all required items gathered","to_state=packed","functional","test","FR08",
 "attr:Order.status;attr:OrderStatus.PACKED","pack items;transition order to=packed"),
("C","The system shall allow Warehouse staff to mark a packed order as shipped once it has been handed over to an external carrier.",
 "warehouse","transition","order","on handover to external carrier","to_state=shipped","functional","test","FR09",
 "attr:Order.status;attr:OrderStatus.SHIPPED","ship order to=carrier;transition order to=shipped"),
("C","The system shall allow the Customer to cancel an order only while it is in the placed state and has not been marked as picked.",
 "customer","cancel","order","if order in placed state and not picked","","functional","test","FR10",
 "class:Order;attr:Order.status","branch:cancel before picking?;cancel order"),
("C","When a valid cancellation is made, the system shall transition the order to the cancelled state.",
 "system","transition","order","on valid cancellation","to_state=cancelled","functional","test","FR11",
 "attr:Order.status;attr:OrderStatus.CANCELLED","transition order to=cancelled"),
("C","When a valid cancellation is made, the system shall immediately instruct the Payment Gateway to execute a full reversal of funds.",
 "system","reverse","payment","on valid cancellation","via PaymentGateway; full amount; immediately","functional","test","FR11",
 "class:Payment","transmit reversal request;PaymentGateway:reverse payment"),
("C","The system shall allow the Customer to initiate a return request for a shipped order within a 30-day window.",
 "customer","initiate","return","if order shipped; within 30 days","","functional","test","FR12",
 "class:Return;attr:Return.requested_at;rel:Order-Return","branch:return within 30 days?;initiate return"),
("C","The system shall allow Warehouse staff to record the physical receipt of returned items.",
 "warehouse","receive","return","","returned items","functional","test","FR13",
 "class:Return","receive return"),
("C","The system shall allow Warehouse staff to approve returned items after receipt.",
 "warehouse","approve","return","after physical receipt of returned items","","functional","test","FR13",
 "class:Return","approve return"),
("C","Once the Warehouse approves the returned items, the system shall issue a refund to the Customer.",
 "system","reverse","payment","if return approved","refund to Customer","functional","test","FR13",
 "class:Refund;rel:Return-Refund","System:reverse payment"),
("C","The system shall allow Sales staff to search for an order by its unique order identifier.",
 "sales","search","order","","by order_id","functional","test","FR14",
 "attr:Order.order_id",""),
("C","The system shall display to Sales staff the current state of a retrieved order.",
 "sales","view","order","","current state","functional","test","FR14",
 "attr:Order.status",""),
("C","The system shall display to Sales staff the historical timeline of state changes of a retrieved order.",
 "sales","view","audit_log","","historical timeline of the order","functional","test","FR14",
 "class:AuditLog;rel:Order-AuditLog",""),
("C","The system shall allow Sales staff to correct a Customer's delivery address on an order before the order reaches the packed state.",
 "sales","correct","address","if order not yet packed","delivery address of the order","functional","test","FR15",
 "attr:Order.delivery_address",""),
("C","The system shall generate a daily summary report of total processed revenue and total number of shipped orders for Sales staff.",
 "system","generate","daily_report","daily","total processed revenue; shipped order count; for Sales","functional","test","FR16",
 "class:DailyReport;attr:DailyReport.total_revenue;attr:DailyReport.shipped_order_count",""),
# ---- NFR
("C","The system shall complete order search, cart update, and checkout submission requests with a 95th-percentile response time of no more than 2 seconds, measured at the API boundary under a nominal load of up to 500 concurrent sessions.",
 "system","respond","request","order search, cart update, checkout submission; <= 500 concurrent sessions","p95 <= 2 s; at API boundary","performance","test","NFR01","",""),
("C","The system shall sustain 2,000 concurrent user sessions while meeting the 2-second 95th-percentile response time, with a request error rate of no more than 0.1%.",
 "system","sustain","concurrent_session","","2000 sessions; p95 <= 2 s; error rate <= 0.1%","performance","test","NFR02","",""),
("C","The system shall encrypt all customer payment data using TLS 1.2 or higher in transit and AES-256 at rest.",
 "system","encrypt","payment","in transit and at rest","payment data; TLS >= 1.2; AES-256","security","test","NFR03","class:Payment",""),
("C","The system shall not store unencrypted primary account numbers in any log, database, or backup.",
 "system","prohibit","primary_account_number","","unencrypted; logs, databases, backups","security","inspection","NFR03","",""),
("C","The system shall record an immutable audit entry for every order state change, capturing the UTC timestamp with millisecond precision, the acting role, the prior state, and the resulting state, modifiable by no role.",
 "system","record","audit_log","on every order state change","immutable; timestamp UTC ms; acting role; prior state; resulting state; modifiable by no role","security","test","NFR04",
 "class:AuditLog;attr:AuditLog.timestamp;attr:AuditLog.actor_role;attr:AuditLog.prior_state;attr:AuditLog.resulting_state;rel:Order-AuditLog",""),
("C","The system shall retain audit entries for at least 12 months.",
 "system","retain","audit_log","",">= 12 months","security","inspection","NFR04","class:AuditLog",""),
("C","The system shall achieve at least 99.9% availability per calendar month, excluding scheduled maintenance windows announced at least 48 hours in advance.",
 "system","achieve","availability","per calendar month; excluding maintenance announced >= 48 h ahead",">= 99.9%","quality","analysis","NFR05","",""),
("C","The system shall time out payment authorization requests to the Payment Gateway after 30 seconds.",
 "system","timeout","payment","","authorization request; 30 s","quality","test","NFR06","class:Payment","PaymentGateway:approve payment"),
("C","The system shall ensure that a retried payment authorization for the same order results in no more than one charge against the customer's payment method.",
 "system","retry","payment","on retried authorization for the same order","at most one charge","quality","test","NFR06",
 "class:Payment;attr:Payment.gateway_reference","PaymentGateway:approve payment"),
("C","The system shall roll back any partially completed order transaction in full within 60 seconds of failure detection, leaving no order in an intermediate state and no discrepancy between financial records and inventory counts.",
 "system","rollback","order","on failure detection","partially completed transaction; within 60 s; in full; no intermediate state; financial records consistent with inventory","quality","test","NFR07",
 "class:Order;class:Inventory;class:Payment",""),
("C","The system shall support a 3x increase in peak daily order volume without modification to application code or data model, verified by load test against the projected peak.",
 "system","scale","order_volume","","3x peak daily volume; no code or data model change","quality","test","NFR08","",""),
# ---- Optional
("O","Each order shall comprise one or more order lines, each recording a product, its quantity, and its unit price.",
 "system","record","order_line","","1..* per order; quantity; unit price","functional","inspection","FR01;FR03",
 "class:OrderLine;attr:OrderLine.unit_price;attr:OrderLine.line_total;rel:Order-OrderLine;rel:OrderLine-Product",""),
("O","The system shall reject a cancellation request for an order that is not in the placed state or has already been picked, and inform the Customer.",
 "system","halt","order","if order not in placed state or already picked","cancellation request","functional","test","FR10","attr:Order.status","branch:cancel before picking?"),
("O","The system shall reject a return request submitted more than 30 days after shipment.",
 "system","halt","return","if more than 30 days after shipment","return request","functional","test","FR12","attr:Shipment.shipped_at","branch:return within 30 days?"),
("O","The system shall reject a delivery address correction for an order that has reached the packed state or later.",
 "system","halt","address","if order packed or later","delivery address correction","functional","test","FR15","attr:Order.delivery_address",""),
("O","When the Warehouse approves a return, the system shall transition the order to the returned state.",
 "system","transition","order","on return approval","to_state=returned","functional","test","FR13","attr:OrderStatus.RETURNED","transition order to=returned"),
("O","When a refund or payment reversal is completed, the system shall transition the order to the refunded state.",
 "system","transition","order","on refund or reversal completed","to_state=refunded","functional","test","FR11;FR13","attr:OrderStatus.REFUNDED","transition order to=refunded"),
("O","The system shall reserve inventory for the ordered quantities when an order is placed.",
 "system","reserve","inventory","on order placed","ordered quantities","functional","test","FR05;FR07;NFR07","attr:Inventory.quantity_reserved",""),
("O","The system shall release reserved inventory when an order is cancelled.",
 "system","release","inventory","on order cancelled","reserved quantities","functional","test","FR11;NFR07","attr:Inventory.quantity_reserved",""),
("O","The system shall record the carrier and tracking number of each shipment.",
 "system","record","shipment","on handover to external carrier","carrier; tracking number","functional","test","FR09",
 "class:Shipment;class:Carrier;attr:Shipment.tracking_number;rel:Order-Shipment;rel:Shipment-Carrier","ship order to=carrier"),
("O","The system shall alert the Customer when an order is shipped.",
 "system","alert","customer","on order shipped","","functional","test","FR09","class:Customer",""),
("O","The system shall interface with the external Payment Gateway through a secure API that supports payment authorization and full payment reversal.",
 "system","interface","payment_gateway","","secure API; authorization; full reversal","interface","inspection","FR04;FR11;NFR03",
 "class:Payment;class:Refund;rel:Payment-Refund;attr:Payment.gateway_reference","transmit payment request;transmit reversal request"),
("O","The system shall restrict order search, delivery address correction, and daily report access to users in the Sales role.",
 "system","restrict","sales_function","","role = Sales","security","test","FR14;FR15;FR16","",""),
]

# ---- 1. requirements
with open(f"{G}/gold-requirements.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(COLS)
    for i, r in enumerate(R, 1):
        w.writerow([f"GR-{i:02d}", *r[:10]])

# ---- 2. tier map (built from an untiered extraction)
sys.path.insert(0, f"{ROOT}/scripts")
from puml_to_inventory import parse_class, parse_activity, tier_key
cls_rows = parse_class(open(f"{G}/gold-class.puml").read())
act_rows = parse_activity(open(f"{G}/gold-activity.puml").read())

C_CLASS = {"Customer","ShoppingCart","Product","Inventory","Order","OrderLine","Payment","Return","AuditLog"}
C_ATTR = {"Product.unit_price","Inventory.quantity_on_hand","Order.order_id","Order.status","Order.total_amount",
          "Order.delivery_address","OrderLine.quantity","Payment.amount","Payment.status","Return.requested_at",
          "AuditLog.timestamp","AuditLog.actor_role","AuditLog.prior_state","AuditLog.resulting_state"}
C_REL = {"Customer-Order","Customer-ShoppingCart","Order-OrderLine","OrderLine-Product","Product-Inventory",
         "Order-Payment","Order-AuditLog","Order-Return"}
O_ACT = {("System","transition","order","to=returned"),("System","transition","order","to=refunded")}

tmap = {}
for r in cls_rows:
    t = r["element_type"]
    name = r["canonical_name"] if t != "attribute" else f"{r['owner_class']}.{r['canonical_name']}"
    tier = "C" if name in (C_CLASS if t == "class" else C_ATTR if t == "attribute" else C_REL) else "O"
    tmap[tier_key("class", r)] = ("class", tier)
for r in act_rows:
    t = r["element_type"]
    if t in ("start","end"): tier = "O"
    elif t == "swimlane": tier = "O" if r["swimlane"] == "System" else "C"
    elif t == "action": tier = "O" if (r["swimlane"], r["verb"], r["object"], r["detail"]) in O_ACT else "C"
    else: tier = "C"
    k = tier_key("activity", r)
    assert k not in tmap or tmap[k][1] == tier, f"conflicting tier for {k}"
    tmap[k] = ("activity", tier)
with open(f"{G}/gold-tier-map.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["diagram","key","tier"])
    for k,(d,t) in tmap.items(): w.writerow([d,k,t])

# ---- 3. element CSVs through the extractor CLI (same path agent output will take)
for kind, src, out in [("class","gold-class.puml","gold-class-elements.csv"),("activity","gold-activity.puml","gold-activity-elements.csv")]:
    subprocess.run([sys.executable, f"{ROOT}/scripts/puml_to_inventory.py", kind, f"{G}/{src}", f"{G}/{out}",
                    "--tier-map", f"{G}/gold-tier-map.csv"], check=True)

cls = list(csv.DictReader(open(f"{G}/gold-class-elements.csv")))
act = list(csv.DictReader(open(f"{G}/gold-activity-elements.csv")))

# ---- 4. traceability, resolving names -> ids
def res_class(ref):
    kind, name = ref.split(":", 1)
    for r in cls:
        if kind == "class" and r["element_type"] == "class" and r["canonical_name"] == name: return [r["element_id"]]
        if kind == "attr" and r["element_type"] == "attribute" and f"{r['owner_class']}.{r['canonical_name']}" == name: return [r["element_id"]]
        if kind == "rel" and r["element_type"] == "relationship" and r["canonical_name"] == name: return [r["element_id"]]
    raise KeyError(ref)
def res_act(ref):
    if ref.startswith("lane:"):
        ids = [r["element_id"] for r in act if r["element_type"] == "swimlane" and r["swimlane"] == ref[5:]]
    elif ref.startswith("branch:"):
        ids = [r["element_id"] for r in act if r["element_type"] == "branch" and r["detail"].startswith(ref[7:])]
    else:
        lane = None
        if ":" in ref.split(" ")[0]: lane, ref = ref.split(":", 1)
        verb, _, rest = ref.partition(" ")
        obj, _, det = rest.partition(" to=")
        ids = [r["element_id"] for r in act if r["element_type"] == "action" and r["verb"] == verb and r["object"] == obj
               and r["detail"] == (f"to={det}" if det else "") and (lane is None or r["swimlane"] == lane)]
    if not ids: raise KeyError(ref)
    return ids
used = set()
with open(f"{G}/gold-traceability.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["gold_req_id","source_input_ids","class_element_ids","activity_element_ids"])
    for i, r in enumerate(R, 1):
        c = [x for ref in filter(None, r[10].split(";")) for x in res_class(ref)]
        a = [x for ref in filter(None, r[11].split(";")) for x in res_act(ref)]
        used |= set(c) | set(a)
        w.writerow([f"GR-{i:02d}", r[9], ";".join(c), ";".join(a)])

# ---- 5. checks
need = {f"FR{i:02d}" for i in range(1,17)} | {f"NFR{i:02d}" for i in range(1,9)}
src = {s for r in R if r[0]=="C" for s in r[9].split(";")}
print("tiers req:", Counter(r[0] for r in R))
print("inputs without Core frame:", sorted(need - src))
print("untraced Core class elems:", [r["element_id"] for r in cls if r["tier"]=="C" and r["element_id"] not in used])
print("untraced Core activity elems:", [r["element_id"] for r in act if r["tier"]=="C" and r["element_id"] not in used])
print("req verbs outside ontology:", sorted({(r[3], r[0]) for r in R if r[3] not in VERBS}))
print("activity verbs outside ontology:", sorted({r["verb"] for r in act if r["element_type"]=="action" and r["verb"] not in VERBS}))
ents = set(ONT["entities"])
print("classes outside ontology entities:", [r["canonical_name"] for r in cls if r["element_type"]=="class" and r["canonical_name"] not in ents])
bad_attr = [f"{r['owner_class']}.{r['canonical_name']}" for r in cls if r["element_type"]=="attribute" and r["detail"]!="literal"
            and r["canonical_name"] not in ONT["entities"].get(r["owner_class"],{}).get("attributes",[])]
print("attributes not in ontology attribute list:", bad_attr)
states = set(ONT["states"]["order_lifecycle"]["canonical_sequence"]) | set(ONT["states"]["order_exceptions"]["canonical"])
lits = {r["canonical_name"].lower() for r in cls if r["detail"]=="literal"}
print("enum literals vs ontology states equal:", lits == states)
legal = {tuple(x) for x in ONT["states"]["legal_transitions"]}
print("Core C/E class/activity counts:", Counter((r["element_type"], r["tier"]) for r in cls+act))
