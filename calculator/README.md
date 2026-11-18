# Tesla／SpaceX 年度營收、獲利與股價 Calculator

Python 3.10 以上，僅使用標準函式庫，無需安裝套件。預設計算 2027–2035 年，可在 JSON 修改年度、業務與假設。

**預設是可執行的示例模型，不是已校準的投資預測。所有預設數字，包括股數、現金、負債、倍數與換股比例，都是示例假設。** 公司實際披露另存於 [reference_facts.json](configs/reference_facts.json)，不會自動覆寫模型。使用前先以實際資料校準起點，再調整未來假設。

## 快速開始

在 repo 根目錄執行：

```bash
# 一次計算保守、基準、樂觀情境
python calculator/forecast.py --out forecast_output

# 只算基準情境
python calculator/forecast.py --scenario base --out forecast_output/base

# 使用你自己的 JSON
python calculator/forecast.py --config my_assumptions.json --scenario base
```

複製 [example.json](configs/example.json) 後修改，或用 `--set` 臨時覆寫。路徑拼錯會報錯，避免參數沒有生效。

```bash
# Robotaxi 付費公里車資改為 $0.60，Tesla 本益比改為 35 倍
python calculator/forecast.py --scenario base \
  --set companies.tesla.segments.robotaxi.fare_usd_per_paid_km.value=0.6 \
  --set companies.tesla.pe_multiple=35 \
  --out forecast_output/robotaxi_price_cut

# 指定 2030 年平均 Starlink 消費者用戶 3,000 萬
# annual 是絕對值，不能把年底用戶直接當全年平均用戶
python calculator/forecast.py --scenario base \
  --set 'companies.spacex.segments.starlink_consumer.average_subscribers.annual={"2030":30000000}' \
  --out forecast_output/starlink

# 打開假想合併快照，每 1 股 SpaceX 換 0.3 股 Tesla
python calculator/forecast.py --scenario base \
  --set merger.enabled=true \
  --set merger.target_exchange_ratio=0.3 \
  --out forecast_output/combined

# 測試太空算力 2030 年有 100 MW 平均 IT 容量
# 必須同時自行修改發射／設備 capex、折舊、電力與營運成本
python calculator/forecast.py --scenario base \
  --set 'companies.spacex.segments.orbital_compute.average_it_mw.annual={"2030":100}' \
  --out forecast_output/orbital_experiment
```

`--set` 在情境覆寫之後生效。數字、布林及物件皆使用 JSON 語法。可重複使用。`--scenario all` 會把同一組命令列覆寫套用至每個情境。`annual` 欄位若原本不存在，先在設定檔新增，或覆寫整個曲線物件。

## 涵蓋的業務

| 公司 | 設定鍵 | 業務／數量單位 |
| --- | --- | --- |
| Tesla | passenger_vehicles | 對外乘用車，台／年，車價排除另列 FSD |
| Tesla | semi | 對外 Semi，台／年 |
| Tesla | energy | Megapack、Powerwall 等合計 GWh／年，價格為美元／GWh |
| Tesla | fsd | 外部全年平均付費訂閱數，不含自有 Robotaxi |
| Tesla | robotaxi | 自有車隊，車數、付費公里、車資與後勤 |
| Tesla | optimus_external | 對外機器人，台／年 |
| Tesla | services_other | 充電、售後、租賃及其他年度校準項 |
| SpaceX | launch_external | 外部發射與太空合約的等效任務，不含自用發射 |
| SpaceX | starlink_consumer | Starlink 全年平均消費者付費用戶 |
| SpaceX | starlink_enterprise | 企業、政府、航空航海合約年度收入包 |
| SpaceX | direct_to_cell | 合作變現的平均等效付費連線，非官方揭露用戶量 |
| SpaceX | starlink_hardware | 對外終端硬體，台／年 |
| SpaceX | ground_compute | 地面算力租賃與自用基建的整體成本 |
| SpaceX | orbital_compute | 太空算力，預設商業容量為 0，研發及建設仍花錢 |
| SpaceX | grok_subscriptions | Grok 外部訂閱 |
| SpaceX | grok_api | Grok API，數量為「百萬計費 tokens」 |
| SpaceX | cursor | 平均付費席位 |
| SpaceX | x_and_other | X 廣告、其他及年度校準項 |

這些是分析細分，不代表公司將每項獨立揭露。`services_other`、`starlink_enterprise`、`x_and_other` 的示例 `units=1`，價格代表該年度收入包；成長在價格曲線表達，並非實際商品單價。可把它們拆成更多互不重疊的 `unit` 或 `subscription` 業務。

鋰礦、精煉、電池與自用機器人影響成本、capex 和折舊。只要沒有對外銷售，就不另創造合併營收。Starshield 等政府業務應依實際合約歸到外部太空任務或企業／政府通訊，避免兩邊重算。自有 Robotaxi 的生產不計對外賣車收入。暫未預設第三方車主平台業務；若新增，應只計平台費，不能把全額車資全算 Tesla 收入。

## 參數曲線

### 2027 Optimus 1,000 萬台：內用優先、餘量出租

[optimus_10m.json](configs/optimus_10m.json) 保存使用者的單年生產假設，不覆蓋原有基準設定：

```bash
python calculator/forecast.py --config calculator/configs/optimus_10m.json \
  --scenario optimus_10m --out forecast_output/optimus_10m
```

`robot_fleet` 計算自持機器人：年末數量＝期初＋當年生產－退役，年平均採年初／年末平均。示例為期初 0、全年均勻生產 1,000 萬台，故年平均可用 500 萬台，不能把年底全部台數乘上 12 個月租金。

1. 先將年平均可用數量分配給 `internal_demand_robots`。
2. 剩餘數量可供出租；實際平均付費台數取「可租數量 × rental_utilization」與 `rental_demand_robots` 的較小值。
3. 外租營收＝平均付費台數 × `monthly_rent_usd` × 12。內用沒有銷售營收。
4. 內用避免成本＝平均內用台數 × `internal_avoided_cost_usd_per_robot_year`，仍受公司可改善製造成本上限約束；租賃收入不套用此上限。
5. 全部自持台數皆計維運成本，製造成本進 capex，折舊與退役帳面損失進成本並於現金流加回。折舊不超過剩餘帳面價值，退役按期初資產帳面值比例移除。

此情境停用原先 Optimus 對外銷售，以及固定額度的機器人節省／capex／折舊，避免與新機器人資產池重算。`robot_fleet` 的內用節省與固定 `robotics_savings_usd` 不能同時為正。

**使用者指定的只有 2027 年生產量及內用優先的分配規則。** 內用需求 100 萬台、出租率 50%、月租 2,000 美元、單台成本 20,000 美元及其他數值均為額外可改的示例；不是公司實績或生產可行性的證明。只預測 2027 年，未擅自延伸往後每年生產 1,000 萬台。

自持製造投入可能造成現金缺口，即使損益表獲利也不代表資金足夠。未明列融資前，原有資金缺口與停用股價估值規則繼續適用。此版內用節省只抵銷 Tesla 指定製造業務，不推定全部台數都能取代人工，也未自動把供 SpaceX 使用的台數當成合併內部交易。

大部分數值可填固定數字，或用以下物件：

```json
{
  "value": 2000000,
  "growth": 0.12,
  "cap": 5000000,
  "floor": 0,
  "annual": {"2030": 3000000}
}
```

- `value`：`years` 第一年的值。
- `growth`：逐年複合成長率，0.12 表示 12%，-0.03 表示每年下降 3%。
- `annual`：該年的絕對值，優先於複合成長；下一年仍回到原始成長曲線，不以覆寫值為新起點。
- `cap`／`floor`：最後套用的上限／下限，亦作用於 annual 覆寫。材料成本底線可用 `floor`。
- 金額均為**美元**，未縮成百萬或十億。比例用 0–1，1 GW=1,000 MW，1 GWh=1,000,000 kWh。
- 改預測起始年時，要重新校準 value、opening 資產負債與車隊，不只是修改年度標籤。

## 業務計算公式

### 對外產品與訂閱

```text
產品銷量 = min(units, capacity_units)             # 沒填容量時不限制
產品營收 = 銷量 × price_usd
直接成本 = 銷量 × unit_cost_usd

訂閱營收 = average_subscribers × monthly_price_usd × 12
訂閱直接成本 = average_subscribers × monthly_cost_usd × 12

業務毛利 = 營收－直接成本－該業務折舊
業務營業利益 = 毛利－該業務研發／營運費用
```

`unit_cost_usd`／`monthly_cost_usd` 排除已另列的折舊、業務 opex 及公司共同費用。車價若含 FSD 交易分攤，須先扣除另列部分。Grok API 應包含實際收費的思考 tokens，不能只用畫面可見輸出數量。

`opex_usd`、`capex_usd`、`da_usd` 可用年度曲線；另可加 `capex_revenue_ratio`、`da_revenue_ratio`。兩種金額會相加，不能把同筆資產同時完整填在固定金額及比例內。`start_year` 前仍計顯式研發、capex 及折舊，不能因未商轉就消除投入。

### Robotaxi

```text
期末車隊 = 期初車隊＋additions－retirements
全年平均車隊 = (期初＋期末) ÷ 2
總公里 = 平均車隊 × km_per_vehicle_day × operating_days
付費公里 = 總公里 × paid_km_share
營收 = 付費公里 × fare_usd_per_paid_km
直接成本 = 總公里 × cash_cost_usd_per_total_km
         ＋平均車隊 × fixed_cash_usd_per_vehicle_year
         ＋平均車隊 × depreciation_usd_per_vehicle_year
車隊新增 capex = additions × vehicle_cost_usd
```

新車／退役車視為平均年中變動。空駛仍耗電、維修及折舊。每車固定現金成本應含保險、清潔、支援、場站等；避免和業務 opex 重算。

車輛購置不一次列為當年費用，而以 capex 支出、折舊費用及現金流加回連結。折舊需自行填入，模型不自動推導殘值、世代、退休資產或減損。因此結果是情境估計，不是固定資產會計帳。`passenger_production_capacity` 檢查外部乘用車銷量＋自有車隊新增是否超出總產能；不把不夠產能的情境當成可交付預測。

### 地面／太空算力

```text
外部計費 MW-hours = average_it_mw × external_share
                  × external_utilization × availability × 8,760
營收 = 外部計費 MW-hours × price_usd_per_billable_mw_hour

忙碌比例 = availability × (外部份額×外部利用率＋自用份額×自用利用率)
全年 kWh = MW × 1,000 × 8,760 × PUE
          × [忙碌比例＋(1－忙碌比例)×idle_power_fraction]
成本 = 電費＋每 MW 現金營運成本＋每 MW 硬體折舊
```

固定以每年 8,760 小時作模型慣例。MW 是全年平均 IT 容量，不是年底名目容量。外租＋自用份額不得超過 100%；自用算力沒有租賃收入，其成本留在 compute 列，因此 Grok 成本不可再加一次同筆自有運算。

`price_usd_per_billable_mw_hour` 是算力服務收入的等效換算，**不是電力售價**。模型沒有用公開 token 牌價反推 GPU 成本，也沒有建立 GPU 世代、模型吞吐與訂閱用量間的物理容量推導，這些需要另外校準。若 Grok 向外部雲端付費，應加入對應業務成本。

太空算力預設容量為 0。啟用時必須另外輸入發射、衛星、散熱、通訊、汰換 capex／折舊及現金支出，不能只把地面電價改成 0 就當太空成本。

### 機器人降本

公司層 `robotics_savings_usd` 只分配到 `robotics_eligible=true` 的業務，且不超過這些業務 COGS 的 `robotics_max_cogs_share`。有效節省超額時會截斷並警示。

參與分配的 `cost_includes_robotics` 必須設為 false，表示 unit cost 的基準尚未包含**這筆額外節省**。原本的成本曲線下降可以代表材料、製程等其他改善；若已包含相同機器人效果，不能再疊加。節省額為機器人現金維運與接管後、機器人折舊前的淨節省。新增內用機器人成本放 `robotics_capex_usd`，其折舊放 `robotics_da_usd`。不計內用機器人銷售收入。

## 公司獲利與現金流

```text
營業利益 = 各業務營業利益合計
         －corporate_opex_usd－sbc_expense_usd－robotics_da_usd
利息 = 平均年初／年底債務 × interest_rate
稅前利益 = 營業利益－利息
所得稅 = max(稅前利益, 0) × tax_rate
淨利 = 稅前利益－所得稅

現金 FCF 代理值 = 淨利＋D&A＋SBC－capex－營運資金增加
經濟 FCF = 現金 FCF 代理值－SBC
年底現金 = 年初現金＋現金 FCF 代理值＋新增借款－還款
         ＋股權募資－庫藏股－股利
```

`corporate_opex_usd` 排除另列 SBC 及內用機器人折舊。其他事業 opex 不應再含公司層另列 SBC。現金 FCF 加回非現金 SBC，但股本稀釋另計，保留它對每股價值的影響。經濟 FCF 留作股東角度的比較，現金餘額使用現金 FCF。

每年以營收乘 `nwc_revenue_ratio` 算年底營運資金，再扣除與上年差額。模型暫不含虧損扣抵、遞延所得稅、利息收入、非營業投資利得、少數股權與複雜租賃。需要時先調整設定及計算函數，不可把本模型稱為完整 GAAP 預測。

若出現資金缺口，不自動假設銀行借錢或投資人認股，當年與之後股價欄均停用。營收及獲利留作「尚未融資的壓力情境」，不表示資金不足仍可繼續經營。要解除缺口，請顯式加入借款、募資與對應稀釋後重新跑完整期間。

## 股價情境：兩種方法

| 方法 | 計算 |
| --- | --- |
| P/E | 年度淨利 × pe_multiple ÷ 年底稀釋股數 |
| SOTP | （各業務營收 × 自訂 EV/Sales 倍數合計－公司費用資本化＋年底現金－年底債務）÷ 年底稀釋股數 |

SOTP 使用**企業價值**倍數，所以才加現金減負債；P/E 直接使用淨利的股權價值，不能再加一次現金。公司費用資本化為當年 corporate opex（含 SBC 與機器人折舊）乘 `corporate_ev_cost_multiple`。EV/Sales 對應企業價值，並不保證反映不同業務的合理毛利或持續投入，需自行校準。

發新股數＝`equity_raised_usd / equity_issue_price_usd`；庫藏股減少股數＝`buybacks_usd / buyback_price_usd`。SBC 稀釋率另外作用於股份。`stock_split` 只填拆股當年，例如 `{"value":1,"annual":{"2030":3}}`；發行與回購價必須使用當年拆股後單位。

輸出的 `eps_usd` 以年初／年底平均股份近似年度 EPS。`year_end_share_earnings_usd` 使用年底股份；上表 P/E 股價使用後者，以反映預測年底股本。兩者在募資或大量稀釋時會不同。淨利為負時，P/E 股價為 N/A；SOTP 股權價值不正時，SOTP 股價為 N/A，保留原始股權值供診斷。

## Tesla＋SpaceX 假想合併

預設關閉。開啟後另產出 `merger.csv`，不把合併當成已發生。

```text
合併股數 = Tesla 年底股數＋SpaceX 年底股數 × 換股比例＋額外股份
合併營收 = 兩家營收合計－內部交易營收抵銷
合併淨利 = 兩家淨利合計＋淨營運協同－交易費用－增量所得稅
```

- `net_operating_synergy_usd` 是扣除新增整合營運負擔後、稅前的淨協同，可為負。
- `target_exchange_ratio` 表示每一股目標公司換得幾股收購方股份。若任何公司拆股，使用當年股本單位的比例。
- `new_shares` 為額外股份，不自動產生募資現金。交易成本在假想合併首年計入，沒有假設稅損利益。
- `intercompany_revenue_usd` 應抵銷雙邊已費用化的內部交易。`intercompany_ev_elimination_usd` 另外扣除賣方營收估值的重複企業價值；不得只抵銷營收卻保留同筆估值。
- 此版本是**每年獨立的 pro-forma 快照**，不是交割後財務遞推。兩家公司先各自預測，再合併當年資料。未遞推協同累積現金、交易費後續效果、購買價分攤、資產利得遞延、交易融資及股東投票等。資產型內部交易需另外處理未實現利得，不能用服務抵銷公式代替。

## 輸出與重現

| 檔案 | 內容 |
| --- | --- |
| companies.csv | 各公司逐年營收、毛利、營業利益、淨利、現金流、股本與兩種估值 |
| segments.csv | 各業務逐年營收、成本、毛利、營業利益、capex、折舊與實際驅動值 |
| merger.csv | 開啟時的合併年度快照 |
| results.json | 全部結果、每情境有效輸入、命令列覆寫、原始設定 SHA-256 與生成時間 |
| summary.md | 方便閱讀的中文年度總表 |

CSV 使用 UTF-8 BOM，方便 Excel 開啟。毛利／營業利益可下鑽到業務，淨利與股價按公司層計算，不強行把利息、稅及共同費用當成各業務的已知獨立淨利。

全部情境先完成驗證，再輸出；不會把失敗情境省略後冒充完整比較。若某次輸入錯誤，舊的輸出檔不會更新，請以成功退出碼及 JSON 的生成時間／輸入雜湊確認版本。

Python 直接呼叫：

```python
import json
from calculator.forecast import forecast

with open("calculator/configs/example.json", encoding="utf-8") as f:
    assumptions = json.load(f)

result = forecast(assumptions, "base")
for year in result["companies"]["tesla"]:
    print(year["year"], year["revenue_usd"], year["net_income_usd"], year["price_pe_usd"])
```

## 測試

```bash
python -m unittest discover -s calculator/tests -v
```

測試涵蓋年度財務勾稽、MW／kWh 單位、自用容量與生產容量、車隊滾動及 capex、機器人節省上限、融資／拆股／稀釋、資金缺口、合併換股／抵銷、CLI 與輸出。

模型對應 [理論 002](../theories/002_ai_supply_deflation.md)，並沿用「成本、價格、利潤與每股價值分開驗證」的原則。簡報是先前研究快照，不會因計算器參數變更而自動更新。
