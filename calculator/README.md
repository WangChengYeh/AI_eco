# Tesla／SpaceX 年度營收、獲利與股價 Calculator

Python 3.10 以上，僅使用標準函式庫，無需安裝套件。預設計算 2027–2031 年，可在 JSON 修改年度、業務與假設。

預設讀取 [current.json](configs/current.json)，持續修正同一份累積分析。**除了明列的使用者假設，其餘數字（包括股數、現金、負債、倍數與換股比例）仍為未校準示例，不是公司指引。** 公司實際披露另存於 [reference_facts.json](configs/reference_facts.json)，不會自動覆寫模型。初始教學用 [example.json](configs/example.json) 保留供對照，不再是預設。

只有一份主預測。`base` 是內部識別碼；修訂由 Git 保存，不是可選情境。「目前修正」不是情境名稱。`bear`／`bull` 只供敏感度檢查，不代表不同修訂版本。檢視原則見 [FORECAST_REVIEW.md](FORECAST_REVIEW.md)，最新重算見 [forecast_summary.md](forecast_summary.md)。

## 快速開始

標準流程統一為 [四步驟 SOP](../SOP.md)：理論 → 數據 → Forecast Python → HTML。查核資料後使用 `python calculator/run_pipeline.py`，而不是只修改網頁數字。`configs/input_provenance.json` 將本輪Robotaxi關鍵參數連到使用者假設、公司披露或模型補充假設；目前仍非全業務已校準。

`configs/user_assumption_research.json` 覆蓋每項主預測使用者假設的網路及Musk訊息搜尋，另列重要理論強版本。新增／修改使用者假設必須同步重新查核，否則 pipeline 停止。查核完成不等於原數量獲證實；本輪保留條件計算數字，新增網頁查核表與[可讀報告](../research/user_assumption_review_2026-11-19.md)，逐項明列原始來源、Musk原貼／原片入口、轉述與讀取限制。

### Robotaxi 2027年中全速

主預測改用 `production_ramp`：`full_rate_year=2027`、`full_rate_month=7` 保留使用者時程；年化產速先以已披露裝置產能的下限125,000台作錨點。年初20%產速、半年線性爬坡、全部自持、部署延遲1月均為模型假設，不是公司已確認產速或部署承諾。

每月製造數量與投運月份分開。年底未投運車仍保留製造成本；未投運期間不計服務營收及折舊。月度製造量合計包含替換用途；啟用此模式不能另填 `additions` 或開啟自動額外替換，避免同一產能被用兩次。工廠產能限制使用製造量，營收使用實際平均服役車隊與付費里程。

### 網頁發佈

根目錄 `index.html` 及 `docs/index.html` 是相同的完整網頁，包含本份主預測結果、樣式及公司／年度切換。GitHub Pages 設定：repo **Settings → Pages → Deploy from a branch → main → /(root) → Save**；若原已選 `/docs` 也可直接使用。啟用後以 Pages 設定顯示的網站網址為準。

每次修正主預測後，執行 `python calculator/build_site.py` 同步重算兩個網頁入口及 `calculator/forecast_summary.md`，再提交 Git。網站顯示已計算的結果，不需要 Python 後端；圖表使用固定版本 D3 靜態資源。資料與分析延續同一份 `current.json`。

在 repo 根目錄執行：

```bash
# 重算同一份主預測（預設只產生 base）
python calculator/forecast.py --out forecast_output

# 額外執行保守／樂觀敏感度檢查
python calculator/forecast.py --scenario all --out forecast_output/sensitivity

# 使用你自己的 JSON
python calculator/forecast.py --config my_assumptions.json --scenario base
```

複製 [current.json](configs/current.json) 後修改，或用 `--set` 臨時覆寫。路徑拼錯會報錯，避免參數沒有生效。

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

# 修正同一分析的 2027 年太空算力製造量為 500 MW
# 發射部署容量亦須一起調整
python calculator/forecast.py --scenario base \
  --set 'companies.spacex.segments.orbital_compute.manufactured_it_mw.annual={"2027":500}' \
  --set 'companies.spacex.segments.orbital_compute.deployment_limit_mw.annual={"2027":500}' \
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
| Tesla | optimus_owned | 自持機器人，內用、出租、維運與替換 |
| Tesla | services_other | 充電、售後、租賃及其他年度校準項 |
| SpaceX | launch_external | 外部發射與太空合約的等效任務，不含自用發射 |
| SpaceX | starlink_consumer | Starlink 全年平均消費者付費用戶 |
| SpaceX | starlink_enterprise | 企業、政府、航空航海合約年度收入包 |
| SpaceX | direct_to_cell | 合作變現的平均等效付費連線，非官方揭露用戶量 |
| SpaceX | starlink_hardware | 對外終端硬體，台／年 |
| SpaceX | ground_compute | 地面算力租賃與自用基建的整體成本 |
| SpaceX | orbital_compute | 太空算力，採用使用者的 2027 年底大量量產時程假設 |
| SpaceX | grok_subscriptions | Grok 外部訂閱 |
| SpaceX | grok_api | Grok API，數量為「百萬計費 tokens」 |
| SpaceX | cursor | 平均付費席位 |
| SpaceX | x_and_other | X 廣告、其他及年度校準項 |

這些是分析細分，不代表公司將每項獨立揭露。`services_other`、`starlink_enterprise`、`x_and_other` 的示例 `units=1`，價格代表該年度收入包；成長在價格曲線表達，並非實際商品單價。可把它們拆成更多互不重疊的 `unit` 或 `subscription` 業務。

鋰礦、精煉、電池與自用機器人影響成本、capex 和折舊。只要沒有對外銷售，就不另創造合併營收。Starshield 等政府業務應依實際合約歸到外部太空任務或企業／政府通訊，避免兩邊重算。自有 Robotaxi 的生產不計對外賣車收入。暫未預設第三方車主平台業務；若新增，應只計平台費，不能把全額車資全算 Tesla 收入。

## 參數曲線

### 同一份分析：2027 年底太空算力量產

`current.json` 同時保留 Optimus 的既有修正，並將太空算力由原本未商轉的示例改為 `orbital_compute`。不是獨立的新分析，也不把量產時程視為公司已驗證進度。

- 使用者指定：2027 年底大量量產。
- 額外規模示例：2027 年製造 1,000 MW，10 月起均勻部署，最多部署 1,000 MW，投運成功率 100%；2028 起每年製造及部署 3,000 MW。這些數量、月份、成功率均可修改，不是使用者已指定的數字。
- 沒有退役時，全年平均可用 MW＝期初已投運 MW＋當年新投運 MW × `(13－部署起始月份) / 24`；有退役時按各月投運批次的實際服務期間積分。
- 因此示例 2027 年底為 1 GW，但 2027 年平均只有 0.125 GW；2028 的年平均為 2.5 GW，含前一年 1 GW 全年貢獻及當年新增容量的平均貢獻。
- 已製造但受 `deployment_limit_mw` 限制而未部署的設備留作庫存，不產生服務收入；次年可繼續部署。
- `commissioning_yield` 只對當年嘗試部署容量生效；失敗資產按可用帳面值記損失，不留下虛構投運容量。
- 製造投入＝當年製造 MW × `hardware_cost_usd_per_mw`，發射部署投入＝當年嘗試部署 MW × `deployment_cost_usd_per_mw`。兩者列 capex，不計內部發射銷售收入。
- 示範單位成本為硬體／衛星／發電／散熱／通訊 2,000 萬美元／MW，發射部署 500 萬美元／MW；4 年服務與折舊壽命是模型補充假設。按月度投運批次追蹤原始成本、折舊與退役，庫存採先進先出成本，未投運不折舊。失敗部署費用及設備成本當年認列損失。
- 對外服務份額 80%、自用 20%，地面算力不因太空量產而自動減少；不再額外把自用算力算成模型銷售收入。

目前預測期為2027–2031。Optimus全年產量依使用者最新假設為100萬、500萬、1,000萬台；2030–2031暫維持每年1,000萬台。季度分配為模型補充假設，另保留5年壽命及到期付費替換機制。太空設備 4 年後退役；每年 3 GW 新部署須同時替換到期容量與擴張，穩定年底容量為 12 GW，不能一直累加到 25 GW。壽命與替換規則需隨新資料更新。

### Optimus年度產量：100萬 → 500萬 → 1,000萬台

[optimus_10m.json](configs/optimus_10m.json) 僅保存早期單年計算供追溯，主預測一律使用 `current.json`：

```bash
python calculator/forecast.py --config calculator/configs/optimus_10m.json \
  --scenario optimus_10m --out forecast_output/optimus_10m
```

`robot_fleet` 計算自持機器人，年底數量＝期初＋當年生產－退役。`production_quarter_units` 可指定各年4季數量，必須與該年 `production_units` 相加一致；季內按月均勻投入，以資產批次計算年平均服務量。2027年各季4／12／28／56萬台，平均可用28.5萬台，不是100萬台全年可出租。未指定季度分配時才採全年均勻生產。

1. 先將年平均可用數量分配給 `internal_demand_robots`。
2. 剩餘數量可供出租；實際平均付費台數取「可租數量 × rental_utilization」與 `rental_demand_robots` 的較小值。
3. 外租營收＝平均付費台數 × `monthly_rent_usd` × 12。內用沒有銷售營收。
4. 內用避免成本＝平均內用台數 × `internal_avoided_cost_usd_per_robot_year`，仍受公司可改善製造成本上限約束；租賃收入不套用此上限。
5. 全部自持台數皆計維運成本，製造成本進 capex，折舊與退役帳面損失進成本並於現金流加回。主預測依投運批次計歷史成本及壽命，不以當年較低造價回溯重估舊設備。`replacement_units` 與原先 `production_units` 分列，合計為實際當年製造量。

主預測停用原先 Optimus 對外銷售，以及固定額度的機器人節省／capex／折舊，避免與自持資產重算。`robot_fleet` 的內用節省與固定 `robotics_savings_usd` 不能同時為正。

**使用者指定2027–2029全年產量路徑及內用優先、剩餘出租規則。** 使用者最新指定可租餘量付費出租率100%，每台3萬美元本輪明列按年解讀，即月租2,500美元。季度分配、2030–2031維持年產1,000萬台、內用需求100萬台、單台成本20,000美元與5年汰換仍為模型補充假設。累積持有量可超過年度產量，原先固定1,000萬台的累積持有上限已移除；出租需求上限已依100%付費出租條件移除；此為強需求假設，未查得官方租金及實際合約支持。

自持製造投入可能造成現金缺口，即使損益表獲利也不代表資金足夠。未明列融資前，資金缺口照實保留，股價仍顯示為融資前條件估值。此版內用節省只抵銷 Tesla 指定製造業務，不推定全部台數都能取代人工，也未自動把供 SpaceX 使用的台數當成合併內部交易。

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

車輛購置以 capex、折舊費用及現金流加回連結。主預測採 6 年服務與折舊壽命；年度總製造量同時提供擴張及替換，沒有額外自動加造退休替換車。既有 5,000 輛示例車視為 2027 年初新投入。`passenger_production_capacity` 檢查外部乘用車銷量＋自持車實際製造量，避免超出總產能；投運量不能代替製造量作檢查。

`robotaxi`／`robot_fleet`／`orbital_compute` 填入 `service_life_years` 啟用投運批次帳；`depreciation_life_years` 決定直線折舊期間；服務期短於折舊期時，退役認列剩餘帳面損失。自持車與機器人可用 `replace_retired=true` 在到期時等量替換，支付當年製造成本；太空算力依當年製造與部署上限投入，沒有額外免費替換。此模式的 `retirements` 必須為 0，避免自動與手動重複退役。歷史示例若不填服務壽命，保留原簡化方法；不可拿它作已校準的長期資產帳。

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

初始 example.json 的太空算力仍為 0；目前分析改用上列製造／部署模型。太空發電沒有外購電費時，也必須計入發電、散熱、通訊及汰換的資本與現金支出，不能只把地面電價改成 0 就當太空成本。

### 機器人降本

公司層節省只分配到 `robotics_eligible=true` 的業務，總額不超過「扣除折舊後現金成本 × automation_eligible_cash_cost_ratio」與「COGS × robotics_max_cogs_share」的較小值。主預測可自動化現金成本占比設 30%，是待校準成本拆分假設；不把折舊或全部材料成本當成可被機器人省掉。按合格現金成本分配，有效節省超額時截斷並警示。

參與分配的 `cost_includes_robotics` 必須設為 false，表示單位成本尚未包含**這筆額外節省**。原本成本曲線下降可代表材料、製程等其他改善，不能把同一機器人效果疊加。自持機器人推導的是避免的人工等成本，機器人維運及折舊已在 `robot_fleet` 費用化；不得再從避免成本重複扣一次。舊式固定節省模式則須自行填入扣除維運後的節省，並另填其 capex／折舊。不計內用營收。

## 公司獲利與現金流

```text
營業利益 = 各業務營業利益合計
         －corporate_opex_usd－sbc_expense_usd－robotics_da_usd
利息 = 平均年初／年底債務 × interest_rate
稅前利益 = 營業利益－利息
所得稅 = max(稅前利益, 0) × tax_rate
淨利 = 稅前利益－所得稅

現金 FCF 代理值 = 淨利＋D&A＋SBC＋股票支付營運費用
               －現金 capex－營運資金增加
現金 capex = 完整 capex－股票支付資本支出
經濟 FCF = 淨利＋D&A－完整 capex－營運資金增加
年底現金 = 年初現金＋現金 FCF 代理值＋新增借款－還款
         ＋股權募資－庫藏股－股利
```

`corporate_opex_usd` 排除另列 SBC 及內用機器人折舊。其他事業 opex 不應再含公司層另列 SBC。現金 FCF 加回非現金 SBC，但股本稀釋另計，保留它對每股價值的影響。經濟 FCF 保留全部資源成本作股東角度比較，現金餘額使用扣除股票代付部分後的現金 FCF。股票支付不代表資源免費，對價由新增股份與稀釋表達。

每年以營收乘 `nwc_revenue_ratio` 算年底營運資金，再扣除與上年差額。模型暫不含虧損扣抵、遞延所得稅、利息收入、非營業投資利得、少數股權與複雜租賃。需要時先調整設定及計算函數，不可把本模型稱為完整 GAAP 預測。

若出現資金缺口，不自動假設銀行借錢或投資人認股。資金需求、營運假設與估值算式分開：目前預設先依下節股票交換資源規則補足可支付部分；仍有剩餘缺口時，淨利為正仍可顯示 P/E 股價，股權價值為正仍可顯示 SOTP 股價，但標記 `valuation_status=conditional_unfunded`。這些是尚未計入額外融資利息／稀釋的條件估值，不表示資金不足仍可交付全部預測。請顯式加入借款、募資與稀釋後重跑；未解決的歷史資金缺口保留提示，不再永久遮蔽以後的估值。SOTP 的負現金以資金缺口抵減股權價值，不視為已取得透支額度。

## 理論 001：資金缺口用股票交換資源

同一份 `current.json` 已啟用 `stock_payment`。不是把缺口當成無法投資，也不是憑空增加現金；公司把原本要付現金的合格資源改以新股作對價。原始 `example.json` 及歷史情境保留未啟用狀態。

```json
"stock_payment": {
  "enabled": true,
  "capex_eligible_ratio": 1,
  "opex_eligible_ratio": 1,
  "acceptance_ratio": 1,
  "reference_price_usd": 250,
  "discount_rate": 0,
  "cash_buffer_usd": 0
}
```

參數含義：

- `capex_eligible_ratio`：資本支出中可交付股票交換的比例。
- `opex_eligible_ratio`：現金營運資源成本中可用股份支付的比例；排除折舊、既有 SBC、利息、稅、債務還款及分配。
- `acceptance_ratio`：交易對手在上述合格範圍願意接受股票的比例。目前設 100% 是理論情境，不是已取得的供應商承諾。
- `reference_price_usd`：交易雙方接受的每股資源交換價格，可用年度曲線。當前 Tesla 250 美元、SpaceX 100 美元都是原設定中的示例價，不是即時報價。
- `discount_rate`：資源交易中的股票折價，適用協議價為參考價乘以（1－折價）。折價越大，同量資源需交付更多股份。
- `max_new_shares`：可選的年度新發股份上限；未填時不另設數量上限，仍受合格資源額及對手接受度限制。
- `cash_buffer_usd`：希望保留的年底現金。預設 0，僅彌補現金需求，不為了多持現金而額外發股。

計算順序：先完成原有營運、借款、明列現金募資與現金收支，再計算需要替換的現金資源付款。優先用股份支付資本支出，再支付合格現金營運資源；發股數＝資源對價／折價後每股協議價。

**對應會計／經濟口徑：**

- 不新增營收，不把資產交換額列為現金募資收入。
- 股票支付 capex 時，保留完整資產取得成本與後續折舊，只減少現金投資支出。
- 股票支付營運資源時，費用仍列入損益，現金流加回該筆非現金支付。
- 新股加進年底及平均股本，再算 EPS、P/E 和 SOTP；以後年度繼續承接擴大後的股本。
- 交易價格獨立輸入，避免用同年稀釋後估值反推同年發股價格的循環。
- 若接受度、資源額或發股上限不足，保留剩餘資金缺口；不默認股票可直接繳稅或支付所有現金義務。

主要輸出：`funding_gap_before_stock_usd`、`stock_payment_usd`、`stock_paid_capex_usd`、`stock_paid_opex_usd`、`resource_shares_issued`、`resource_dilution_fraction`、`cash_capex_usd`、`funding_gap_usd`。已使用股票對價且沒有殘餘缺口時，估值狀態為 `stock_payment_assumed`；此標籤保留交易對手接受的假設，不表示交易已實現。

這是年度情境模型，未處理月度支付時點、交易費用、稅務與全部股份支付會計估值細節。它檢驗理論中的資源交換機制，不是將理論的普遍接受度先當成已被驗證。

## 股價情境：兩種方法

| 方法 | 計算 |
| --- | --- |
| P/E | 年度淨利 × pe_multiple ÷ 年底稀釋股數 |
| SOTP | （各業務營收 × 自訂 EV/Sales 倍數合計－公司費用資本化＋年底現金－年底債務）÷ 年底稀釋股數 |

SOTP 使用**企業價值**倍數，所以才加現金減負債；P/E 直接使用淨利的股權價值，不能再加一次現金。公司費用資本化為當年 corporate opex（含 SBC 與機器人折舊）乘 `corporate_ev_cost_multiple`。EV/Sales 對應企業價值，並不保證反映不同業務的合理毛利或持續投入，需自行校準。

發新股數＝`equity_raised_usd / equity_issue_price_usd`；庫藏股減少股數＝`buybacks_usd / buyback_price_usd`。SBC 稀釋率另外作用於股份。`stock_split` 只填拆股當年，例如 `{"value":1,"annual":{"2030":3}}`；發行與回購價必須使用當年拆股後單位。

輸出的 `eps_usd` 以年初／年底平均股份近似年度 EPS。`year_end_share_earnings_usd` 使用年底股份；上表 P/E 股價使用後者，以反映預測年底股本。兩者在募資或大量稀釋時會不同。淨利為零或負時，P/E 股價為 N/A，原因欄為 `non_positive_net_income`；SOTP 股權價值不正時，SOTP 股價為 N/A，原因欄為 `non_positive_equity_value`。資金缺口本身不觸發 N/A。仍保留原始股權值與資金缺口供診斷。

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
