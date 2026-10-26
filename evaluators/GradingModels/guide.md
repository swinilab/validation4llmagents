# Hướng dẫn GradingModels cho người mới hoàn toàn

Tài liệu này dành cho người **chưa biết gì** về module `GradingModels`. Đọc xong
bạn sẽ biết: module này để làm gì, các khái niệm cần biết, cách chạy lần đầu, cách
đọc kết quả, và cách xử lý khi pipeline "dừng lại chờ bạn".

> **Cập nhật đường dẫn (đọc trước):** module không còn giữ workspace riêng. Các
> ví dụ bên dưới dùng cách chạy và đường dẫn cũ; hãy đổi như sau:
>
> | Cũ | Mới |
> |---|---|
> | `--run-id <id>` (đọc `submissions/<id>/`) | `--submission <thư mục chứa 2 file .puml> --out <thư mục RUN>` |
> | `evaluators/GradingModels/run/<id>/` | `<RUN>/grading_models/run/` |
> | `evaluators/GradingModels/review/<id>/` | `<RUN>/grading_models/review/` (không còn nằm trong git) |
> | `gold/G2-…`, `gold/G3-…`, `gold/domain-requirements.md` | mục `gold:` trong `config.yaml` (hiện trỏ vào `materials/`) |
>
> Từ pipeline chính: `uv run main.py --phase val --grade models`. Chi tiết ở
> [README.md](README.md).

> Các tài liệu khác trong thư mục này dành cho người đã quen:
> - [README.md](README.md) — tóm tắt kỹ thuật, bố cục mã nguồn.
> - [workflow.md](workflow.md) — sơ đồ luồng chi tiết.
> - [../../materials/m2-model-grading-spec.md](../../materials/m2-model-grading-spec.md) — spec đầy đủ (nguồn chân lý).

---

## Mục lục

1. [Module này làm gì?](#1-module-này-làm-gì)
2. [Các khái niệm cần biết trước](#2-các-khái-niệm-cần-biết-trước)
3. [Chuẩn bị](#3-chuẩn-bị)
4. [Chạy lần đầu (5 phút)](#4-chạy-lần-đầu-5-phút)
5. [Đọc kết quả](#5-đọc-kết-quả)
6. [Chấm bài của model thật](#6-chấm-bài-của-model-thật)
7. [Khi pipeline dừng lại chờ bạn (`NEEDS_REVIEW`)](#7-khi-pipeline-dừng-lại-chờ-bạn-needs_review)
8. [Các tuỳ chọn dòng lệnh](#8-các-tuỳ-chọn-dòng-lệnh)
9. [Pipeline bên trong làm gì? (tóm tắt 8 bước)](#9-pipeline-bên-trong-làm-gì-tóm-tắt-8-bước)
10. [Chạy test](#10-chạy-test)
11. [Lỗi thường gặp](#11-lỗi-thường-gặp)
12. [Hỏi nhanh](#12-hỏi-nhanh)
13. [Bản đồ thư mục](#13-bản-đồ-thư-mục)

---

## 1. Module này làm gì?

Dự án này cho các LLM (ví dụ `gpt-oss-120b`) sinh ra **hai sơ đồ UML** cho hệ thống
quản lý đơn hàng "OrderMan", viết bằng ngôn ngữ **PlantUML**:

| File | Loại sơ đồ | Mô tả |
| --- | --- | --- |
| `structural.puml` | Sơ đồ cấu trúc (class diagram) | Có những class, thuộc tính, enum, quan hệ nào |
| `behavioral.puml` | Sơ đồ hành vi (activity diagram) | Quy trình xử lý đơn hàng diễn ra theo thứ tự nào, ai làm gì |

**GradingModels là "giám khảo" chấm hai sơ đồ đó.** Nó so sánh sơ đồ của model với
**đáp án chuẩn (gold)** do con người làm sẵn, rồi cho ra các con số:

- **Recall** (độ phủ): trong đáp án chuẩn có bao nhiêu phần model vẽ đúng?
- **Precision** (độ chính xác): trong những gì model vẽ, bao nhiêu phần là đúng?
- **F1**: số trung bình hài hoà của hai số trên.
- **Syntax Validity**: file `.puml` viết có đúng cú pháp không?
- **Control checklist**: 6 mục đạt/không đạt (ví dụ: có đúng một node bắt đầu không).

Ví dụ trực quan: đáp án chuẩn có 50 "thứ" trong sơ đồ cấu trúc. Model vẽ ra 54 thứ,
trong đó 37 thứ khớp đáp án. Khi đó Recall = 37/50 = 0.74 (phủ được 74% đáp án) và
Precision ≈ 37/54 = 0.69 (69% những gì nó vẽ là đúng). (Precision thực tế còn cộng
thêm các phần "ngoài đáp án nhưng vẫn hợp lý", xem mục 9, bước S7.)

---

## 2. Các khái niệm cần biết trước

Đọc kỹ mục này, mọi thứ phía sau sẽ dễ hiểu hơn nhiều.

### 2.1. Gold, submission, run_id

| Thuật ngữ | Nghĩa | Nằm ở đâu |
| --- | --- | --- |
| **Gold** | Đáp án chuẩn, đã "đóng băng", không được sửa | `gold/G2-structural.puml`, `gold/G3-behavioral.puml` |
| **Submission** | Bài làm của một model cần chấm | `submissions/<run_id>/structural.puml` và `behavioral.puml` |
| **run_id** | Tên đặt cho một lần chấm, cũng là tên thư mục của submission. Ví dụ `gold-identity`, `gpt-oss-run01` | Do bạn tự đặt |

### 2.2. "Element" — đơn vị để đếm

Pipeline không so sánh file văn bản, mà **tách mỗi sơ đồ thành các element** rồi đếm
element nào khớp.

**Sơ đồ cấu trúc — gold có đúng 50 element:**

| Loại (kind) | Ví dụ | Số lượng trong gold |
| --- | --- | --- |
| `class` | `Order`, `Customer` | 6 |
| `attribute` | `Order.total : Decimal` | 22 |
| `enum` | `OrderStatus` | 4 |
| `literal` | `OrderStatus.pending` | 13 |
| `relationship` | `Order *-- OrderItem` | 5 |

**Sơ đồ hành vi — gold có đúng 39 element:**

| Loại (kind) | Ví dụ | Số lượng trong gold |
| --- | --- | --- |
| `action` | `Fill Order` | 9 |
| `object_node` | `Order [filled]` | 10 |
| `swimlane` | làn (người) thực hiện hành động đó | 9 |
| `transition` | mũi tên từ hành động này sang hành động kế tiếp | 11 |

Các node điều khiển (decision, fork, join, start, end) **không** được đếm làm
element. Chúng chỉ được kiểm tra riêng bằng "control checklist".

### 2.3. Gate (cổng cú pháp) và `n/a`

Trước khi chấm nội dung, pipeline kiểm tra file `.puml` có **parse được hoàn toàn**
không (validity phải đúng `1.0`).

- Parse sạch → được chấm.
- Có dù chỉ một lỗi → **không chấm** nội dung sơ đồ đó. Kết quả ghi là chuỗi `"n/a"`.

> **Rất quan trọng:** `n/a` **khác** `0`.
> - `0` = "đã đo, không khớp cái nào".
> - `n/a` = "chưa đo được, vì file lỗi cú pháp".
>
> Gate fail **không phải** là lỗi của pipeline. Pipeline vẫn chạy xong và thoát với
> mã `0`.

Hai sơ đồ được chấm **độc lập**: structural lỗi thì behavioral vẫn được chấm bình thường.

### 2.4. Cosine similarity và ngưỡng (threshold)

Để biết `class OrderItem` của model có "giống" `class OrderItem` của gold không,
pipeline dùng mô hình embedding (`all-mpnet-base-v2`) biến mỗi nhãn thành một vector
số, rồi đo **độ giống nhau (cosine)** từ 0 đến 1.

Cặp nào có cosine ≥ **ngưỡng** thì mới được xét là "ứng viên khớp". Cấu hình hiện tại
(trong `config.yaml`):

```yaml
threshold_models: 0.75                   # ngưỡng chính
sweep_models: [0.70, 0.75, 0.80, 0.85]   # chạy thử cả 4 ngưỡng để xem độ nhạy
```

Kết quả được báo cáo cho **cả bốn ngưỡng**, nhưng bài báo dùng ngưỡng chính 0.75.

### 2.5. Rule layer (tầng luật)

Embedding chỉ biết "giống về nghĩa", mà nhiều chỗ "giống nghĩa" vẫn **sai**. Ví dụ
`Order [filled]` và `Order [shipped]` có embedding gần như y hệt, nhưng là hai trạng
thái khác nhau. Vì vậy sau khi ghép cặp, **tầng luật** kiểm tra thêm bằng quy tắc cứng:

| Kiểm tra | Ví dụ lỗi bị bắt |
| --- | --- |
| Kiểu dữ liệu thuộc tính | `Order.total` là `String` thay vì `Decimal` |
| Quan hệ (loại, bội số, hướng) | `Order *-- OrderItem` (composition) bị vẽ thành association thường |
| Trạng thái của object node | `Payment [paid]` trong khi đúng phải là `Payment [completed]` |
| Swimlane (làn) | `Fill Order` bị đặt vào làn `Customer` thay vì `OrderStaff` |
| Guard (điều kiện nhánh) | Hoán đổi `accepted` và `declined` → nghĩa nghiệp vụ bị đảo ngược |

Cặp nào **trượt** tầng luật thì **không tính là khớp**.

### 2.6. Ledger và "MANUAL" — chỗ cần con người

Có vài trường hợp máy **không tự quyết được** (ví dụ thuộc tính tiền dùng `Float`
thay vì `Decimal` — có thể chấp nhận hoặc không). Khi đó pipeline:

1. Ghi câu hỏi vào một file CSV (gọi là **ledger**) trong `review/<run_id>/`.
2. **Dừng lại**, báo `NEEDS_REVIEW` (mã thoát `2`).
3. Bạn mở CSV, điền `PASS` hoặc `FAIL`, rồi **chạy lại đúng lệnh cũ**.

Pipeline **không bao giờ đứng chờ bạn gõ phím**. Nó luôn thoát ra, bạn điền xong rồi
chạy lại. Đây là điểm khác biệt hay làm người mới bối rối, xem kỹ mục 7.

### 2.7. Hai thư mục "cache" và "review"

| Thư mục | Ai ghi | Xoá được không? | Commit git? |
| --- | --- | --- | --- |
| `run/<run_id>/` | Pipeline (kết quả trung gian) | **Được.** Xoá đi chạy lại ra đúng kết quả cũ | Không (đã nằm trong `.gitignore`) |
| `review/<run_id>/` | Con người (và pipeline thêm dòng câu hỏi trống) | **KHÔNG.** Mất là mất công chấm tay | **Có** |

Pipeline **không bao giờ ghi đè** một ô bạn đã điền.

---

## 3. Chuẩn bị

### 3.1. Yêu cầu

- Python 3.11 (xem `.python-version`).
- Virtual environment `.venv` ở thư mục gốc dự án, đã cài sẵn `numpy`, `scipy`,
  `sentence-transformers`, `pyyaml`, `requests`, `pytest`.
- Lần đầu chạy, thư viện `sentence-transformers` cần **tải model embedding**
  `sentence-transformers/all-mpnet-base-v2` về máy (khoảng vài trăm MB), nên cần có
  mạng. Các lần sau dùng bản đã tải.
- **Không cần** API key nếu bạn chưa bật LLM judge (xem mục 7.3).

### 3.2. Mở đúng terminal

Dự án nằm trong WSL Ubuntu (`/home/swe/validation4llmagents`) và `.venv` là môi
trường Linux (`.venv/bin/python`). Vì vậy hãy chạy lệnh **trong terminal WSL/Ubuntu**,
không phải PowerShell thuần của Windows.

```bash
cd /home/swe/validation4llmagents
```

Mọi lệnh trong tài liệu này giả định bạn đang đứng ở **thư mục gốc dự án** này.

> Lưu ý: [README.md](README.md) trong thư mục này ghi lệnh là
> `GradingModels/run.py`. Đường dẫn đúng hiện tại là
> `evaluators/GradingModels/run.py` như dưới đây.

---

## 4. Chạy lần đầu (5 phút)

Repo đã có sẵn một submission mẫu tên `gold-identity`: chính là **đáp án chuẩn được
nộp lại như một bài làm**. Chấm bài này phải ra điểm tuyệt đối. Đây là cách tốt nhất
để kiểm tra mọi thứ hoạt động.

```bash
.venv/bin/python evaluators/GradingModels/run.py --run-id gold-identity
```

Kết quả mong đợi: in ra chữ

```
DONE
```

và mã thoát là `0` (kiểm tra bằng `echo $?`). Khi kiểm tra tài liệu này, lệnh trên
chạy khoảng 17 giây.

Chuyện gì vừa xảy ra:

1. Pipeline đọc `gold/` và `submissions/gold-identity/`.
2. Chạy lần lượt các bước S0 → S7 (mục 9).
3. Ghi kết quả vào `evaluators/GradingModels/run/gold-identity/`.

Chạy lại lần nữa sẽ **nhanh hơn**, vì mỗi bước tự bỏ qua nếu file kết quả của nó đã
có. Muốn tính lại từ đầu thì thêm `--force` (hoặc xoá thư mục `run/gold-identity/`).

---

## 5. Đọc kết quả

Mọi kết quả nằm trong `evaluators/GradingModels/run/<run_id>/`. File quan trọng nhất
là **`07_metrics.json`**.

### 5.1. Các file trong `run/<run_id>/`

| File | Bước | Nội dung |
| --- | --- | --- |
| `00_syntax.json` | S0 | Cú pháp: validity, dòng nào bị từ chối |
| `01_elements.json` | S1 | Danh sách element của gold và của submission |
| `02_sim.npy`, `02_sim_index.json` | S2 | Ma trận độ giống (cosine) |
| `03_candidates.json` | S3 | Các cặp ứng viên vượt ngưỡng |
| `04_match.json` | S4 | Kết quả ghép cặp 1–1 |
| `05_axis.json` | S5 | Kết quả tầng luật (PASS / FAIL / MANUAL cho từng cặp) |
| `06_control.json` | S6 | Control checklist 6 mục |
| `07_metrics.json` | S7 | **Kết quả cuối** |
| `manifest.json` | — | "Biên bản" lần chạy: cấu hình, phiên bản, thời gian |

### 5.2. Đọc `07_metrics.json`

Rút gọn từ lần chạy `gold-identity`:

```json
{
  "run_id": "gold-identity",
  "primary_threshold": 0.75,
  "status": "final",
  "pending_type": 0,
  "pending_guard": 0,
  "pending_rubric": 0,
  "control": { "item_1": "pass", "...": "...", "item_6": "pass" },
  "structural": {
    "syntax_validity": 1.0,
    "gate": "pass",
    "n_gen": 50,
    "gold_total": 50,
    "sweep": [
      { "threshold": 0.75, "recall": 1.0, "precision": 1.0, "f1": 1.0,
        "matched_gold": 50, "matched_gen": 50 }
    ],
    "recall": 1.0, "precision": 1.0, "f1": 1.0
  },
  "behavioral": { "...": "cấu trúc tương tự, gold_total = 39" }
}
```

Giải nghĩa từng trường:

| Trường | Ý nghĩa |
| --- | --- |
| `status` | `"final"` = không còn gì chờ người, số liệu chính thức. `"provisional"` = còn mục chờ nên số liệu là **tạm thời** |
| `pending_type` / `pending_guard` / `pending_rubric` | Số dòng đang chờ bạn điền (mục 7). Muốn `final` thì cả ba phải bằng 0 |
| `control.item_1 … item_6` | 6 mục checklist: `pass`, `fail` hoặc `n/a` |
| `structural.gate` / `behavioral.gate` | `pass` = parse sạch và đã được chấm; ngược lại là bị chặn |
| `n_gen` | Số element model vẽ ra (sau khi gộp các nhãn trùng) |
| `gold_total` | Số element của đáp án (50 hoặc 39) |
| `sweep` | Recall / Precision / F1 tại **từng** ngưỡng |
| `recall`, `precision`, `f1` ở ngoài cùng | Giá trị ở ngưỡng chính (0.75). Có thể là `"n/a"` nếu gate fail |
| `matched_gold` | Số element gold được model phủ được |
| `matched_gen` | Số element model vẽ mà khớp gold |
| `diagnostics` | Chẩn đoán chi tiết: tầng luật loại cặp nào, vì sao, v.v. |

Công thức (đơn giản hoá):

```
Recall    = matched_gold / gold_total
Precision = (matched_gen + rubric_pass) / n_gen
F1        = 2 * P * R / (P + R)        (bằng 0 nếu P + R = 0)
```

`rubric_pass` là số element model vẽ **thêm ngoài đáp án nhưng vẫn hợp lý** (mục 9,
bước S7).

### 5.3. Khi nào nên nghi ngờ kết quả?

- `status` là `"provisional"` → còn mục chờ người; Recall là **cận dưới**.
- `gate` không phải `pass` → số liệu là `"n/a"`, hãy xem `00_syntax.json` để biết
  dòng nào gây lỗi.
- `diagnostics.rule_rejections` khác rỗng → có cặp "giống nghĩa nhưng sai luật". Đây
  chính là chỗ cho thấy model sai ở đâu.

---

## 6. Chấm bài của model thật

### Bước 1: Tạo thư mục submission

Đặt tên `run_id` bất kỳ (nên dùng chữ thường, số, dấu gạch ngang), tạo thư mục và
chép hai file `.puml` vào:

```bash
mkdir -p submissions/gpt-oss-run01
cp /duong/dan/structural.puml submissions/gpt-oss-run01/
cp /duong/dan/behavioral.puml submissions/gpt-oss-run01/
```

Cấu trúc bắt buộc:

```
submissions/
└── gpt-oss-run01/          <-- run_id
    ├── structural.puml
    └── behavioral.puml
```

Thiếu một trong hai file thì sơ đồ đó nhận `n/a` (gate `missing`), sơ đồ kia vẫn được chấm.

> Thư mục `submissions/` là **bất biến**: đã nộp thì đừng sửa file bên trong. Muốn
> thử bản khác, tạo một `run_id` mới.

### Bước 2: Chạy

```bash
.venv/bin/python evaluators/GradingModels/run.py --run-id gpt-oss-run01
```

### Bước 3: Xem mã thoát

```bash
echo $?
```

| Mã | Chữ in ra | Nghĩa | Bạn làm gì |
| --- | --- | --- | --- |
| `0` | `DONE` | Xong | Đọc `run/gpt-oss-run01/07_metrics.json` |
| `2` | `NEEDS_REVIEW` | Cần bạn điền file review | Làm theo mục 7 |
| `1` | `FAILED: ...` | Lỗi thật | Xem mục 11 |

---

## 7. Khi pipeline dừng lại chờ bạn (`NEEDS_REVIEW`)

Pipeline in ra dòng kiểu:

```
review needed: /home/swe/validation4llmagents/evaluators/GradingModels/review/gpt-oss-run01/type_ledger.csv (3 empty row(s))
NEEDS_REVIEW
```

Mở file được in ra, điền, lưu, rồi **chạy lại đúng lệnh cũ** (cùng `--run-id`). Pipeline
dùng lại cache nên các bước đầu không phải tính lại (kể cả embedding tốn thời gian).

### 7.1. `type_ledger.csv` — kiểu dữ liệu thuộc tính

Xuất hiện khi kiểu dữ liệu của model nằm ở vùng "cảnh báo" hoặc không có trong bảng
`rules.yaml`. Ví dụ gold dùng `Decimal` còn model dùng `Float`.

Các cột:

```
gold_id,gen_id,gold_type,gen_type,cosine,verdict,reviewer,timestamp,note
```

Bạn chỉ điền các cột **`verdict`**, **`reviewer`**, **`timestamp`** (và `note` nếu muốn):

| Cột | Điền gì |
| --- | --- |
| `verdict` | **Đúng chữ `PASS` hoặc `FAIL`** (viết hoa). Giá trị khác sẽ làm cả lần chạy bị `FAILED` |
| `reviewer` | Tên bạn |
| `timestamp` | Thời điểm, ví dụ `2026-10-26T09:30` |

Ví dụ một dòng sau khi điền:

```csv
A:Order.total,A:Order.total,Decimal,Float,1.0,FAIL,minh,2026-10-26T09:30,tiền phải dùng Decimal (REQ-F-46)
```

### 7.2. `guard_ledger.csv` — điều kiện nhánh (guard)

Xuất hiện khi guard của model không khớp bảng đồng nghĩa (alias) trong `rules.yaml`
(ví dụ gold là `accepted`, model viết `confirmed`). Cách điền giống `type_ledger.csv`:

```
gold_id,gen_id,gold_guard,gen_guard,path_detail,verdict,reviewer,timestamp,note
```

Chỉ điền `verdict` (`PASS`/`FAIL`), `reviewer`, `timestamp`. Hãy dựa vào cột
`gold_guard`, `gen_guard`, `path_detail` để quyết định hai guard có cùng nghĩa
nghiệp vụ không.

### 7.3. `rubric_human.csv` và LLM judge — element ngoài đáp án

Model có thể vẽ thêm element **không có trong gold** nhưng vẫn đúng (ví dụ tách
class `Address` ra khỏi `Customer`). Bước S6/S7 "rubric" xử lý chúng bằng hai câu hỏi:

1. **Traceable:** có truy được về một yêu cầu trong `gold/domain-requirements.md` không?
2. **Consistent:** có mâu thuẫn với element nào của gold không?

Việc này do **LLM judge** chấm, và người chấm mù một mẫu nhỏ (`kappa_sample_size: 30`)
để đo độ đồng thuận (Cohen's κ, cần ≥ 0.60).

**Trạng thái hiện tại của dự án:** trong `config.yaml`, `judge_model: null`, tức là
**chưa có judge**. Khi đó mọi element ngoài gold được để ở trạng thái *pending* chứ
không bị chấm bừa bằng 0 (một số liệu trung thực hơn). Muốn bật judge:

1. Điền `judge_model` trong `config.yaml` bằng một **snapshot cố định** của model,
   thuộc **họ model khác** với model đang bị chấm.
2. Đặt biến môi trường `OPENROUTER_API_KEY` (không gõ key vào file hay chat).

`rubric_human.csv` chỉ chứa các cột `element_id, kind, label, traceable, consistent,
reviewer, timestamp`. Cố ý **không có cột nào của LLM** để bạn chấm mù. Đừng cố tìm
cách xem nhãn LLM trước khi điền.

### 7.4. Chỉ muốn xem số tạm, không muốn điền gì?

Dùng `--on-pending provisional`:

```bash
.venv/bin/python evaluators/GradingModels/run.py --run-id gpt-oss-run01 --on-pending provisional
```

Mọi mục đang chờ được coi là **không khớp** (`not_covered`), pipeline chạy tới cùng và
đánh dấu `"status": "provisional"`. Số này chỉ là **cận dưới** của Recall, đừng đưa
vào kết quả chính thức.

---

## 8. Các tuỳ chọn dòng lệnh

```bash
.venv/bin/python evaluators/GradingModels/run.py --run-id <run_id> \
    [--diagram structural|behavioral|both] \
    [--on-pending halt|provisional] \
    [--stage all|S0|S1|...|S7] \
    [--force]
```

| Tuỳ chọn | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `--run-id` | (bắt buộc) | Tên thư mục trong `submissions/` |
| `--diagram` | `both` | Chỉ chấm một sơ đồ (`structural` hoặc `behavioral`) |
| `--on-pending` | `halt` | `halt`: dừng chờ người. `provisional`: chạy tiếp với số tạm |
| `--stage` | `all` | Chỉ chạy một bước (xem lưu ý bên dưới) |
| `--force` | tắt | Tính lại các bước dù đã có file kết quả |

> Lưu ý về `--stage`: tên bước trong `--stage` theo **spec**, không theo tên file. Ví
> dụ `--stage S7` là bước metrics, nhưng code nằm ở `s8_metrics.py`. Người mới nên
> luôn để `--stage all`.

Ví dụ:

```bash
# Chỉ chấm sơ đồ hành vi
.venv/bin/python evaluators/GradingModels/run.py --run-id gpt-oss-run01 --diagram behavioral

# Tính lại tất cả từ đầu
.venv/bin/python evaluators/GradingModels/run.py --run-id gpt-oss-run01 --force
```

---

## 9. Pipeline bên trong làm gì? (tóm tắt 8 bước)

Bạn không cần thuộc phần này để chạy. Nó chỉ giúp hiểu khi đọc các file trong
`run/<run_id>/`. Sơ đồ đầy đủ có trong [workflow.md](workflow.md).

| Bước | Tên | Làm gì | Ai làm |
| --- | --- | --- | --- |
| **S0** | Syntax gate | Parse PlantUML, tính `validity`. Dưới 1.0 thì sơ đồ đó thành `n/a` | Tự động |
| **S1** | Elements | Tách sơ đồ thành element; **gộp các nhãn trùng nhau**; kiểm tra gold đúng 50 / 39 element | Tự động |
| **S2** | Similarity | Tính embedding và cosine giữa element gold và element của model | Tự động |
| **S3** | Candidates | Lấy mọi cặp có cosine ≥ ngưỡng thấp nhất (0.70) làm ứng viên | Tự động |
| **S4** | Matching | Ghép cặp **1–1** bằng thuật toán Hungarian, theo thứ tự phụ thuộc (class trước, rồi thuộc tính của class đó...) | Tự động |
| **S5** | Rule layer | Kiểm tra luật cứng (kiểu, quan hệ, trạng thái, làn, guard). Cặp mơ hồ chuyển cho người | Tự động + người |
| **S6** | Control checklist | 6 mục đạt/không đạt | Tự động |
| **S7** | Rubric + Metrics | Chấm element ngoài gold; tính Recall / Precision / F1 | LLM judge + người |

Sáu mục của control checklist:

1. Có đúng một node start và ít nhất một node end.
2. Mọi nhánh ra khỏi decision đều có guard rõ ràng.
3. Có cặp fork/join đúng cho nhánh "giao hàng" song song với "lập hoá đơn".
4. Có vòng lặp thanh toán lại (back edge, thân vòng, điều kiện thoát đúng).
5. Mọi hành động đổi trạng thái đều có object node `Entity [status]` theo sau.
6. Mọi hành động nằm đúng swimlane của người thực hiện.

Những điều pipeline **cố ý không làm**:

- **Không có điểm tổng hợp có trọng số.** Chỉ báo các thành phần riêng.
- **Không gộp nhãn bằng độ giống ngữ nghĩa.** Chỉ gộp khi nhãn *giống hệt* nhau
  (vì `Order [filled]` và `Order [shipped]` rất giống nhau nhưng là hai thứ khác nhau).
- **Không có con số "ma thuật" trong code.** Mọi ngưỡng ở `config.yaml`, mọi từ vựng
  ở `rules.yaml`.

---

## 10. Chạy test

Bộ test kiểm tra pipeline đúng theo spec (ví dụ: chấm gold với chính nó phải ra điểm
tuyệt đối; hoán đổi `accepted`/`declined` phải bị bắt; gate lỗi phải ra `n/a` chứ
không phải `0`).

```bash
.venv/bin/python -m pytest evaluators/GradingModels/tests -q
```

Các test tự tạo thư mục submission tạm rồi dọn đi, nên không làm bẩn thư mục
`submissions/` của bạn. Test này tải model embedding và chạy pipeline nhiều lần nên
có thể mất vài phút.

Nên chạy test **sau mỗi lần bạn sửa** `rules.yaml`, `config.yaml` hoặc mã nguồn.

---

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `FAILED: submission directory not found: ...` | `--run-id` sai tên hoặc chưa tạo thư mục | Kiểm tra `ls submissions/` và tạo đúng cấu trúc ở mục 6 |
| `FAILED: gold ... does not parse at validity 1.0` | File gold bị sửa hỏng hoặc parser bị đổi | Khôi phục `gold/` bằng git. **Không sửa gold để "cho chạy được"** |
| `FAILED:` kèm lời nhắc về inventory (50 / 39) | Parser phân loại element sai, tổng số lệch | Báo cho người phụ trách module; không bỏ qua |
| `FAILED:` nêu một dòng ledger, verdict không hợp lệ | Bạn điền `verdict` khác `PASS`/`FAIL` (gõ `pass`, `Pass`, `OK`, để dấu cách...) | Sửa đúng thành `PASS` hoặc `FAIL` rồi chạy lại |
| `FAILED:` nhắc `OPENROUTER_API_KEY` | Đã đặt `judge_model` nhưng chưa có biến môi trường key | `export OPENROUTER_API_KEY=...` trong terminal của bạn rồi chạy lại |
| `FAILED:` kèm `ConfigError` | `config.yaml` hoặc `rules.yaml` thiếu key hoặc thừa key lạ (ví dụ `dedup_threshold`) | Xoá/thêm key cho đúng. Loader cố ý không dùng giá trị mặc định ngầm |
| Kết quả toàn `n/a` | Gate cú pháp fail | Mở `run/<run_id>/00_syntax.json`, xem `rejections` để biết dòng nào và mã lỗi gì |
| Chạy lần đầu rất lâu / báo lỗi mạng | Đang tải model embedding | Cần mạng ở lần đầu; chờ tải xong |
| Sửa `submissions/` nhưng kết quả không đổi | Cache cũ của bước đã chạy | Thêm `--force` hoặc xoá `run/<run_id>/` |
| `command not found` hoặc lỗi `.venv/bin/python` | Đang ở PowerShell Windows, hoặc sai thư mục | Mở terminal WSL và `cd /home/swe/validation4llmagents` |

Các mã lỗi cú pháp trong `00_syntax.json`: `unsupported_construct`, `unbalanced_block`,
`unknown_keyword`, `malformed_edge`, `malformed_attribute`, `duplicate_declaration`.

---

## 12. Hỏi nhanh

**Tôi có thể xoá `run/` không?**
Được. Nó là cache. Xoá rồi chạy lại ra đúng kết quả cũ, miễn là `review/` còn nguyên.

**Tôi có thể xoá `review/` không?**
Không. Đó là công chấm tay của bạn.

**Chạy lại có làm mất những gì tôi đã điền không?**
Không. Pipeline không bao giờ sửa một dòng đã có `verdict`. Nó chỉ thêm dòng câu hỏi
trống mới nếu có cặp mới cần hỏi.

**Vì sao điểm gate fail là `n/a` mà không phải 0?**
Vì `0` khẳng định "model vẽ ra thứ chẳng liên quan gì đến đáp án", còn gate fail chỉ
nói "parser không đọc nổi file". Hai chuyện đó khác nhau, gộp chung sẽ làm sai các
giá trị trung bình giữa nhiều model.

**Vì sao phải chạy 4 ngưỡng 0.70–0.85?**
Vì nhãn trong sơ đồ rất ngắn (1–3 từ) nên khoảng cosine khác với câu văn dài. Chạy
cả bốn ngưỡng để xem kết quả nhạy với ngưỡng đến đâu. Việc chốt ngưỡng chính thức
vẫn là một mục còn mở trong spec (mục 16.3).

**Con người chỉ phải chấm tay khi nào?**
Chỉ có hai loại: (1) các dòng trong hai ledger `type_ledger.csv` / `guard_ledger.csv`,
(2) mẫu mù `rubric_human.csv` để đo κ. Phán quyết ledger chỉ làm **một lần** ở ngưỡng
thấp nhất và dùng lại cho cả bốn ngưỡng.

**Còn mục nào chưa chốt trước khi chấm chính thức?**
Theo [README.md](README.md): đóng băng bảng tương thích kiểu `type_table`
(§16.2), phân tích độ nhạy ngưỡng (§16.3), chọn `kappa_pool` giữa `per_section` và
`pooled` (§16.4), xác nhận cách xử lý alias guard `approved` (§16.5), và đặt
`judge_model` (hiện là `null`). Mỗi mục này làm đổi con số đã công bố.

---

## 13. Bản đồ thư mục

```
validation4llmagents/
├── config.yaml                     <- ngưỡng, model embedding, chính sách chạy
├── gold/                           <- ĐÁP ÁN CHUẨN (đóng băng, đừng sửa)
│   ├── G2-structural.puml
│   ├── G3-behavioral.puml
│   └── domain-requirements.md
├── submissions/
│   └── <run_id>/                   <- bài làm cần chấm (bất biến)
│       ├── structural.puml
│       └── behavioral.puml
└── evaluators/GradingModels/
    ├── guide.md                    <- tài liệu này
    ├── README.md  workflow.md      <- tài liệu kỹ thuật
    ├── rules.yaml                  <- từ vựng đóng: bảng kiểu, alias guard, trạng thái hợp lệ, vai trò
    ├── run.py                      <- ĐIỂM VÀO: file bạn chạy
    ├── configload.py               <- đọc config.yaml / rules.yaml, báo lỗi nếu thiếu key
    ├── ledgers.py                  <- đọc/ghi CSV review, không ghi đè ô đã điền
    ├── judge.py                    <- gọi LLM judge (khi đã đặt judge_model)
    ├── parser/                     <- đọc PlantUML thành đồ thị
    ├── stages/                     <- các bước S0..S7
    ├── tests/                      <- bộ test nghiệm thu
    ├── run/<run_id>/               <- CACHE (xoá được, không commit)
    └── review/<run_id>/            <- do NGƯỜI điền (KHÔNG xoá, có commit)
        ├── type_ledger.csv
        ├── guard_ledger.csv
        ├── rubric_llm.csv
        └── rubric_human.csv
```

### Tóm tắt một dòng

> Bỏ hai file `.puml` vào `submissions/<run_id>/`, chạy
> `.venv/bin/python evaluators/GradingModels/run.py --run-id <run_id>`, nếu thấy
> `NEEDS_REVIEW` thì điền CSV được in ra rồi chạy lại, nếu thấy `DONE` thì đọc
> `run/<run_id>/07_metrics.json`.
