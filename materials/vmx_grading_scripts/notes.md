# Cách chấm VMX — đặc tả logic

Tài liệu mô tả cách một bài nộp được chấm trên hai chỉ số VMX. Mô tả ở mức logic:
chấm cái gì, dựa vào đâu, quy ước ra sao. Không nói về cài đặt.

---

## 1. Đầu vào của việc chấm

Mỗi lần chấm làm việc trên **một bài nộp** của agent, gồm ba thứ:

| Thứ | Vai trò |
| --- | --- |
| `VMX.csv` | Đối tượng được chấm |
| `structural.puml` | Nơi tra cứu tên phần tử cấu trúc |
| `behavioral.puml` | Nơi tra cứu tên phần tử hành vi |

Cộng thêm một thứ cố định, dùng chung cho mọi bài nộp:

| Thứ | Vai trò |
| --- | --- |
| `domain_requirements.json` | Nơi tra cứu mã requirement đầu vào (32 FR + 8 NFR) |

Nguyên tắc quan trọng: hai tập tra cứu về diagram được lấy từ **chính bài nộp
đó**, không lấy từ gold. Việc chấm không so sánh diagram của agent với diagram
của gold ở bất cứ đâu trong hai chỉ số này.

---

## 2. Ba tập tên hợp lệ

Trước khi chấm, dựng ba tập tên. Mỗi cột của VMX tra vào đúng một tập.

**Tập nguồn** — toàn bộ mã `REQ-F-xx` và `REQ-N-xx` trong file domain
requirements. Cố định 40 phần tử.

**Tập cấu trúc** — đọc từ `structural.puml` của bài nộp, gồm ba loại:
- tên class
- tên enum
- tên thuộc tính, viết dạng `Class.attribute`

Không gồm relationship. Lý do: relationship không có tên tự nhiên trong
PlantUML, nên muốn tham chiếu tới nó phải bịa ra một quy ước đặt tên, và agent
không có cách nào đoán đúng quy ước đó. Tham chiếu sẽ hỏng vì lý do hình thức
chứ không phải vì nội dung sai — tức là chỉ số đo nhầm thứ.

**Tập hành vi** — đọc từ `behavioral.puml` của bài nộp, chỉ gồm **tên action**.

Không gồm decision, object node, hay control node (initial, final, fork, join,
merge). Cùng lý do với relationship: những loại node này không mang tên trong
cú pháp PlantUML.

---

## 3. Chỉ số 1 — VMX Requirement Coverage (Completeness)

Đo trên **dòng**. Mỗi dòng của VMX đạt hoặc không đạt.

Luật phụ thuộc loại requirement, nhận biết qua tiền tố mã:

| Loại | Điều kiện đạt |
| --- | --- |
| `US-` | Ô Source khác rỗng **và** ô Structural khác rỗng |
| `NFR-` | Ô Source khác rỗng |

```
coverage = số dòng đạt / tổng số dòng
```

Ô Behavioral không tham gia chỉ số này, kể cả với user story.

**Vì sao US không bắt buộc ô Behavioral.** Có những requirement về cấu trúc dữ
liệu tĩnh không có bước nào trong luồng hoạt động — ví dụ "lưu tên, địa chỉ, số
điện thoại của khách hàng". Bắt chúng phải trỏ tới một action sẽ khuyến khích
agent nhét action thừa vào diagram chỉ để lấp ô, làm hỏng chính diagram.

**Vì sao NFR không bắt buộc ô Structural.** Requirement chất lượng như "khả dụng
99.5% mỗi tháng" không hiện thực bởi class hay action nào. Ô Source là liên kết
duy nhất có nghĩa.

**Vì sao vẫn bắt US phải có ô Structural.** Mọi user story đều nói về dữ liệu mà
hệ thống lưu hoặc thay đổi, nên luôn có ít nhất một class, enum hoặc thuộc tính
đứng sau. Ô này rỗng là dấu hiệu agent không nối requirement với mô hình.

---

## 4. Chỉ số 2 — VMX Referential Integrity (Correctness)

Đo trên **tham chiếu**, không phải trên dòng.

Một tham chiếu = một giá trị sau khi tách ô bằng dấu `;`. Đếm ở cả ba cột
Source, Structural, Behavioral. Ô rỗng không sinh tham chiếu nào.

Mỗi tham chiếu được tra vào tập tương ứng với cột của nó. Tra thấy thì đạt,
không thấy thì hỏng.

```
integrity = số tham chiếu tra thấy / tổng số tham chiếu
```

**"Tồn tại" nghĩa là tồn tại trong chính bài nộp đó.** Nếu agent vẽ một class
mà gold không có, rồi trỏ VMX tới class đó một cách nhất quán, tham chiếu vẫn
đạt. Chỉ số này đo tính tự nhất quán giữa VMX và hai diagram cùng bài nộp,
không đo độ giống gold.

Hệ quả: chỉ số bắt được lỗi agent trỏ tới thứ không tồn tại — ví dụ VMX ghi
`Customer.email` trong khi diagram chỉ khai báo `name`, `address`, `phone`,
`bankAccount`. Đây là dạng hallucination phổ biến nhất.

Ngược lại, chỉ số **không** bắt được lỗi agent vẽ thừa một thực thể rồi trỏ
tới nó nhất quán. Lỗi đó thuộc phần chấm chất lượng mô hình, không thuộc hai
chỉ số VMX.

**So khớp là so khớp chuỗi chính xác.** Tên trong ô VMX phải trùng từng ký tự
với tên khai báo trong puml. Điều này được nêu rõ trong mô tả cột của prompt,
nên agent biết trước luật.

---

## 5. Quan hệ giữa hai chỉ số

Hai chỉ số đo hai thứ độc lập và không thay thế được cho nhau:

- Coverage hỏi: **có điền không?**
- Integrity hỏi: **điền có trỏ vào thứ có thật không?**

Một bài để trống hết ô diagram sẽ coverage thấp nhưng integrity cao, vì ít
tham chiếu thì ít chỗ sai. Ngược lại, bài điền dày nhưng bịa tên sẽ coverage
cao mà integrity thấp. Luôn đọc hai số cùng nhau.

---

## 6. Những gì không nằm trong hai chỉ số này

Để tránh hiểu nhầm phạm vi:

- Không chấm luồng của activity diagram (thứ tự, guard, fork/join, vòng lặp).
- Không chấm swimlane — tên lane, số lane, cách gán action vào lane.
- Không chấm multiplicity, kiểu dữ liệu, hay loại quan hệ trong class diagram.
- Không so diagram của agent với diagram gold.
- Không chấm chất lượng acceptance criteria.

Những thứ trên nếu cần đo thì phải có chỉ số riêng, với quy trình chấm riêng
và thường cần phán đoán của chuyên gia.

---

## 7. Kết quả trên gold

Gold hiện tại đạt cả hai chỉ số 100%:

```
VMX Requirement Coverage  : 22/22  = 100.0%
VMX Referential Integrity : 151/151 = 100.0%
```

Gold không có file `behavioral.puml` (G3 chỉ tồn tại dưới dạng diagram trong
công cụ GUI), nên khi chấm gold, tập hành vi được lấy từ đặc tả văn bản của G3
gồm 8 action. Kết quả chấm có in rõ dòng này để không nhầm với trường hợp bài
nộp thật.

Ba dòng có ô Behavioral rỗng, đều hợp lệ theo luật ở mục 3:

| Dòng | Lý do |
| --- | --- |
| US-01 | Dữ liệu khách hàng — tĩnh, không có action trong luồng |
| US-02 | Dữ liệu sản phẩm — tĩnh, không có action trong luồng |
| US-14 | G3 chưa có action `Reject Payment`; trạng thái đổi mà không có action gây ra |

US-14 là vấn đề của mô hình G3, không phải của VMX. Thêm action `Reject Payment`
vào lane Accountant sẽ lấp được ô này và làm cặp confirm/reject đối xứng.