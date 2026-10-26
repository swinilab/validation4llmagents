# VMXGrading

Chấm hai metric truy vết của `VMX.csv` (định nghĩa ở `materials/M2-metrics.md` §1.1–1.2).
Chỉ là đối chiếu tra cứu: không embedding, không LLM judge, không người duyệt, nên
kết quả luôn tất định và luôn `final`.

| Metric | Công thức |
|---|---|
| **VMX Requirement Coverage** | requirement có dòng VMX đủ điều kiện / số requirement trong `requirements.json` |
| **VMX Referential Integrity** | tham chiếu resolve được / tổng tham chiếu VMX |

Một requirement được tính *covered* khi có dòng VMX với `SRS-Req-ID` trùng và
`US-` có `Domain-Req-ID` **và** `Structural-Elements` khác rỗng, `NFR-` có
`Domain-Req-ID` khác rỗng (bảng này nằm ở `rules.yaml`, mục `completeness`).

Một tham chiếu *resolve được* khi khớp character-for-character với một tên được khai
báo trong **chính submission**, không bao giờ với gold:

| Cột | Tra trong |
|---|---|
| `Domain-Req-ID` | các key của `FR_INPUT` và `NFR_INPUT` trong `gold.domain` (config.yaml) |
| `Structural-Elements` | class, enum hoặc `Class.attribute` trong `structural.puml` của submission |
| `Behavorial-Elements` | action trong `behavioral.puml` của submission |

Tên cột phân biệt đúng chính tả schema (`Behavorial-Elements`, thiếu chữ `i`). Cột
bị viết khác đi được ghi vào `inputs.vmx.schema.missing_columns` và bị đọc như rỗng.
Ô được tách theo `;`, trim, loại trùng trong cùng ô; cột `SRS-Req-ID` không phải tham
chiếu.

Tên khai báo được đọc bằng parser PlantUML của `ModelsGrading`, nên hai module thống
nhất về việc submission khai báo những gì.

## Chạy

```bash
# qua pipeline (cùng với reqs và models)
python main.py --phase grade --grade vmx --run-id <run_id>

# riêng module, từ thư mục gốc repo
python -m evaluators.VMXGrading.run --submission <dir> --out generated/RUN_x
```

`--submission` chứa `requirements.json`, `VMX.csv`, `structural.puml`, `behavioral.puml`.
Kết quả nằm ở `<RUN>/grading/vmx/run/`:

| File | Nội dung |
|---|---|
| `00_inputs.json` | trạng thái từng file đầu vào, schema của VMX, kích thước từ vựng |
| `01_coverage.json` | outcome từng requirement (`covered`, `incomplete`, `no_row`, `unknown_prefix`) |
| `02_integrity.json` | điểm theo cột và danh sách tham chiếu hỏng (dòng, id, cột, giá trị) |
| `03_metrics.json` | hai metric + chẩn đoán |
| `manifest.json` | rules đã dùng, thời gian chạy |

## n/a và 0

- Thiếu `VMX.csv`: Coverage = **0** (đã đo, không nối gì), Integrity = **n/a** (không có
  tham chiếu nào để đo).
- Thiếu `requirements.json`: Coverage = **n/a** (không có mẫu số).
- Thiếu một file `.puml`: từ vựng của nó rỗng, mọi tham chiếu vào đó là hỏng.

Exit code: `0` DONE, `1` FAILED (config hoặc domain input không đọc được). File đầu vào
của submission thiếu/hỏng là kết quả chấm hợp lệ, không phải FAILED.
