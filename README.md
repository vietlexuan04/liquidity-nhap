# Liquidity Risk Analytics Toolkit

Mô phỏng quy trình phân tích rủi ro thanh khoản ngân hàng theo Basel III (LCR, NSFR) +
stress testing, xây dựng trên dữ liệu công khai FDIC của **JPMorgan Chase Bank, N.A.**
(Cert #628), Q1/2023 – Q2/2026. Project cá nhân, hướng tới vị trí Chuyên viên Quản trị rủi
ro thanh khoản — mục tiêu minh hoạ quy trình phân tích (data pipeline → mapping có kiểm
chứng → ratio engine → sensitivity/benchmark → stress testing → SQL/BI), không phải tái tạo
số liệu quản trị chính thức của JPMorgan.

**Đọc trước khi dùng số trong repo này**: toàn bộ LCR/NSFR là **proxy**, tính từ dữ liệu
Call Report công khai (không đủ chi tiết để tính đúng 100% theo quy định) — baseline proxy
thấp hơn số LCR thật JPMorgan công bố khoảng **19-33 điểm %** (xem benchmark bên dưới). Đây
là đặc tính đã biết của mô hình, có giải thích đầy đủ, không phải lỗi.

## Vì sao làm project này

Chuẩn bị cho vị trí quản trị rủi ro thanh khoản — JD yêu cầu hiểu LCR/NSFR/LDR, NHNN & Basel
III, liquidity gap, stress testing, và thành thạo SQL/Power BI/Python. Project này thực hành
từng phần của JD trên dữ liệu thật thay vì chỉ đọc lý thuyết.

## Tech stack

Python (pandas-free, chỉ dùng thư viện chuẩn: `csv`, `sqlite3`, `random`) cho pipeline +
tính toán · SQLite cho lưu trữ/truy vấn · Power BI cho dashboard · dữ liệu nguồn: FDIC
BankFind API (tải thủ công, không cần code để lấy dữ liệu thô).

## Luồng xử lý (chạy theo thứ tự)

```
data/raw/jpm_628_raw.csv                 (tải tay từ FDIC BankFind, xem hướng dẫn bên dưới)
        │
src/parse_fdic_raw.py      ──→  data/processed/jpm_628_wide.csv, mnemonic_labels.csv
        │                        (duỗi định dạng FDIC quirky → bảng sạch: 1 dòng/quý)
src/build_mapping.py       ──→  mapping/liquidity_mapping.csv, nhnn_ratio_reference.csv
        │                        (gán từng dòng bảng cân đối vào vai trò LCR/NSFR theo
        │                         Basel III BCBS 238/295, đối chiếu NHNN TT22/TT25;
        │                         RECONCILED chính xác 0 sai lệch với ASSET/LIABEQ, 14/14 quý)
src/mapping_to_long.py     ──→  mapping/liquidity_mapping_long.csv
        │                        (bản long/tidy phái sinh, để SQL/Power BI dễ query)
src/ratios.py              ──→  data/processed/ratios_by_quarter.csv
        │                        (HQLA, LCR, ASF/RSF, NSFR, LDR — 14 quý)
src/sensitivity.py         ──→  data/processed/sensitivity_results.csv
        │                        (OAT sensitivity trên 19 dòng confidence=Low + benchmark
        │                         với LCR thật JPMorgan công bố → data/processed/lcr_benchmark.csv)
src/stress_testing.py      ──→  data/processed/stress_*.csv
        │                        (3 kịch bản cố định x 14 quý, Monte Carlo deposit run-off,
        │                         survival horizon, reverse stress test — chỉ LCR)
src/db.py                  ──→  liquidity_risk.db
                                 (gộp toàn bộ 12 bảng CSV vào 1 SQLite để Power BI kết nối)
```

Chạy lại toàn bộ: `for f in src/parse_fdic_raw.py src/build_mapping.py src/mapping_to_long.py src/ratios.py src/sensitivity.py src/stress_testing.py src/db.py; do python3 $f; done`

## Cấu trúc thư mục

```
data/raw/            FDIC Call Report gốc (tải tay, xem hướng dẫn bên dưới)
data/processed/      Toàn bộ output trung gian + kết quả (CSV)
mapping/             Bảng mapping LCR/NSFR + README phương pháp luận chi tiết
src/                 Toàn bộ code Python, chạy độc lập từng bước
liquidity_risk.db    SQLite gộp — nguồn cho Power BI / truy vấn SQL
README.md            File này
STRESS_TESTING_README.md   Kết quả stress testing đầy đủ
```

## Cách lấy dữ liệu gốc

Dữ liệu FDIC BankFind không cần viết code để tải — dán thẳng URL sau vào trình duyệt
(đổi `CERT` và khoảng `REPDTE` nếu muốn ngân hàng/giai đoạn khác):

```
https://banks.data.fdic.gov/api/financials?filters=CERT:628 AND REPDTE:[20230101 TO 20261231]&fields=REPDTE,ASSET,DEP,DEPDOM,LNLSNET,SC,EQ,CHBAL&sort_by=REPDTE&sort_order=DESC&limit=100&format=csv&download=true
```
(Bản dùng trong repo này tải đầy đủ chi tiết hơn qua "Customize a Report" tại
banks.data.fdic.gov/bankfind-suite/financialreporting, không chỉ các field cơ bản trên.)

## Phát hiện chính

### 1. Xu hướng LCR/NSFR (baseline, 14 quý)
LCR: 113% (Q1/23) → 85% (Q2/26); NSFR: 140% → 115%. Cả hai giảm dần theo thời gian, LDR ổn
định quanh 45-55%.

### 2. Sensitivity & Benchmark (kiểm định trước khi stress)
2 giả định "0% dòng tiền vào" (`L_OTH_LE12`, `A_REVREPO`, tổng ~$1,200B) gần như giải thích
trọn vẹn khoảng lệch -19 đến -33pp so với LCR thật JPMorgan Chase Bank, N.A. công bố (10-Q
SEC) — kiểm định bằng OAT sensitivity trên 19 dòng `confidence=Low`, không chỉ khẳng định
suông. Chi tiết: `mapping/mapping_README.md`.

### 3. Hai lỗi phát hiện qua review độc lập, đã sửa và ghi lại quá trình
`CHCOIN` trùng lặp với `CHBAL` (xác minh đúng ở 14/14 quý trước khi sửa); thang kỳ hạn khoản
vay dùng nhầm giá trị ròng thay vì gộp, gây dư nợ "âm" vô nghĩa. Cả hai đã sửa, reconciliation
vẫn khớp tuyệt đối sau khi sửa. Chi tiết: `mapping/mapping_README.md`, mục "Lỗi đã phát hiện".

### 4. Stress testing (chỉ LCR; đầy đủ: `STRESS_TESTING_README.md`)
Combined scenario kéo LCR Q2/2026 từ 85% → 51% (Δ-34pp); Idiosyncratic (-31pp) nặng hơn nhiều
so với Market-wide (-6pp) vì rút tiền gửi/drawdown cam kết là khoản $ lớn hơn haircut chứng
khoán. Reverse stress test cho thấy baseline đã <100% ngay cả khi chưa stress — minh chứng
trực quan cho đặc tính bảo thủ của proxy nói ở trên.

## Giới hạn đã biết (đọc trước khi dùng số trong repo)

- Không mô hình hoá dòng tiền vào (LCR inflow) ở hầu hết các dòng → proxy thấp hơn thực tế
- Trading liabilities (`B_TRADEL`) bị bỏ sót hoàn toàn khỏi LCR outflow → ngược chiều, proxy cao hơn thực tế ở điểm này
- Giả định kỳ hạn đều (uniform maturity) cho các dòng gộp ≤1 năm
- Không mô hình hoá management action/counterbalancing capacity trong stress testing
- 19/48 dòng mapping có `confidence=Low` — đã lượng hoá mức ảnh hưởng qua sensitivity, không chỉ cảnh báo suông

Danh sách đầy đủ, kèm căn cứ từng dòng: `mapping/mapping_README.md`.

## Việc tiếp theo (chưa làm)

- Stress test cho NSFR (hiện chỉ có LCR)
- Power BI dashboard (đang làm thủ công, xem `STRESS_TESTING_README.md` để lấy số liệu)
- Case study áp dụng khung này vào 1 NHTM Việt Nam (VIB/VCB/ACB), đối chiếu ngưỡng NHNN cụ thể hơn `mapping/nhnn_ratio_reference.csv`

