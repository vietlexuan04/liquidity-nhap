# STRESS_TESTING_README.md — Phương pháp luận & kết quả stress testing

Áp dụng `src/stress_testing.py` lên baseline đã kiểm định (xem `mapping/mapping_README.md`,
mục "Sensitivity & Benchmark") — **chỉ stress LCR** (NSFR để sau). Toàn bộ số liệu nằm trong
`data/processed/stress_*.csv`, hoặc truy vấn qua `liquidity_risk.db` (bảng `stress_*`).

## Giả định tường minh quan trọng nhất

**Không mô hình hoá management action / counterbalancing capacity** — không có giả định ngân
hàng sẽ bán tài sản ngoài HQLA, rút hạn mức dự phòng, hay cắt giảm cho vay mới để ứng phó cú
sốc. Toàn bộ kết quả dưới đây là phản ứng "cơ học" thuần tuý của bảng cân đối như đã báo cáo,
dưới cú sốc đã cho — một ngân hàng thật sẽ phản ứng, nên kết quả này **cố tình bi quan hơn**
thực tế một ngân hàng sẽ trải qua.

**Baseline proxy đã thấp hơn số LCR thật JPMorgan công bố ~19-33 điểm %** (xem benchmark). Vì
vậy **mọi kết quả dưới đây đều báo cả số tuyệt đối lẫn delta so với baseline của chính mô
hình** — không nên đọc số tuyệt đối một mình, dễ hiểu nhầm "ngân hàng sắp sụp" trong khi đó là
đặc tính bảo thủ của proxy, không phải điểm yếu thật của JPMorgan.

## 1. Ba kịch bản cố định

| | Idiosyncratic | Market-wide | Combined |
|---|---|---|---|
| Tiền gửi bán lẻ ổn định (`D_INS_STABLE`) | 5%→10% | không đổi | 10% |
| Tiền gửi brokered (`D_INS_BRO`) | 10%→25% | không đổi | 25% |
| Tiền gửi DN/khối ngoại không BH (`D_DOM_UNINS_OTH`/`D_FO_IPC`) | 40%→70% | không đổi | 70% |
| Cam kết tín dụng chưa dùng (`O_*`) | x1.5 drawdown | không đổi | x1.5 |
| HQLA haircut GSE/muni (`S_GSE`/`S_MUNI`) | không đổi | 15%→25% / 50%→65% | 25% / 65% |
| Repo (`B_REPO`) | không đổi | 25%→50% | 50% |

`B_ST` (vay ngắn hạn khác/FHLB) **giữ nguyên baseline** — đề xuất ban đầu không cho số cụ thể
cho dòng này, không tự đoán.

**Kết quả (LCR %, Q2/2026 làm đại diện; đầy đủ 14 quý trong `stress_scenarios_by_quarter.csv`):**

| Kịch bản | LCR | Δ vs baseline (pp) | Δ vs baseline (%) |
|---|---:|---:|---:|
| Baseline (không stress) | 85.0% | — | — |
| Idiosyncratic | 53.8% | -31.2 | -36.7% |
| Market-wide | 79.0% | -6.0 | -7.1% |
| Combined | 51.0% | -34.0 | -40.0% |

**Nhận xét**: Idiosyncratic nặng hơn Market-wide rất nhiều (-31pp vs -6pp) — vì rút tiền gửi
và drawdown cam kết tín dụng là khoản đô-la lớn hơn hẳn so với haircut chứng khoán GSE/muni
(vốn chỉ chiếm phần nhỏ trong $957B HQLA, phần lớn là Treasury/Fed reserves vẫn giữ 0% haircut).
Xu hướng này **nhất quán ở cả 14 quý** — Combined luôn gần sát Idiosyncratic hơn là Market-wide,
không phải chỉ đúng ở 1 quý.

## 2. Monte Carlo deposit run-off (Q2/2026, 10.000 draws)

Random hoá 4 dòng tiền gửi (`D_INS_STABLE`, `D_INS_BRO`, `D_DOM_UNINS_OTH`, `D_FO_IPC`) quanh
giá trị combined scenario, phân phối Beta (std = 20% mean), các tham số khác (HQLA haircut,
drawdown, repo) **giữ cố định ở giá trị combined** — không random hoá toàn bộ cùng lúc vì không
có cơ sở giả định tương quan giữa các loại rủi ro khác nhau.

| Percentile | LCR | Δ vs baseline (pp) |
|---|---:|---:|
| p5 | 44.5% | -40.5 |
| p25 | 47.7% | -37.4 |
| p50 | 50.7% | -34.4 |
| p75 | 54.5% | -30.5 |
| p95 | 61.7% | -23.3 |

**Kiểm tra chéo**: median (50.7%) rất khớp với combined scenario điểm (51.0%) — xác nhận model
nhất quán giữa 2 cách tính (kịch bản cố định vs phân phối xác suất quanh cùng tâm).

## 3. Survival horizon (Q2/2026)

Giả định: outflow rải đều theo ngày trong 30 ngày (`net_outflow / 30`/ngày) — giả định đơn
giản hoá, thực tế dòng rút thường dồn vào những ngày đầu khủng hoảng hơn là rải đều.

| Kịch bản | HQLA | Net outflow 30d | LCR | Số ngày sống sót |
|---|---:|---:|---:|---:|
| Baseline | $957.1B | $1,125.7B | 85.0% | 25.5 ngày |
| Idiosyncratic | $957.1B | $1,779.3B | 53.8% | 16.1 ngày |
| Market-wide | $940.6B | $1,190.5B | 79.0% | 23.7 ngày |
| Combined | $940.6B | $1,844.1B | 51.0% | 15.3 ngày |

Baseline đã <30 ngày — hệ quả trực tiếp của baseline proxy thấp hơn thật, không phải JPMorgan
thật sự chỉ trụ được 25.5 ngày.

## 4. Reverse stress test (Q2/2026)

Tham số hoá cường độ sốc θ (θ=0: baseline, θ=1: đúng combined scenario, nội suy tuyến tính
từng hệ số, cho phép ngoại suy ngoài [0,1]):

| Mục tiêu LCR | θ cần | Diễn giải |
|---|---:|---|
| 100% | **-0.23** | **Cần GIẢM stress xuống dưới cả baseline** 23% khoảng cách combined — vì baseline vốn đã <100%. Đây là minh chứng trực quan nhất cho đặc tính bảo thủ của proxy, không phải JPMorgan thật sự dưới ngưỡng quy định. |
| 75% | 0.20 | Chỉ cần 20% cường độ combined scenario đã đủ chạm 75% |
| 50% | 1.05 | Cần hơi quá (105%) cường độ combined để chạm 50% |
| ~0% (HQLA cạn gần hết) | ~40.0 | Cần gấp ~40 lần cường độ combined — cho thấy dù combined đã nặng, vẫn còn cách rất xa điểm cạn kiệt hoàn toàn thanh khoản |

## Cách tra cứu

Toàn bộ bảng trên nằm trong `liquidity_risk.db` (SQLite), bảng `stress_scenarios_by_quarter`,
`stress_montecarlo_2026q2`, `stress_survival_horizon`, `stress_reverse_test` — join với
`ratios_by_quarter` qua `report_period` để so baseline. Build lại DB bất cứ lúc nào bằng
`python3 src/db.py` (đọc trực tiếp từ các CSV trong `data/processed/` và `mapping/`, không sửa
tay file `.db`).
