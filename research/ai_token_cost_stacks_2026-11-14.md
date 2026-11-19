# 案例 002：AI token 價格與五條算力供應鏈

> 版本說明（2026-11-20）：本文件保留2026-11-14研究快照；歷史價格、榜單與營運數據不能直接當成今日報價或2027預測輸入。最新forecast及資料校準範圍見[完整檢查報告](full_review_2026-11-20.md)。

- 查核日：2026-11-14；價格為當日公開頁面快照，美元／百萬 tokens。
- 用途：驗證[理論 002](../theories/002_ai_supply_deflation.md)「持續降低完整任務成本」；與[Robotaxi 案例](robotaxi_tesla_waymo_uber_taxi_2026-11-14.md)並列。
- 結論：已有地面合作與硬體效率進展；尚缺五條供應鏈在同品質、同延遲下的完整成本，不能宣告成本冠軍。太空項目仍列為條件情境。

## 一、先分三種價格

| 指標 | 付錢的人 | 回答的問題 |
| --- | --- | --- |
| API token 售價 | 應用開發者付模型／雲端平台 | 使用這個服務要付多少錢？ |
| 算力採購價 | 模型公司付雲端／算力供應商 | 預留或實際使用設備容量的合約成本？ |
| 完整任務成本 | 使用者或供應商，須指定視角 | 一項驗收通過的工作究竟花多少？ |

API 定價包含產品定位、競爭、促銷與利潤策略，不能倒推出電價或推論毛利。算力租約也不等於股票付款：本案例未以採購合作證明直接股權支付。

模型供應商的生產成本與應用使用者支付的 API 費是不同口徑；使用者成本不可再加一次供應商的電費與設備折舊。合併供應鏈分析時，內部移轉價格亦不能重複計算。

## 二、五條供應鏈：電力 × 晶片 × 模型

下表「優勢」均是待驗證的降本途徑，不是最低成本排名。

| 組合 | 電力與設施 | 晶片／系統 | 模型及合作狀態 | 核心待驗證問題 |
| --- | --- | --- | --- | --- |
| Claude＋SpaceX 地面 | Colossus 地面設施；SpaceX 申報描述電網、自建天然氣發電、Megapack 與廠房改造 [S1–S3] | 官方合作公告列 NVIDIA H100、H200、GB200 等；不能把 GPU 顆數直接相加視為等效算力 [S2] | Claude 由 Anthropic 提供；2026-05-06 正式公布算力合作 [S1–S2] | 快速建置與能源整合，是否降低 Anthropic 實付的每項成功任務成本？節省由誰保留？ |
| Claude＋SpaceX 太空 | 構想使用軌道太陽能與輻射散熱；須含部署、通訊及設備汰換 [S2、S4–S5] | 未取得足以建立商業成本基準的確定晶片、量產配置與在軌壽命 | Anthropic 表達參與多 GW 軌道算力開發的興趣；本次未找到已商轉供應 Claude 的可比成本證據 [S2] | 每公斤部署成本、每瓦系統重量、利用率及壽命達到何值，才勝過地面？ |
| Google | 自有資料中心與能源採購／營運整合；不表示所有電力自產 | 自研 TPU、模型與系統協同設計；Google 自述 Ironwood 每瓦性能較 Trillium 提高一倍 [S6] | Google DeepMind 的 Gemini；自研硬體不等於自行晶圓製造 | 同任務實際 tokens／秒、焦耳／任務與全成本，是否持續領先？ |
| OpenAI＋Microsoft | Azure 地面資料中心與供電體系；個別工作負載的合約電價未知 | Azure 有 NVIDIA GB200／GB300；Maia 亦執行 OpenAI 模型，不能把全部 OpenAI 工作負載視為同一晶片 [S7–S8] | OpenAI 模型；Microsoft 仍是主要雲端夥伴，2026-04 修約後非獨家 [S9] | 系統效率、利用率及模型部署優化能否抵銷雲端費與商業分潤？ |
| OpenAI＋Oracle | OCI／Stargate 地面設施；電力、土地、建設與供應商協作 [S10–S11] | Abilene 已有 NVIDIA GB200，OpenAI 稱 GPT-5.5 在該站訓練 [S10] | 模型仍屬 OpenAI；Oracle 提供算力與雲端，不是另一個 OpenAI 模型 | 大規模交付、設備效率與合約條件，能否帶來較低的有效算力成本？ |

### 合作與容量的證據邊界

- Anthropic 五月公告：取得 Colossus 1 超過 300 MW、逾 220,000 顆 NVIDIA GPU 的容量；這是公司公告的容量與交付規劃，不是本研究獨立測得的持續負載。[S1]
- 太空合作公告使用「表達興趣」並明列工程挑戰；不能直接升格成已完成多 GW 商用服務。[S2]
- Oracle 2025 年公告的額外 4.5 GW 是開發協議。OpenAI 2026 年更新有 Abilene 運行與模型訓練證據，仍不能把全部規劃容量當成已送電滿載。[S10–S11]
- Microsoft 關係應使用 2026-04-27 修約版本：保留主要雲端夥伴地位，OpenAI 可跨雲提供產品，IP 授權不再獨家；不沿用較早的全面獨家說法。[S9]
- 五列並非互斥陣營：Anthropic 亦使用 Google TPU、AWS Trainium 與其他 NVIDIA 算力；Google Cloud 2026-10 公告將提供 OpenAI 模型，公告當時仍是即將推出。[S1、S12] 本案 Google 列固定指「Gemini＋Google 基建」，避免與跨雲銷售混用。

## 三、公開 token 售價快照

下表採標準文字 API；不含快取、Batch、Fast mode、工具、雲端專屬議價與稅。不同模型沒有經本研究證明等品質；同一份文字在不同 tokenizer 下的 token 數也可能不同。

| 模型／服務 | 輸入 | 輸出 | 1M 輸入＋0.2M 計費輸出的帳單示例 |
| --- | ---: | ---: | ---: |
| Claude Fable 5.2，標準 API [S13] | $8 | $40 | $16 |
| Gemini 4 Carbon，至 2026-11-30 導入價 [S14] | $2 | $10 | $4 |
| Gemini 4 Carbon，2026-12-01 起已公告價格 [S14] | $4 | $20 | $8 |
| GPT-6.1 Sol，標準 API [S15] | $2 | $10 | $4 |

示例只是相同「計費數量」下的乘法，不是相同任務的能力、耗電或成本排名。推理模型需計入實際收費的思考 tokens；不可只計畫面顯示的答案。API 方案也不等於 ChatGPT／Claude 訂閱制成本。

Claude Fable 5.2 相對 5.1 的輸入／輸出牌價由 $10／$50 降至 $8／$40，均下降 20%。[S13] 這支持售價變化，尚未證明 SpaceX 供電或某一晶片造成降價。Google 已公告的導入價結束，更說明單次售價快照不能代表永久成本曲線。

「Claude＋SpaceX 地面」與「Claude＋SpaceX 太空」未有各自可直接購買、且能歸因至該設施的公開獨立牌價；OpenAI＋Microsoft／Oracle 亦不能直接套用同一 OpenAI API 價格，反推兩家供應商成本完全相同。須取得指定區域、模型版本、部署方式及合約的實付帳單。

## 四、真正應驗證的成本模型

### 供應鏈生產視角

同一期間、同一品質與服務要求：

```
基礎設施單位成本 =
（硬體與設施攤提＋電力＋網路＋營運維修）
÷ 可交付且通過品質要求的服務量

模型服務完整成本 =
基礎設施成本＋模型研發／訓練分攤＋驗證及其他營運分攤
```

訓練與推論分列，再揭露分攤方法。若採購的是含電費與設備的算力租約，使用租約支出替代相應自建項目，避免重複計算。設備購價與折舊亦擇一致口徑；融資負擔另揭露。實測應分 prefill／decode、上下文長度、記憶體／網路限制及達標延遲，不能用峰值 FLOPS 代替。

### 應用使用者視角

```
每項成功任務成本 =
（全部 API 帳單＋工具／外部服務＋人工驗證及整合費）
÷ 驗收通過任務數
```

所有失敗、重試、子任務與思考 token 支出都進分子；只把驗收通過的任務放分母。模型較貴但重試少，仍可能更便宜。需固定資料集、驗收規則、延遲上限與安全要求；不能以少量容易題目代表所有工程或醫療工作。

## 五、電價的影響有多大？純假設敏感度

以下均不是企業實測：

- 假設整個運算節點平均 IT 功率 1 kW，PUE 1.2、電價 $0.10/kWh，每小時電費為 1 × 1.2 × 0.10＝$0.12。
- 若電價減半、其他條件不變，節省 $0.06／節點小時；仍不能換算每百萬 token，因為缺少特定模型、批次、延遲與利用率下的吞吐量。
- 假設電力占完整生產成本 20%，電費降低 50%，總成本僅降低 10%；即使電費歸零，也最多省原成本的 20%，前提是其他項目不增加。
- 假設固定資本及營運支出每期 100、有效服務量由 50 增至 80，該部分單位成本由 2 降至 1.25，下降 37.5%；不是總成本下降 37.5%。

因此有便宜電力仍需配合晶片效率、記憶體、模型演算法、排程與需求。較高利用率若損害延遲或品質，不可當成等價成本改善。

## 六、太空算力的損益門檻

太陽光沒有燃料帳單，不代表電力系統免費。太空真空缺少對流，設備須把熱傳至散熱結構，再向外輻射；不能只因太空冷，就把散熱成本填零。[S5]

太空情境至少納入：

| 成本／限制 | 需要的數據 |
| --- | --- |
| 上軌部署 | 每公斤完整交付成本、系統 kg/kW、部署與在軌驗收成功率 |
| 電力與熱管理 | 太陽能板、電源轉換、儲能及散熱器的質量、效率與退化 |
| 晶片及衛星壽命 | 可用年限、輻射故障、備援、汰換頻率與可維修性 |
| 通訊與工作型態 | 星間／地面頻寬、延遲、資料傳輸費；訓練與推論適用性分開 |
| 營運及容量利用 | 在軌可用率、實際付費負載、地面站與終止任務成本 |

條件式判準：只有當「每項成功任務的地面電力／土地／冷卻等節省」大於「額外部署、太空設備、通訊、故障與汰換等成本」時，太空才取得經濟優勢；其他成本差異也須納入。SpaceX 招股資料本身描述軌道算力工程與重複使用等前提。[S4] 本次未取得可完整代入的公開數據，故不填虛構的每 token 太空價格。

## 七、台積電與價值分配

晶片設計、晶圓製造、先進封裝、HBM 記憶體與雲端部署要分開觀察。NVIDIA Blackwell 使用台積電 CoWoS 先進封裝；這是製造與封裝價值鏈，不代表台積電決定 Claude 或 GPT 的 API 售價。[S16]

即使 Google 或 Microsoft 採自研加速器，仍須追蹤實際代工、封裝、記憶體、良率與交付成本；本案不推定每個晶片型號的製造來源均相同。模型公司省下採購費，不必然代表代工廠利潤同步下降，也不必然代表消費者取得全部節省。

## 八、對理論 001＋002 的判斷

| 命題 | 本次能支持什麼 | 尚不能支持什麼 |
| --- | --- | --- |
| 整合能源、晶片、模型可降本 | 供應鏈整合、硬體每瓦性能進展與公開價格變化 | 五家同品質完整成本排名 |
| 降本可以轉為降價與擴張 | 更大容量與服務價格調整已有公告 | 單一基建合作造成某次模型降價的因果 |
| 持續降本者可形成競爭壓力 | 可用成功任務成本與追趕時間檢驗 | 預先認定 Google／SpaceX 永遠勝出 |
| 股權資源交換可強化循環 | 後續可連結融資、設備與能源投資 | 算力合約本身即證明用股份付電費或已取代貨幣 |
| 公司成長提高股東購買力 | 後續追蹤稀釋後每股現金流與投資回收 | token 用量增加即保證股價報酬 |

本案例最重要的可驗證命題：**誰能持續降低同品質成功任務的完整成本，並在降價後保留正向經濟收益，誰才具備理論 002 所指的動態成本優勢。** 電力、晶片、模型要一起看，還要檢查節省最後留在模型商、雲端、晶片商、代工廠或使用者哪一層。

## 九、後續最小數據集

這是研究欄位，並未另設自動追蹤任務。

1. 每月保存模型版本、標準／快取／Batch／思考 token 費率、促銷期限、實付帳單。
2. 使用固定任務集，保存驗收率、總計費 tokens、人工修正時間、延遲及每成功任務支出。
3. 基建分別保存已送電／已安裝／已驗收容量、設備世代、可用率與有效利用率。
4. 能取得時保存電價、PUE、焦耳／成功任務、設備攤提、合約最低採購義務及研發分攤。
5. 連續比較成本降幅、售價降幅、利潤與每股現金流；未知欄位留白，不以 GPU 顆數或 MW 替代。

## 來源

- [S1：Anthropic，Higher usage limits and a SpaceX compute deal，2026-05-06](https://www.anthropic.com/news/higher-limits-spacex)
- [S2：SpaceXSI，New Compute Partnership with Anthropic，2026-05-06](https://x.ai/news/anthropic-compute-partnership)
- [S3：SpaceX 招股申報，地面供電、Colossus 建設與整合](https://www.sec.gov/Archives/edgar/data/1181412/000162828026039276/spaceexplorationtechnologi.htm)
- [S4：SpaceX EU Prospectus，2026-06-05，軌道算力計畫與風險](https://content.spacex.com/cms-assets/FINAL_Documents%20and%20Updates/SpaceX%20-%20EU%20Prospectus%20%28Approved%20by%20Bafin%29%20-%20June%205%2C%202026.pdf)
- [S5：NASA，Small Spacecraft Technology State of the Art，2021，Thermal Control](https://www.nasa.gov/wp-content/uploads/2021/10/soa_2021_1.pdf)
- [S6：Google 2026 Environmental Report，2025 年績效與 TPU 協同設計；公司自述](https://storage.googleapis.com/gweb-mobius-cdn/sustainability/uploads/21455428735c7305f2cb5c0038fc14bb0803abb8.pdf)
- [S7：Microsoft，Azure GB200／GB300 inference，2026-11-13；公司測試](https://techcommunity.microsoft.com/blog/azurehighperformancecomputingblog/azure-vms-deliver-inference-performance-in-line-with-industry-benchmarks/4573039)
- [S8：Microsoft，Maia 多 GW 部署計畫，2026-10-12](https://blogs.microsoft.com/blog/2026/10/12/microsoft-to-expand-azure-maia-system-to-multi-gigawatt-deployments/)
- [S9：Microsoft，修訂 OpenAI 合作條款，2026-04-27](https://blogs.microsoft.com/blog/2026/04/27/the-next-phase-of-the-microsoft-openai-partnership/)
- [S10：OpenAI，Building the compute infrastructure for the Intelligence Age，2026-04-29](https://openai.com/index/building-the-compute-infrastructure-for-the-intelligence-age/)
- [S11：OpenAI，Stargate／Oracle 4.5 GW 協議，2025-07-22](https://openai.com/index/stargate-advances-with-partnership-with-oracle/)
- [S12：OpenAI，Google Cloud 模型合作公告，2026-10-21](https://openai.com/index/openai-models-google-cloud/)
- [S13：Anthropic，Claude Fable 5.2，2026-11-09](https://www.anthropic.com/claude/fable)
- [S14：Google Gemini Developer API pricing，含導入價截止與後續價格，2026-11-14 查核](https://aistudio.google.com/docs/pricing)
- [S15：OpenAI，GPT-6.1 Sol 模型費率，2026-11-14 查核](https://developers.openai.com/api/docs/models/compare?model=gpt-6.1-sol)
- [S16：Reuters，NVIDIA Blackwell／TSMC CoWoS，2025-01-16](https://www.marketscreener.com/quote/stock/NVIDIA-CORPORATION-57355629/news/Nvidia-CEO-says-its-advanced-packaging-technology-needs-are-changing-48782596/)

來源中的規劃、公司自述與性能測試，均不視為本研究獨立驗證的成本結果。

