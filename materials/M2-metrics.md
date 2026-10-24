# Metrics và phương pháp chấm

**Phiên bản:** 2.0
**Ngày:** 2026-10-24
**Phạm vi:** định nghĩa metric, quy trình chấm Requirements, quy trình chấm Models.

Hai metric VMX chỉ được định nghĩa ở Phần 1; quy trình chấm chúng nằm ngoài
phạm vi tài liệu này vì đã có script riêng.

# Phần 1 — Metrics

## 1.1 Bảng metric

| Nhóm | Metric | Công thức |
|---|---|---|
| **Completeness** | Requirement Recall | Số gold AC cộng gold `NFR-` statement được agent phủ / Tổng gold AC cộng gold `NFR-` statement (**70**) |
| | Structural Semantic Recall | Số gold element (class, attribute, enum, literal, relationship) được agent match ngữ nghĩa / Tổng gold element (**50**) |
| | Behavioral Semantic Recall | Số gold element (action, object node, swimlane, transition) được agent match ngữ nghĩa / Tổng gold element (**39**) |
| | VMX Requirement Coverage | Số requirement có dòng VMX được điền — `US-` cần `Domain-Req-ID` **và** `Structural-Elements` khác rỗng, `NFR-` cần `Domain-Req-ID` khác rỗng / Tổng requirement liệt kê trong `requirements.json` |
| **Correctness** | Requirement Precision | Số AC cộng `NFR-` statement sinh ra được chấm đúng / Tổng AC cộng `NFR-` statement sinh ra (sau dedup) |
| | Structural Semantic Precision | Số element sinh ra được chấm đúng ngữ nghĩa / Tổng element sinh ra |
| | Behavioral Semantic Precision | Số element sinh ra được chấm đúng ngữ nghĩa / Tổng element sinh ra |
| | Structural Syntax Validity | Số element Structural hợp lệ cú pháp / Tổng element Structural |
| | Behavioral Syntax Validity | Số element Behavioral hợp lệ cú pháp / Tổng element Behavioral |
| | VMX Referential Integrity | Số tham chiếu VMX resolve được tới một item tồn tại / Tổng tham chiếu VMX |

## 1.2 Glossary

**Gold** — artifact tham chiếu do chuyên gia soạn (`G1` requirements, `G2`
structural, `G3` behavioral), dùng để đối chiếu.

**Semantically matched / correct** — được đánh giá là tương đương về nghĩa, không
phải khớp chuỗi chính xác (ví dụ `Client` ≈ `Customer`). Với relationship, cả hai
đầu mút và loại quan hệ đều phải khớp.

**VMX** — ma trận truy vết do agent sinh, ánh xạ mỗi requirement (`SRS-Req-ID`)
tới domain requirement nguồn (`Domain-Req-ID`), element structural và element
behavioral.

**Tham chiếu VMX** — một giá trị thu được bằng cách tách ô `Domain-Req-ID`,
`Structural-Elements` hoặc `Behavorial-Elements` theo dấu `;`, sau khi trim
khoảng trắng và loại trùng trong cùng ô. Cột `SRS-Req-ID` là định danh, không
phải tham chiếu, nên bị loại trừ. Ô rỗng không sinh tham chiếu nào.

> Lưu ý chính tả: tên cột trong schema là `Behavorial-Elements` (thiếu chữ `i`).
> Viết sai so với schema sẽ làm hỏng Referential Integrity vì so khớp theo tên cột.

**Resolve được tới item tồn tại** — tham chiếu khớp character-for-character với
một tên được khai báo trong chính submission của agent: một domain requirement id
trong file input đối với `Domain-Req-ID`; một class, enum hoặc `Class.attribute`
trong `structural.puml` của submission đối với `Structural-Elements`; một action
trong `behavioral.puml` của submission đối với `Behavorial-Elements`. Tồn tại
được xét với chính submission, **không bao giờ** với gold diagram — nên metric này
đo tính nhất quán nội tại chứ không đo độ giống gold.

## 1.3 Hai điều kiện correctness

Áp cho item sinh ra không phủ gold nào (Phần 2 §2.5) và cho element không match
gold nào (Phần 3 §3.6). Một item như vậy vẫn được tính đúng nếu thoả **cả hai**:

1. **Traceable** — truy được về một domain requirement hoặc một đoạn mô tả domain
   có thật, không phải chức năng tự bịa thêm.
2. **Consistent** — không mâu thuẫn với bất kỳ gold item nào khác. Ví dụ một AC
   sinh ra nói "an order may have multiple invoices" là inconsistent với
   `US-10-AC04` dù nó không khớp gold AC nào.

Điều kiện atomicity (mỗi AC một mệnh đề) **không** nằm trong bộ điều kiện này.
Lý do: độ mịn của AC là quy ước trình bày, không phải tính đúng đắn; và ca suy
biến mà atomicity định chặn — viết vài AC khổng lồ phủ mọi thứ — đã bị chặn sẵn
bởi hiệu ứng loãng cosine mô tả ở §2.2. Độ mịn được báo cáo như chỉ số chẩn đoán,
không dùng để chấm.

# Phần 2 — Requirements Grading

Chấm hai metric: Requirement Recall (com) và Requirement Precision (cor).

## 2.1 Tóm tắt quyết định

| Hạng mục | Quyết định |
|---|---|
| Đơn vị chấm | AC-level (từng acceptance criterion / từng NFR statement) |
| Mẫu số gold | **70** = 62 AC + 8 NFR |
| Embedding model | `sentence-transformers/all-mpnet-base-v2` |
| Threshold khởi điểm | 0.75, kèm sensitivity 0.70 / 0.75 / 0.80 / 0.85 |
| Phạm vi matching | Toàn cục (không chia theo US) |
| Lớp kiểm tra bổ sung | 3 trục: polarity, hướng/tên định danh, giá trị số |
| Trục 1 (polarity) | Rule-based + chấm tay phần rule không quyết được |
| Trục 2, 3 | Rule-based thuần (deterministic) |
| Rubric cho unmatched | LLM judge + validate trên mẫu human, báo cáo Cohen's κ |

## 2.2 Đơn vị chấm và mẫu số

### Đơn vị

Một requirement `US-` **không** được chấm như một khối. Câu user story chỉ nêu
một năng lực, không khẳng định điều gì kiểm chứng được trên hệ thống chạy. Đơn vị
chấm là **từng acceptance criterion**.

Một requirement `NFR-` mang ngưỡng định lượng ngay trong statement và không có
acceptance criteria. Đơn vị chấm là **chính statement đó**.

### Không merge AC

Không nối các AC của cùng một US thành một đoạn rồi so sánh. Ba lý do:

1. **Mất độ phân giải.** Cosine của đoạn dài bị chi phối bởi chủ đề chung chứ
   không bởi nội dung cụ thể. Hai đoạn cùng nói về đơn hàng luôn chứa dày đặc
   `order`, `order item`, `product`, `customer`, `quantity`, `unit price` nên
   similarity dồn về khoảng hẹp ~0.8–0.95 bất kể agent khẳng định điều gì. Ví dụ:
   agent chỉ phủ 2/6 AC của `US-03` vẫn cho cosine ~0.85–0.9 ở mức đoạn.
2. **Mất tính chất tỉ lệ.** Merge cho ra một điểm similarity duy nhất cho cả US.
   Nó không chia được thành tử số / mẫu số, nên không còn là recall theo định
   nghĩa mà trở thành "độ giống trung bình" — một đại lượng khác hẳn.
3. **Mất khả năng truy lỗi.** AC-level cho biết chính xác agent hỏng ở đâu ("bỏ
   sót toàn bộ ràng buộc composition của `US-03-AC06`", "bỏ sót 3/5 transition của
   `US-06-AC04`"). Đây là phần phân tích có giá trị nhất của empirical study.

Hiệu ứng ở điểm 1 cũng chính là cơ chế chặn ca agent viết AC gộp quá to: AC càng
dài thì cosine với từng gold AC ngắn càng loãng và tụt dưới ngưỡng.

### Mẫu số gold

Đếm từ `G1-requirements.json` v1.1:

| US | Số AC | US | Số AC |
|---|---|---|---|
| US-01 | 4 | US-09 | 3 |
| US-02 | 4 | US-10 | 6 |
| US-03 | 6 | US-11 | 6 |
| US-04 | 3 | US-12 | 3 |
| US-05 | 3 | US-13 | 5 |
| US-06 | 4 | US-14 | 4 |
| US-07 | 3 | US-15 | 5 |
| US-08 | 3 | | |

Tổng AC = 62. NFR-01 đến NFR-08 = 8 statement.

> **Mẫu số gold = 62 + 8 = 70.**

Prompt không còn giới hạn cận trên số AC mỗi story (chỉ còn cận dưới 3), nên
`|S|` — tổng số AC agent sinh ra — là biến tự do. Mẫu số gold không đổi.

## 2.3 Pipeline

```
gold (70)          gen (M)
    │                 │
    └────┬────────────┘
         ▼
  [B1] Encode + ma trận similarity toàn cục (70 × M)
         ▼
  [B2] Sinh tập candidate match (threshold)
         ▼
  [B3] Lớp kiểm tra 3 trục  ──► loại các cặp similarity cao nhưng sai nghĩa
         ▼
  ┌──────┴──────┐
  ▼             ▼
matched      unmatched
hợp lệ           │
  │              ├─► trùng lặp với gen khác ──► redundant (không tính)
  │              └─► còn lại ──► [B4] Rubric 2 điều kiện
  ▼                                      │
Recall = matched / 70                    ▼
Precision = (matched + rubric pass) / M_dedup
```

### B1 — Encode và dựng ma trận

Model: `sentence-transformers/all-mpnet-base-v2` (Apache 2.0, 768 chiều, mean
pooling).

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("all-mpnet-base-v2")
emb_gold = model.encode(gold_units, normalize_embeddings=True)   # 70 câu
emb_gen  = model.encode(gen_units,  normalize_embeddings=True)   # M câu
sim = util.cos_sim(emb_gold, emb_gen)                            # 70 × M
```

**Phạm vi là toàn cục.** Mỗi ô là cosine của *một* gold AC với *một* gen AC.
Không dựng 15 ma trận con theo từng US. Lý do: nếu ràng buộc theo US, một gen AC
viết đúng nội dung `US-03-AC06` nhưng agent xếp nhầm dưới `US-04` sẽ không bao giờ
match được và bị tính miss oan.

Nhãn US của agent **không** dùng làm ràng buộc, mà ghi lại làm cột chẩn đoán: báo
cáo tỉ lệ match cross-US như một finding riêng (agent hiểu đúng nội dung nhưng tổ
chức sai).

Vì ma trận được dựng đầy đủ, **thứ tự sắp xếp AC của agent không ảnh hưởng đến kết
quả** — phép matching bất biến với hoán vị hàng/cột.

### B2 — Sinh tập candidate

**Cho Recall:** không áp ràng buộc 1-1. Một gold AC được coi là có candidate nếu
tồn tại ít nhất một gen AC vượt threshold. Cho phép many-to-one (nhiều gen AC cùng
phủ một gold AC — agent tách nhỏ) và one-to-many (một gen AC phủ nhiều gold AC —
agent gộp). Recall về bản chất là bài toán phủ, không phải bài toán ghép đôi.

**Cho Precision:** chạy thêm matching 1-1 (Hungarian) chỉ nhằm phát hiện trùng
lặp. Nếu hai gen AC cùng khớp vào một gold AC đã được "tiêu thụ", cái thứ hai đánh
dấu `redundant`, không cộng điểm. Mục đích duy nhất của ràng buộc 1-1 ở đây là
chặn việc agent viết lại cùng một điều kiện ba lần để ăn ba điểm.

Threshold khởi điểm **0.75**. Báo cáo sensitivity ở 0.70 / 0.75 / 0.80 / 0.85.

### B3 — Lớp kiểm tra 3 trục

Embedding similarity không nhạy với ba khía cạnh quyết định tính đúng đắn của AC
trong domain state-machine. Mọi cặp vượt threshold đều phải qua lớp này. **Lớp này
áp cho cả Recall lẫn Precision** — nếu gold nói "rejects" mà gen viết "accepts" thì
gold AC đó *không* được phủ, tính là covered sẽ thổi phồng recall.

#### Trục 1 — Polarity

`G1` chứa nhiều cặp AC đối xứng dùng gần hệt bộ từ vựng, chỉ khác ở kết cục. Ví dụ
`US-06-AC01` ("sets its status to pending") và `US-06-AC02` ("rejects the request
and leaves the status unchanged").

Rule-based + chấm tay phần còn lại:

- Nhóm "từ chối": `rejects`, `leaves ... unchanged`, `registers no`, `does not`
- Nhóm "chấp nhận": `sets ... to`, `records`, `stores`, `accepts`

Bắt được keyword ở cả hai phía → so nhóm, quyết định tự động. Gen AC không khớp
keyword nào (agent diễn đạt khác, ví dụ "no state change occurs" hay "the
submission does not result in a persisted order") → chuyển sang chấm tay. Với quy
mô 70 item, phần này dự kiến chỉ còn vài trường hợp.

Các cặp dễ dính trục này: toàn bộ `US-04`, `US-07-AC01` vs `AC02`, `US-10-AC01` vs
`AC02`/`AC03`, `US-13-AC01` vs `AC03`, `US-15-AC01` vs `AC02`/`AC03`.

#### Trục 2 — Hướng và tên định danh

Rule-based thuần. Enum của domain là tập đóng và hữu hạn nên rule đạt độ chính xác
tuyệt đối; đây cũng là trục quan trọng nhất với domain state-machine nên cần tính
deterministic.

1. **Hướng transition.** Trích cặp `(from, to)` rồi so **có thứ tự**.
   `pending → filled` và `filled → pending` có cosine gần 1 nhưng một đúng một sai.
   `US-06-AC04` chứa 5 transition: `submitted→pending`, `pending→filled`,
   `pending→closed`, `filled→shipped`, `shipped→closed`.

2. **Tên status / enum / role.** So theo whitelist lấy từ `G1`:
   - Order status: `submitted | pending | filled | shipped | closed`
   - Invoice status: `issued | paid`
   - Payment status: `pending | completed | failed`
   - Payment method: `bank | card | cash`
   - Role: `Customer | OrderStaff | Accountant`

   Lưu ý dễ lẫn: `G1` dùng `completed` cho payment nhưng `paid` cho invoice. Role
   phải khớp đúng: `US-06/07/08/09/15` là OrderStaff; `US-10/13/14` là Accountant;
   `US-11/12` là Customer.

3. **Hướng cardinality.** `at most one` vs `at least one` vs `any number` vs
   `exactly one`. Xuất hiện ở `US-01-AC03`, `US-03-AC02`, `US-10-AC04`,
   `US-11-AC06`, `US-12-AC03`.

#### Trục 3 — Giá trị số và ngưỡng

Rule-based thuần. Chỉ áp cho NFR. Trích toàn bộ số + đơn vị từ cả hai phía, so
khớp chính xác, đồng thời so chiều bất đẳng thức (`at least` vs `at most`).

| NFR | Giá trị phải khớp |
|---|---|
| NFR-01 | 50 items, 2 giây, 95% |
| NFR-02 | 200 concurrent users, 20 submissions/giây |
| NFR-03 | 100% |
| NFR-05 | TLS 1.2 |
| NFR-06 | 12 tháng |
| NFR-07 | 99.5%, 24 giờ |
| NFR-08 | 15 phút |

Gen viết "within 3 seconds" hay "99.9%" vẫn cho cosine ~0.97 nhưng ngưỡng sai thì
NFR vô nghĩa.

#### Kết quả của lớp này

Lệch bất kỳ trục nào → cặp bị loại khỏi `matched`, ghi lý do vào log. **Báo cáo:**
số cặp vượt threshold cosine nhưng bị lớp này loại. Con số đó là bằng chứng thực
nghiệm cho chính quyết định thiết kế này.

### B4 — Rubric cho phần unmatched

Chỉ phục vụ Precision. Một item sinh ra không phủ gold nào vẫn có thể đúng, vì gold
không vét hết domain requirements. Xét theo hai điều kiện ở §1.3.

Phân biệt hai loại unmatched:

- **Mảnh của một gold AC composite** (agent tách `US-01-AC01` thành 3 AC con) →
  pass rubric → tính correct. Thiết kế hai nhánh đã hấp thụ sẵn trường hợp split,
  nên Precision không bị phạt oan.
- **Trùng lặp với một gen AC khác** → redundant, không cộng. Phát hiện bằng
  similarity *giữa các gen AC với nhau*, không phải với gold.

**Cách chấm: LLM judge + validate trên mẫu human.** Quy trình bắt buộc:

1. Prompt judge cố định, `temperature = 0`, log toàn bộ output.
2. Judge **khác họ model** với model đang được đánh giá (tránh self-preference
   bias). Không dùng cùng một model vừa làm generator vừa làm judge.
3. Pin version cụ thể của judge (snapshot, ví dụ `gpt-4o-2024-08-06`).
4. Lấy mẫu ngẫu nhiên từ tập unmatched, human chấm **blind**, tính **Cohen's κ**.
5. κ ≥ 0.6 → chạy LLM cho toàn bộ, báo cáo κ. κ < 0.6 → sửa prompt, lấy **mẫu mới
   (held-out)**, lặp lại. Không tính lại κ trên chính mẫu đã dùng để tinh chỉnh
   prompt (overfit, κ đẹp giả).
6. Khai báo prompt judge đầy đủ trong appendix.

> **Cỡ mẫu.** Cỡ mẫu thông lệ cho κ là 150–200 item. Tập unmatched dự kiến chỉ
> ~15–20 item, **thấp hơn ngưỡng này**, nên κ sẽ có khoảng tin cậy rất rộng. Hai
> cách xử lý, chọn một khi chạy thật:
> - Nếu chỉ đánh giá **một** model: human chấm toàn bộ unmatched, LLM judge chạy
>   song song để đối chiếu, báo cáo tỉ lệ đồng thuận như quan sát phụ chứ không gọi
>   là validation.
> - Nếu đánh giá **nhiều** model: gộp tập unmatched của tất cả model lại, khi đó
>   tổng số item đủ lớn để κ có ý nghĩa. Đây là phương án nên nhắm tới.

#### Về Cohen's κ

κ đo mức đồng thuận giữa hai người chấm **sau khi trừ phần đồng thuận do may mắn**:

```
κ = (p_o − p_e) / (1 − p_e)
```

`p_o` = tỉ lệ đồng thuận quan sát được. `p_e` = tỉ lệ đồng thuận kỳ vọng nếu cả hai
chấm ngẫu nhiên (tính từ phân phối biên của mỗi người).

Không dùng % agreement thuần vì: nếu 90% item thuộc nhãn "correct", hai người nhắm
mắt đoán "correct" hết vẫn đạt ~81% agreement. Ví dụ `p_o = 0.90`, `p_e = 0.81` →
κ = 0.47, chỉ ở mức trung bình dù nhìn 90% tưởng tốt.

Thang Landis & Koch: <0.20 kém · 0.21–0.40 yếu · 0.41–0.60 trung bình · 0.61–0.80
tốt · >0.80 rất tốt. Ngưỡng chấp nhận thông thường: **κ ≥ 0.6**.

## 2.4 Dedup trước khi tính Precision

Loại các gen AC gần trùng nhau. Nếu không, agent chỉ cần diễn đạt lại cùng một điều
kiện ba lần là Precision được cộng ba lần.

Tính similarity trong nội bộ tập gen (`M × M`), cặp nào vượt ngưỡng dedup (gợi ý
0.90, cao hơn threshold matching) thì giữ một, đánh dấu phần còn lại `redundant`.
Báo cáo số item bị dedup.

## 2.5 Công thức

Gọi `G` = tập gold unit (`|G| = 70`), `S` = tập gen unit sau dedup, `matched` = tập
gold unit có ít nhất một gen unit phủ **và** qua được cả 3 trục.

```
Recall    = |matched| / 70
Precision = ( |matched hợp lệ| + |unmatched đạt rubric| ) / |S|
```

Bất đối xứng cần lưu ý: không phải `matched` nào cũng vào tử số Precision (bị trục
1/2/3 loại), nhưng `unmatched` vẫn có thể vào tử số (đạt rubric).

**Báo cáo F1** bên cạnh hai số rời. Vì `|S|` là biến tự do của agent, chiến lược
viết ít AC nhưng chắc ăn sẽ cho Precision cao và Recall thấp; nhìn một metric sẽ
hiểu sai.

## 2.6 Khai báo trong paper

**Embedding:** tên model + **revision hash** trên HuggingFace (không chỉ tên); phiên
bản `sentence-transformers`; pooling strategy; có normalize vector trước khi tính
cosine hay không; threshold + bảng sensitivity.

**Lớp 3 trục:** framing đề xuất — *"Vì embedding similarity không nhạy với phủ định,
thứ tự đối số và giá trị số — các khía cạnh quyết định tính đúng đắn của AC trong
domain state-machine — chúng tôi bổ sung một lớp kiểm tra rule-based trên ba khía
cạnh này."* Không viết "chúng tôi dùng 3 trục" như một khái niệm có sẵn; đây là
thiết kế riêng của nghiên cứu này. Citation hỗ trợ: CheckList (Ribeiro et al., ACL
2020), trong đó negation và number perturbation là hai capability được liệt kê rõ.
Kèm số liệu: bao nhiêu cặp vượt threshold cosine nhưng bị lớp này loại.

**LLM judge:** model + snapshot version, temperature, prompt đầy đủ (appendix); cỡ
mẫu human, Cohen's κ, ghi rõ nếu cỡ mẫu dưới ngưỡng thông lệ.

**Chẩn đoán:** phân phối số AC mỗi story và độ dài AC, đặt cạnh gold (15 story, 62
AC, trung bình 4.1). Model lệch hẳn khỏi vùng này thì điểm phải đọc kèm bối cảnh đó.

# Phần 3 — Models Grading

Chấm bốn metric: Structural / Behavioral Semantic Recall và Precision. Syntax
Validity đóng vai trò cổng chặn (§3.1).

## 3.1 Cổng syntax

Chạy parser syntax có sẵn trên `structural.puml` và `behavioral.puml`.

**Structural Syntax Validity hoặc Behavioral Syntax Validity < 1.0 → dừng.** Các
metric semantic của mô hình đó ghi `n/a`, không ghi 0. Phân biệt "agent mô hình hoá
sai" với "không đo được" — gộp hai thứ này vào cùng giá trị 0 sẽ làm hỏng diễn giải
bảng kết quả và làm sai trung bình khi tổng hợp nhiều model.

Báo cáo riêng số model bị chặn ở cổng này, kèm loại lỗi cú pháp.

## 3.2 Kiểm kê gold

### Structural — `G2`, tổng 50 element

| Loại | Số | Chi tiết |
|---|---|---|
| Class | 6 | Customer, Product, Order, OrderItem, Invoice, Payment |
| Attribute | 22 | Customer 4, Product 4, Order 4, OrderItem 2, Invoice 4, Payment 4 |
| Enum | 4 | OrderStatus, InvoiceStatus, PaymentStatus, PaymentMethod |
| Enum literal | 13 | OrderStatus 5, InvoiceStatus 2, PaymentStatus 3, PaymentMethod 3 |
| Relationship | 5 | Customer–Order, Order–OrderItem, Order–Invoice, OrderItem–Product, Invoice–Payment |

Sáu mũi tên `..>` từ class sang enum **không** tính là relationship: chúng biểu diễn
quan hệ kiểu dữ liệu, đã được tính qua kiểu của attribute.

### Behavioral — `G3`, tổng 39 element

| Loại | Số | Chi tiết |
|---|---|---|
| Action | 9 | Make an Order, Receive order, Fill Order, Ship Order, Send Invoice, Make Payment, Reject Payment, Accept Payment, Close Order |
| Object node | 10 | Order[submitted/pending/filled/shipped/closed], Invoice[issued/paid], Payment[pending/failed/completed] |
| Swimlane assignment | 9 | một gán lane cho mỗi action |
| Transition | 11 | xem §3.4 |

Ba quy ước đếm, áp cho cả gold lẫn submission:

**Gộp theo nhãn phân biệt.** `G3` có `Make Payment` và `Payment [pending]` xuất hiện
hai lần (một ngoài vòng lặp, một trong thân). Đếm theo instance sẽ phạt agent nào vẽ
vòng lặp mà không lặp lại node, tức phạt một lựa chọn trình bày.

**Control node không vào mẫu số.** Hai lý do. Thứ nhất, chúng phần lớn là ngầm định
và không có nhãn — `if/else/endif` sinh ra một decision và một merge nhưng merge
không hề xuất hiện trong source. Không có text thì embedding vô dụng, muốn ghép
chúng chỉ còn cách giải đồng hình đồ thị trên bộ khung điều khiển. Thứ hai, số lượng
chúng phụ thuộc cú pháp chứ không phụ thuộc nghiệp vụ: `G3` dùng `split`/`end split`
bốn lần thuần tuý để gắn object node, một agent mô hình hoá đúng y hệt mà không dùng
`split` sẽ bị trừ vì một lựa chọn gõ phím. Control được kiểm bằng checklist ở §3.5.

**`<style>` block và dòng `title` bị bỏ qua**, không vào mẫu số. Agent sẽ không sinh
ra chúng.

## 3.3 Pipeline

```
gold element          gen element
      │                    │
      └────────┬───────────┘
               ▼
    [B1] Cổng syntax ──► fail ──► n/a, dừng
               ▼
    [B2] Parse → danh sách element / Graph IR
               ▼
    [B3] Match: embedding + Hungarian, ràng buộc loại
               ▼
    [B4] Lớp rule-based ──► loại cặp sai kiểu / sai hướng / sai loại quan hệ
               ▼
    [B5] Recall = matched / (50 hoặc 39)
         Precision = (matched + rubric pass) / tổng element sinh ra
```

Cùng hình dạng với Phần 2: embedding sinh candidate, rule-based quyết định, phần dư
mới dùng rubric. Không thêm cơ chế mới.

**Ràng buộc loại ở B3:** class chỉ match class, attribute chỉ match attribute,
action chỉ match action. Không cho phép một action match một decision chỉ vì văn bản
gần giống nhau.

## 3.4 Quy tắc match

### Structural

**Class** — match theo embedding tên, ngưỡng dùng chung với Phần 2 (0.75).
`Client ≈ Customer` hợp lệ.

**Attribute** — hai tầng: chỉ xét sau khi class chủ đã match. Tránh `Invoice.date`
khớp nhầm `Payment.date`. Match cần cả tên tương đương **và** kiểu tương thích:

| Gold | Chấp nhận | Cảnh báo | Sai |
|---|---|---|---|
| `Decimal` | `BigDecimal`, `Numeric`, `Money` | `Float`, `Double` | `String`, `Integer` |
| `Integer` | `Int`, `Long` | — | `String`, `Decimal` |
| `Date` | `DateTime`, `LocalDate` | `Timestamp` | `String` |
| `String` | `Text`, `VarChar` | — | kiểu số |

Kiểm kiểu quan trọng vì `REQ-F-46` bắt buộc mọi giá trị tiền tệ là decimal.

**Enum** — match theo tên + so tập literal. Literal là tập đóng nên so exact sau
chuẩn hoá case. Điểm dễ sai: gold dùng `completed` cho payment nhưng `paid` cho
invoice.

**Relationship** — chỉ tính match khi đủ bốn điều kiện: hai đầu mút đã match; **loại
quan hệ** đúng; **multiplicity hai đầu** đúng; **hướng** đúng. `Order *-- OrderItem`
mà agent viết thành association thường là sai, vì prompt yêu cầu tường minh
composition khi entity không tồn tại độc lập (`REQ-F-07`). `"1" -- "0..*"` viết
ngược cũng là sai.

### Behavioral

**Action** — embedding + ràng buộc loại.

**Object node** — so cặp `(entity, status)`. Entity match theo embedding, status so
exact theo whitelist ở Phần 2 trục 2. `Order [filled]` và `Order [shipped]` có cosine
rất cao nhưng là hai element khác nhau.

**Swimlane assignment** — so lane của action đã match. Whitelist role:
`Customer | OrderStaff | Accountant`. Đây là kiểm tra deterministic rẻ nhất trong cả
phần này, và nó bắt trực tiếp một yêu cầu của prompt.

**Transition** — định nghĩa là cặp action liên tiếp theo luồng điều khiển, **bỏ qua
control node và object node nằm giữa**. Nhờ vậy đo được thứ tự và rẽ nhánh mà không
phải căn chỉnh control node.

11 transition của gold:

| # | From | Guard | To |
|---|---|---|---|
| 1 | Make an Order | | Receive order |
| 2 | Receive order | accepted | Fill Order |
| 3 | Receive order | declined | Close Order |
| 4 | Fill Order | | Ship Order |
| 5 | Fill Order | | Send Invoice |
| 6 | Send Invoice | | Make Payment |
| 7 | Make Payment | declined | Reject Payment |
| 8 | Reject Payment | | Make Payment |
| 9 | Make Payment | authorized | Accept Payment |
| 10 | Ship Order | | Close Order |
| 11 | Accept Payment | | Close Order |

Transition chỉ tính match khi hai đầu mút đã match **và** guard tương đương. Đây là
thứ bắt lỗi đảo nhánh: đảo `accepted`/`declined` giữ nguyên số node và cạnh nhưng sai
hoàn toàn nghiệp vụ. Transition 4 và 5 là hai nhánh của fork, không có thứ tự giữa
chúng.

## 3.5 Checklist control

Sáu mục pass/fail, báo cáo riêng, không có công thức tổng hợp. Mỗi mục rút thẳng từ
một yêu cầu của prompt nên đây là kiểm tra tuân thủ spec, không phải heuristic tự chế.

| # | Kiểm tra | Nguồn |
|---|---|---|
| 1 | Đúng một initial node, ít nhất một final node | Prompt, Diagram 2 |
| 2 | Mọi cạnh ra khỏi decision đều có guard tường minh | Prompt, Diagram 2 |
| 3 | Có fork và join khớp nhau cho nhánh ship ∥ invoice | `REQ-F-31` |
| 4 | Có vòng lặp retry payment: back edge, đúng thân, đúng điều kiện thoát | `REQ-F-34` |
| 5 | Mỗi action đổi trạng thái có object node `Entity [status]` theo sau | Prompt, Diagram 2 |
| 6 | Mọi action nằm trong swimlane của role thực hiện nó | Prompt, Diagram 2 |

Mục 5 và 6 trùng một phần với mẫu số §3.2 — ở đó đo độ phủ nội dung, ở đây đo tính
hệ thống (có áp dụng nhất quán cho mọi action hay chỉ vài chỗ).

## 3.6 Element không match gold

Xét theo hai điều kiện correctness ở §1.3, giống Phần 2. Một class `Address` tách
riêng khỏi `Customer` là traceable (`REQ-F-01`) và consistent → tính đúng, dù gold
không có. Một class `Warehouse` không truy được về domain requirement nào → không
tính.

## 3.7 Ba vấn đề chặn

**Parser chưa đọc được chính gold.** Prototype hiện chưa hỗ trợ `detach` và
`end merge`. `G3` dùng `detach` hai lần và `split`/`split again`/`end split` bốn
lần. Phải mở rộng parser trước khi chạy bất cứ thứ gì.

**Decision trong gold không có label.** `G3` viết `if () then ([accepted])` và
`while () is ([declined])` — điều kiện rỗng, toàn bộ ngữ nghĩa nằm ở guard. Nếu
thuật toán chấm similarity của *label* decision thì agent viết `if (Order valid?)`
sẽ bị trừ oan dù đúng. **Chấm guard, không chấm label decision.**

**Phân biệt Fork/Join với Decision/Merge.** Decision chọn một nhánh theo điều kiện;
Fork kích hoạt các luồng song song. Merge hợp nhất các nhánh thay thế mà không đồng
bộ; Join đồng bộ các nhánh đến. Agent thay Fork/Join bằng Decision/Merge là lỗi mô
hình hoá dù số node và cạnh có thể bằng nhau — checklist mục 3 bắt ca này.

## 3.8 Nằm ngoài phạm vi

**Điểm tổng hợp có trọng số** dạng `S = 0.35·F1_node + 0.40·F1_edge + 0.25·F1_sem`:
không dùng. Trọng số là tuỳ ý, không có cơ sở trong chuẩn UML, và gộp lại thì mất
thông tin chẩn đoán mà không được gì. Báo cáo từng thành phần.

**Graph Edit Distance:** chi phí tính toán cao, và với đồ thị cỡ này không nói thêm
gì ngoài node/transition matching. Để ở future work.

**Behavioral conformance qua Petri net / PM4Py:** để ở future work. Nếu làm, báo cáo
thành metric riêng trước khi quyết định có đưa vào tổng hợp hay không.

## 3.9 Khai báo trong paper

Dùng chung phần embedding với §2.6 nếu cùng model và threshold; nếu khác, khai báo
riêng.

Thêm: bảng tương đương kiểu dữ liệu đầy đủ; danh sách cú pháp PlantUML mà parser hỗ
trợ và không hỗ trợ; số model bị chặn ở cổng syntax kèm loại lỗi; kết quả checklist
control dạng bảng pass/fail theo từng model.

---

# Tồn đọng

1. **Mở rộng parser** cho `detach`, `split`/`end split`, `end merge` trước khi chạy —
   hiện không parse được gold `G3`.
2. **Bảng tương đương kiểu dữ liệu** ở §3.4 mới là bản nháp, cần chốt trước khi chạy.
3. **Ngưỡng matching cho Models** đang dùng chung 0.75 với Requirements. Cần kiểm
   xem tên class và tên action (chuỗi ngắn 1–3 từ) có cần ngưỡng khác chuỗi dài của
   AC hay không — sensitivity analysis riêng.
4. **Cỡ mẫu κ** cho phần rubric của Models cũng nhỏ như Phần 2; gộp chung tập
   unmatched của cả Requirements và Models để tính κ là một phương án cần cân nhắc.