# Order Management System – User Manual

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Running the System](#running-the-system)
5. [User Roles and Capabilities](#user-roles-and-capabilities)
6. [Typical Workflows](#typical-workflows)
7. [Viewing Documentation and Diagrams](#viewing-documentation-and-diagrams)
8. [Troubleshooting \& FAQ](#troubleshooting--faq)
9. [Appendix: Glossary](#appendix-glossary)

---

## Overview
The **Order Management System (OMS)** is a reference implementation of a complete order‑to‑cash workflow covering customers, order staff, and accountants. It demonstrates how to:
- Store and manage customers, products, orders, invoices, and payments.
- Enforce business rules such as status transitions, multiplicities, and validation constraints.
- Provide traceability from high‑level domain requirements to functional user stories, UML diagrams, and a requirements matrix.

The artefacts produced for this system are:
- `srs.md` – a full Software Requirements Specification.
- `structural.puml` – a PlantUML class diagram (structural model).
- `behavioral.puml` – a PlantUML activity diagram (behavioural model).
- `requirements.json` – machine‑readable list of all functional and non‑functional requirements.
- `VMX.csv` – traceability matrix linking SRS requirements to domain requirements and diagram elements.

The manual below explains how to set up the environment, explore the artefacts, and (optionally) run a small Python demo that mimics the OMS behaviour.

---

## Prerequisites
To view the documentation and run the optional demo you need:

| Tool | Minimum version |
|------|-----------------|
| **Python** | 3.11 |
| **uv** (Python package manager) | latest (installed via `pip install uv` or the official installer) |
| **Git** (optional, for cloning the repository) |
| **Web browser** – any modern browser that can render Markdown and PlantUML images |
| **PlantUML** – the diagrams are plain PlantUML source; you can render them locally using the PlantUML CLI or an online server (e.g., https://www.plantuml.com/plantuml/). |

---

## Installation
The repository contains only documentation and PlantUML files – there is no compiled binary. Follow these steps to set up a Python virtual environment and install the optional demo dependencies.

```bash
# 1. Clone the repository (if you haven't already)
git clone <repository‑url> oms-demo
cd oms-demo

# 2. Initialise a virtual environment using uv (the repository already includes a uv lock file)
uv venv .venv --python 3.11
source .venv/bin/activate

# 3. Install the demo dependencies (if you want to run the Python script)
uv pip install -r requirements.txt  # the file may be empty; uv will still create the environment
```
If you do not wish to run the Python demo, you can skip steps 2‑3 and simply open the Markdown files directly.

---

## Running the System
The artefacts are static; the “system” is represented by the UML models and the SRS. However, a lightweight Python script (`demo.py`) is provided to illustrate the core business rules.

```bash
# Activate the virtual environment (if not already active)
source .venv/bin/activate

# Run the demo script
python demo.py
```
The script will:
1. Create a few sample customers, products, and orders.
2. Walk through the status transitions defined in the functional requirements (e.g., `submitted → pending → filled → shipped → closed`).
3. Print out each step, showing validation messages when a rule is violated (e.g., trying to ship an order that is not `filled`).

> **Note**: The demo is illustrative only; it does not persist data to a database.

---

## User Roles and Capabilities
The OMS defines three distinct roles. Each role’s capabilities are expressed as user stories in the SRS (`srs.md`). Below is a concise mapping:

| Role | Primary Capabilities (selected user stories) |
|------|----------------------------------------------|
| **Customer** | - Submit an order (`US‑13`).<br>- Submit a payment against an invoice (`US‑32`). |
| **OrderStaff** | - Receive an order (`US‑18`).<br>- Mark order as filled (`US‑20`).<br>- Decline an order (`US‑22`).<br>- Set order to shipped (`US‑25`).<br>- Raise an invoice (`US‑28`).<br>- Close an order (`US‑40`). |
| **Accountant** | - Raise an invoice (`US‑28`).<br>- Confirm a payment (`US‑35`).<br>- Reject a payment (`US‑38`). |

For the full list of user stories, see the **Functional Requirements** section of `srs.md`.

---

## Typical Workflows
### 1. Customer places an order
1. Customer selects existing products and specifies quantities.
2. System validates the customer exists, each product exists, and at least one order‑item is present.
3. System records the order with status **submitted** and computes the total amount.
4. Customer receives a confirmation.

### 2. Order staff processes the order
1. **Receive** – status changes from **submitted** to **pending**.
2. **Validate** – optional checks (stock, address). If OK, **fill** the order (status → **filled**).
3. **Ship** – once filled, staff can set status to **shipped**.
4. **Close** – after the invoice is **paid** and the order is **shipped**, staff closes the order (status → **closed**).

### 3. Accountant handles invoicing & payments
1. After an order is **filled** (or **shipped**), accountant raises an **invoice** (status **issued**).
2. Customer submits a **payment** (status **pending**).
3. Accountant **confirms** the payment → payment status **completed**, invoice status becomes **paid**.
4. If payment fails, accountant can **reject** it → status **failed**; a new payment may be submitted.

All state transitions are enforced by the system (see user stories `US‑49` and `US‑50`).

---

## Viewing Documentation and Diagrams
- Open `srs.md` in any Markdown viewer (VS Code, GitHub, typora, etc.) to read the full specification.
- To render the UML diagrams:
  1. Copy the contents of `structural.puml` or `behavioral.puml` into an online PlantUML editor (e.g., https://plantuml.com/online).
  2. Or, install PlantUML locally (`brew install plantuml` on macOS or `sudo apt install plantuml` on Linux) and run:
     ```bash
     plantuml structural.puml
     plantuml behavioral.puml
     ```
     This will generate PNG/SVG files next to the source files.
- `requirements.json` can be opened with any JSON viewer; it lists every requirement and its acceptance criteria.
- `VMX.csv` can be opened in a spreadsheet program (Excel, LibreOffice Calc) to see traceability from each SRS requirement back to the original domain requirement IDs.

---

## Troubleshooting \& FAQ
**Q: I get a `ModuleNotFoundError` when running `demo.py`.**
- Ensure the virtual environment is activated (`source .venv/bin/activate`).
- Install dependencies with `uv pip install -r requirements.txt`.

**Q: PlantUML does not render the diagrams.**
- Verify you have Java installed (PlantUML requires a JRE). `java -version` should show 11+.
- Use the online PlantUML server if local rendering fails.

**Q: Where are the data stored?**
- The demo script uses in‑memory Python objects; the SRS does not prescribe a persistence mechanism.

**Q: How do I extend the system with a database?**
- Follow the class diagram in `structural.puml` to design tables (e.g., `Customer`, `Product`, `Order`, `OrderItem`, `Invoice`, `Payment`).
- Implement the status‑transition logic as described in the user stories.

---

## Appendix – Glossary
- **Order** – A request from a customer containing one or more order items.
- **OrderItem** – A line‑item linking a product to an order with quantity and unit price.
- **Invoice** – A billing document generated for an order.
- **Payment** – A monetary transaction against an invoice.
- **Status** – The current lifecycle state of an order, invoice, or payment (e.g., `submitted`, `pending`, `filled`).
- **Payment Method** – One of `bank`, `card`, or `cash`.
- **Pending** – A temporary state awaiting confirmation.
- **Issued** – Invoice state after creation, before payment.
- **Completed** – Payment state after successful confirmation.
- **Failed** – Payment state after rejection.

---

*End of manual.*