# mapping/ — Ghi chú phương pháp luận

## File này dùng để làm gì

`liquidity_mapping.csv` gán mỗi khoản mục trong `data/processed/jpm_628_wide.csv` (dữ liệu
JPMorgan Chase Bank, FDIC Cert #628, Q1/2023–Q2/2026) vào một vai trò trong khung LCR/NSFR
của Basel III, kèm hệ số (%) áp dụng. `liquidity_mapping_long.csv` là bản xuất phái sinh ở
dạng "long/tidy" (1 dòng = 1 khoản mục × 1 vai trò trong 1 ratio) để nạp SQL/Power BI dễ hơn
— **file wide mới là nguồn dữ liệu gốc (source of truth)**; file long chỉ để tiện query, sinh
lại bất cứ lúc nào bằng `src/mapping_to_long.py`, không tự sửa tay file long.

**Quan trọng: đây là ước tính (proxy) minh hoạ phương pháp, không phải số LCR/NSFR chính thức
của JPMorgan.** Call Report công khai của FDIC không đủ chi tiết để tính đúng theo quy định
(không có lịch kỳ hạn dòng tiền ra chi tiết theo từng ngày trong 30 ngày, không tách rõ tiền
gửi "operational" vs "non-operational" theo đúng định nghĩa Basel...). JPMorgan tự công bố LCR
chính thức riêng qua hồ sơ SEC — số trong repo này **không nhằm khớp với số đó**, mục tiêu là
minh hoạ cách phân loại và tính toán.

## Cấu trúc `liquidity_mapping.csv` (wide, nguồn gốc)

| Cột | Ý nghĩa |
|---|---|
| `line_id` | Mã tự đặt cho dòng (không phải mnemonic FDIC gốc, vì nhiều dòng là công thức gộp) |
| `side` | `asset` / `liability` / `equity` / `offbs` (ngoại bảng) / `memo` |
| `group` | Nhóm chức năng: cash, securities, loans, deposits, borrowings, capital, commitments... |
| `definition` | Công thức tính từ các mnemonic FDIC gốc trong `jpm_628_wide.csv` |
| `hqla_level` / `hqla_haircut` | Chỉ điền cho dòng đủ điều kiện HQLA (LCR, tử số) |
| `lcr_outflow` / `lcr_inflow` | % dòng tiền ra/vào trong 30 ngày (LCR, mẫu số) — chỉ điền cho dòng liên quan |
| `nsfr_asf` / `nsfr_rsf` | % nguồn vốn ổn định cần có / đã có (NSFR) — chỉ điền cho dòng liên quan |
| `in_balance_sum` | 1 = tính vào tổng đối chiếu bảng cân đối; 0 = ngoại bảng/memo, không cộng |
| `confidence` | High/Medium/Low — mức tin cậy của hệ số đã chọn (xem bên dưới) |
| `rationale` / `source` | Căn cứ chọn hệ số, trích điều khoản BCBS 238 (LCR) / BCBS 295 (NSFR) |

**Vì sao không phải cột nào cũng có dữ liệu**: 1 dòng chỉ tham gia đúng vai trò của nó trong
bảng cân đối. Một khoản cho vay không bao giờ là HQLA → 2 cột `hqla_*` luôn trống ở các dòng
`loans`. Một khoản tiền gửi không có RSF (đó là chỉ tiêu phía Tài sản) → cột `nsfr_rsf` trống
ở các dòng `deposits`. Đây là thiết kế có chủ đích, không phải thiếu dữ liệu.

## Cách chọn hệ số (factor sourcing)

- **HQLA level/haircut và LCR outflow/inflow**: theo BCBS 238 (Basel III LCR framework),
  đối chiếu thêm US Reg WW (12 CFR 249) cho phần phân loại chứng khoán GSE/GNMA vì Basel gốc
  không nói rõ bằng luật Mỹ.
- **ASF/RSF**: theo BCBS 295 (Basel III NSFR framework).
- **Ngưỡng NHNN** (LDR/CDR, tỷ lệ vốn ngắn hạn cho vay TDH, lộ trình LCR/NSFR dự thảo): xem
  file riêng `nhnn_ratio_reference.csv`, có trích Thông tư 22/2019/TT-NHNN và Thông tư
  25/2026/TT-NHNN (nâng tỷ lệ vốn ngắn hạn cho vay trung dài hạn từ 30% lên 40%, hiệu lực
  1/7/2026) — dùng để **đối chiếu ngưỡng**, không dùng để tính công thức.
- Khi Call Report không tách đủ chi tiết theo đúng định nghĩa Basel (ví dụ deposit
  operational/non-operational, rating trái phiếu địa phương), tôi chọn hệ số **thận trọng
  hơn** trong 2 mức Basel cho phép, và đánh dấu `confidence=Low` kèm giải thích cụ thể ở cột
  `rationale`.

## Đối chiếu tổng (reconciliation) — đã kiểm chứng

Tổng tất cả dòng `side=asset` khớp **chính xác 0 sai lệch** với `ASSET`, và tổng tất cả dòng
`side in (liability, equity)` khớp **chính xác 0 sai lệch** với `LIABEQ`, ở **cả 14/14 quý**
(script `src/build_mapping.py` in ra bảng đối chiếu này mỗi lần chạy). Đây là điều kiện cần để
tin rằng mapping bao phủ đủ 100% bảng cân đối, không thiếu/thừa dòng nào.

## Lỗi đã phát hiện qua review độc lập và cách sửa

Hai lỗi dưới đây được phát hiện khi so sánh với một bản mapping khác (làm bởi AI khác), sau
đó xác minh lại bằng số liệu thật trên cả 14 quý trước khi sửa — không sửa theo suy đoán.

### 1. Trùng lặp `CHCOIN` với `CHBAL` (dòng `A_CIPC` / `A_CASH_SCOPE_ADJ`)

Xác minh: đẳng thức `CHBAL = CHFRB + CHNUS + CHUS + CHCIC` đúng **tuyệt đối ở cả 14/14 quý**
(không phải trùng hợp 1 kỳ). Nếu cộng thêm `CHCOIN` như một khoản độc lập, tổng tài sản tính
ra sẽ **vượt quá** `ASSET` đã báo cáo ở **mọi quý**, đúng bằng giá trị `CHCOIN`. Kết luận:
`CHCOIN` không phải khoản cộng thêm — giá trị của nó đã nằm sẵn (trùng) bên trong một trong 4
mã kia theo cách FDIC định nghĩa field (nhiều khả năng trong `CHCIC` hoặc `CHNUS`), nhưng
nguyên nhân chính xác không xác định được từ tài liệu công khai của FDIC.

Cách sửa: tách rõ thành 2 dòng riêng — `A_CIPC` = `CHCIC` (đầy đủ, đúng label), và
`A_CASH_SCOPE_ADJ` = `-CHCOIN` (dòng điều chỉnh trùng lặp, có ghi chú rõ lý do) — thay vì giấu
phép trừ vào công thức của `A_CIPC` như bản đầu (`CHCIC - CHCOIN`, đúng số nhưng gây hiểu lầm
vì tên dòng không phản ánh phép trừ). `confidence=Low` vì nguyên nhân gốc chưa xác định chắc
chắn — **cần rà lại nếu có tài liệu định nghĩa field chi tiết hơn từ FDIC**.

### 2. Số dư nợ vay "dư" bị âm (dòng `L_RECON`)

Nguyên nhân: lịch kỳ hạn/định giá lại của khoản vay (`LNRS3LES`, `LNRS3T12`, ... `LNOTOV15`
— Schedule RC-C Part I) được báo cáo theo **giá trị gộp (gross)**, không phải giá trị ròng sau
dự phòng. Bản đầu dùng `LNLSNET` (ròng) làm gốc để trừ đi tổng các bucket kỳ hạn, tạo ra một
số dư "âm" (~-16.5 triệu USD tại Q2/2026) — vô nghĩa về kinh tế, vì không thể có khoản vay âm.

Xác minh: `LNLSNET = LNLSGR - LNATRES` đúng tuyệt đối; và `LNLSGR - Σ(bucket)` luôn **dương**,
ổn định quanh **0.5-0.7% tổng dư nợ gộp** qua cả 14 quý (hợp lý — phần dư nợ không nằm trong
lịch kỳ hạn, ví dụ khoản nợ xấu không tính lãi/không xếp lịch định giá lại).

Cách sửa: đổi gốc công thức của `L_RECON` sang `LNLSGR`; thêm dòng riêng `A_ALLOW` = `-LNATRES`
(khoản dự phòng, dòng trừ tường minh, không có trọng số RSF riêng vì không phải rủi ro thanh
khoản kinh tế thực).

**Về ngòi nổ RSF cho khoản vay**: chuẩn NSFR áp hệ số RSF lên **giá trị ghi sổ ròng** (carrying
value), không phải giá trị gộp. Vì lịch kỳ hạn `LNRS*/LNOT*` chỉ có ở mức gộp, `ratios.py` (sẽ
viết ở bước sau) sẽ nhân **toàn bộ giá trị các dòng `group=loans`** với hệ số ròng dự phòng
`LNLSNET / LNLSGR` (≈98.3% tại Q2/2026, dao động theo quý) **trước khi** áp `nsfr_rsf`, để xấp
xỉ RSF trên cơ sở ròng mà vẫn giữ được độ chi tiết theo kỳ hạn của lịch gốc. Đây là gợi ý từ
bản review độc lập, áp dụng ở bước tính toán (không sửa vào `liquidity_mapping.csv` vì hệ số
này thay đổi theo từng quý, không phải hằng số).

## Ba giả định lớn nhất khác cần biết

1. **Không mô hình hoá dòng tiền vào (LCR inflow)** ở hầu hết các dòng — mặc định = 0% trừ vài
   ngoại lệ (`L_NBFI_SHORT`). Đây là giả định thận trọng, khiến LCR proxy **thấp hơn** thực tế.
2. **Trading liabilities / phái sinh** (`B_TRADEL`) **chưa được tính vào outflow LCR** — với
   một ngân hàng có hoạt động trading lớn như JPMorgan, đây có thể là khoản outflow đáng kể bị
   thiếu (LCR proxy sẽ **cao hơn** thực tế ở điểm này — ngược hướng với giả định #1 ở trên).
3. **Giả định "kỳ hạn đều" (uniform maturity)** cho các dòng gộp `<=1 năm` (30/365 rơi vào 30
   ngày đầu) — vì Call Report không chia nhỏ hơn mốc 1 năm ở nhiều dòng nguồn vốn vay.

Toàn bộ giả định khác (bao gồm 18/48 dòng `confidence=Low`) được ghi cụ thể ở cột `rationale`
của từng dòng — đọc trực tiếp trong CSV thay vì lặp lại ở đây để tránh 2 nguồn có thể lệch nhau.

## Sensitivity & Benchmark (kiểm định baseline trước khi stress test)

Trước khi thiết kế kịch bản stress, đã kiểm định baseline theo 2 bước — vì stress 1 con số mà
bản thân nó đã là ước lượng không chắc chắn (18-19/48 dòng `confidence=Low`) sẽ cộng dồn 2 lớp
bất định mà không tách được lớp nào đóng góp bao nhiêu.

### 1. Sensitivity (one-at-a-time) trên các dòng `confidence=Low`, tại Q2/2026

Baseline: LCR = 85.0%, NSFR = 115.1%. Đổi từng dòng sang biên trên/dưới hợp lý (theo danh mục
Basel thay thế mà dòng đó có thể thuộc về — xem `src/sensitivity.py`, dict `BOUNDS`), giữ
nguyên các dòng khác:

| Dòng | Δ LCR (pp) | Dòng | Δ NSFR (pp) |
|---|---:|---|---:|
| `L_OTH_LE12` (inflow 0%→50%) | +49.1 | `A_TRADE` (rsf 15%→100%) | -41.7 |
| `A_REVREPO` (inflow 0%→100%) | +48.2 | `D_DOM_FOR` (asf 0%→50%) | +2.6 |
| `D_FO_IPC` (outflow 100%→25%) | -23.9 | `A_CASH_FOREIGN` (rsf 0%→15%) | -2.1 |
| `A_CASH_FOREIGN` (haircut 0%→100%) | -21.7 | 7 dòng khác | <1.5 mỗi dòng |
| `O_OTHER` (outflow 20%→50%) | -19.4 | | |
| `B_REPO` (outflow 25%→100%) | -17.7 | | |
| `L_NBFI_SHORT` (inflow 33%→100%) | +16.3 | | |
| 11 dòng còn lại | <5 mỗi dòng | | |

**Kết luận**: không phải cả 19 dòng Low-confidence đều quan trọng ngang nhau — chỉ 4-5 dòng đầu
bảng (đặc biệt 2 giả định "0% dòng tiền vào" cho `L_OTH_LE12` và `A_REVREPO`) thực sự quyết
định kết quả LCR. Kết quả chi tiết: `data/processed/sensitivity_results.csv`.

Combined-extreme (đẩy cả 19 dòng cùng lúc theo hướng xấu/tốt nhất): LCR dao động 35.7%-416.1%,
NSFR 106.1%-161.5%. **Đây là biên lý thuyết tuyệt đối, không phải khoảng tin cậy thực tế** (xác
suất cả 19 giả định cùng sai 1 hướng ~0) — chỉ dùng OAT ở bảng trên khi trích dẫn trong báo cáo.

`B_TRADEL` (trading liabilities) hiện bị **bỏ sót hoàn toàn** khỏi LCR outflow (xem mục Limitations)
— đây là 1 khoản omission, không phải hệ số chưa chắc, nên thử riêng: nếu gán outflow
20%/50%/100%, LCR giảm thêm 2.5/6.0/11.1pp so với baseline.

### 2. Benchmark với LCR thật JPMorgan Chase Bank, N.A. công bố (10-Q/SEC, 8 quý trùng)

| Quý | Proxy LCR | LCR thật (Bank, average) | Lệch (pp) |
|---|---:|---:|---:|
| 24Q2 | 105.7% | 125% | -19.3 |
| 24Q3 | 95.7% | 121% | -25.3 |
| 25Q1 | 97.2% | 124% | -26.8 |
| 25Q2 | 100.1% | 120% | -19.9 |
| 25Q3 | 91.7% | 117% | -25.3 |
| 25Q4 | 95.3% | 115% | -19.7 |
| 26Q1 | 90.5% | 120% | -29.5 |
| 26Q2 | 85.0% | 118% | -33.0 |

Nguồn số thật: 10-Q JPMorganChase & Co (SEC EDGAR, CIK 0000019617) và LCR Disclosure Report
của JPMorgan Chase Bank, N.A. — mục "Firm and JPMorgan Chase Bank, N.A.'s average LCR".
Lưu ý: số thật là **trung bình cả quý** (average), còn proxy tính từ **số dư cuối quý**
(point-in-time) — khác nhau về phương pháp, không chỉ khác về độ chi tiết dữ liệu.

**Proxy luôn thấp hơn số thật 19-33pp, cùng hướng, nới rộng dần theo thời gian** — khớp đúng
với phát hiện ở mục sensitivity: giả định "0% dòng tiền vào" cho 2 khoản lớn
(`L_OTH_LE12`, `A_REVREPO`, tổng ~$1,200B) gần như giải thích trọn vẹn khoảng lệch này. Nếu
sửa 2 giả định đó theo hướng Basel cho phép (xem bảng sensitivity), proxy sẽ tiệm cận số thật
hơn nhiều — nhưng **cố tình chưa sửa** ở baseline, để giữ baseline ở mức giả định bảo thủ nhất
quán, dễ giải thích hơn là "tinh chỉnh để khớp số thật" (risk of overfitting to one bank's
disclosed number thay vì theo đúng phương pháp luận Basel chung).

Dữ liệu đầy đủ: `data/processed/lcr_benchmark.csv`.

## Cách dùng để tính ratio (bước tiếp theo, `src/ratios.py`)

```
HQLA          = Σ(asset_value × (1 - haircut))                     [chỉ dòng có hqla_level]
LCR outflow   = Σ(liability_value × lcr_outflow) + Σ(offbs_value × lcr_outflow)
LCR inflow    = Σ(asset_value × lcr_inflow)
LCR           = HQLA / max(LCR outflow - LCR inflow, LCR outflow × 25%)   [Basel: inflow cap 75% outflow]

ASF           = Σ(liability_value × nsfr_asf) + Σ(equity_value × nsfr_asf)
RSF           = Σ(asset_value × nsfr_rsf × netting_factor)   [netting_factor = LNLSNET/LNLSGR, chỉ áp cho group=loans]
NSFR          = ASF / RSF
```
Chỉ dùng các dòng có `in_balance_sum` liên quan đúng vai trò (offbs không cộng vào tổng bảng
cân đối nhưng vẫn cộng vào outflow LCR).
