# SpaceX算力：客戶合約、建設速度與太空時程查核

查核日：2026-11-20（台北）。範圍為使用者提供的Eric AI影片標題截圖（IMG_4808.jpeg）；未取得影片URL、完整影片或字幕，因此以下查核針對標題命題，未宣稱已審閱影片全文。截圖相對發布時間不等於原始消息發生日。

## 命題與估值用途

| 命題 | 已查到的證據與日期 | 分類及可用邊界 |
| --- | --- | --- |
| Anthropic租用SpaceX算力 | 雙方2026-05-06公告已簽Colossus 1合作；Anthropic 2026-11-17初步招股文件進一步列出多項SpaceXAI協議。[S1][S2][S3] | 公司披露。可校準交付後收入，但須計取消、續約、交付與履約風險。地面合約不能直接當太空訂單。 |
| 微軟「爭搶」SpaceX算力 | 近期媒體轉述Nadella表示有可租容量就願意租，未列價格、開始日或合約公告。[S4] | 媒體轉述的條件式意願；本輪未核驗原始完整訪談。未找到已簽約的數量／金額，不建立確定營收。 |
| 2029年大部分算力在太空 | SEC收錄2026-06-08 CFO訪談：預期2027展示、若按目標2028開始飛行、2029有具規模的太空算力。[S5] | 管理層前瞻路徑，不是實績；已讀原文未提供2029太空占比或多數門檻。不能把「有具規模」升格為「大部分」。未聲稱所有後續發言都不存在該目標。 |
| SpaceX四個月蓋好資料中心 | NVIDIA 2024-10-28公告Colossus設施與系統122天完成；屬特定歷史案例。[S6] | 公司／供應商披露的案例，不代表所有GW級新址可四個月完成。 |
| 其他公司都要1–4年 | SemiAnalysis 2026-11-03自有研究列MiniHard約五個月、Gun Range目標四個月，文中同類建設比較多為8–12個月。[S7] | 支持部分項目的速度優勢；不支持對所有競爭者、所有建設範圍一概用1–4年。Gun Range是目標，非已完工實績。 |

## Anthropic：可用於收入校準的條款

來源為Anthropic官方IPO網站2026-11-17初步招股文件，PDF第193頁（0起算192頁），內文印刷頁180、Infrastructure Service Arrangements。[S3] 初步文件可能更新，使用時應保留版本日期。

- 2026年5月至10月簽訂及修訂多項SpaceXAI協議。
- 協議期間延伸至2029年，合計支出最高約1,205億美元，並非無條件保證的確定訂單餘額。
- 全部容量交付後，合計每月約31億美元；文件預期2026年12月達到，爬坡期間費率不同。
- 以31億乘12個月，年化為372億美元；這是交付及持續履約成立時的年化值，不是2026實際收入，也不是新增於既有SpaceX算力收入之外的一筆收入。
- 各協議初始不可取消期間分別至2027年1月、3月；之後任一方可提前90天書面通知取消。不能把全期最高額當成不可取消多年backlog，亦不能據此斷言已取消。
- 最新數字涵蓋多項協議；早期每月12.5億美元是先前披露口徑，不應再與每月31億相加。需依合約範圍及修訂橋接，避免重算。

初始Colossus 1公告所列逾300MW／22萬GPU，與後來多項協議合計每月31億美元不是同一已對齊容量範圍；未取得最新對應MW、GPU組合及SLA前，不能用31億除300MW推導整體租價。

## 建設速度如何傳導至估值

122天為NVIDIA披露的特定設施／系統案例；從首個機櫃進場到開始訓練另為19天。[S6] 兩者起訖不同。SemiAnalysis區分改建、擴建與新建，Gun Range四個月仍為目標。[S7]

估值應按場址分開「土地／許可／前置工程→土建→電力及冷卻可用→GPU到貨→測試驗收→付費投運」。四個月土建或整合不保證四個月完成全部電網、可靠度與客戶驗收，也不代表投入成本按工期同比下降。較快交付可提早收入與降低資金占用，但必須保留施工前置付款、能源、備援、維護及融資成本。不能同時在容量爬坡與額外速度溢價重複加值。

## 太空時程與現行主模型

官方CFO訪談支持管理層對2029有具規模太空算力的期待，未直接證明2029多數容量在太空，也未證實太空各年一年回收。[S5]

以本次查核時主模型版本[7722b49](https://github.com/WangChengYeh/AI_eco/commit/7722b496550bfc169eb842a0c287b7b950ef14cb)為例：2029年底太空51.81GW、地面18.1012GW，太空占兩者約74.11%。這是模型技術容量假設，不是公司實績、已獲准發射量或由本影片驗證的指引；年底占比也不同於全年平均容量或營收占比。模型已涵蓋此積極路徑，不再另加一次「太空占多數」溢價。

地面與太空2027–2031均12個月回收，是使用者指定條件；目前以完整成本及主預測利用率反推必要價格。先指定回收期得到的價格，仍須以外部成交價、對應設備／MW、有效付費需求及成本檢驗。這些新證據不會自行把回收假設升格為實績，也不證實模型的2031股數、持股保留比例或股價。

## 本輪更新與下一步校準

本輪只補證據及估值適用邊界，未修改current.json、租價、容量、回收目標、現金、股數或估值數字。機器可讀來源更新於[reference_facts](../calculator/configs/reference_facts.json)，尚未建立新數據到模型輸入的映射。

後續應先建立各客戶／各批次的交付月份、實收費率、可取消期間及續約，再與「容量×對外份額×利用率×單價」的總收入對帳。Anthropic收入應包含在對應算力分部，不能在分部外再加；微軟僅作未簽約需求情境，太空收入須配對真實交付與客戶合約。合約總額不直接當市值，仍須扣完整投入、營運成本、稅、利息與稀釋。

相關計算：[回收及逐月融資報告](../research/spacex_payback_financing_2026-11-20.md)、[兩公司股數報告](../research/share_dilution_2026-11-20.md)。

## 原始來源與存取限制

- [S1：Anthropic合作公告，2026-05-06](https://www.anthropic.com/news/higher-limits-spacex)：公司正文已讀，含Colossus 1合作及太空合作興趣。
- [S2：SpaceXSI合作公告，2026-05-06](https://x.ai/news/anthropic-compute-partnership)：公司正文已讀；太空仍是合作興趣，不是已下單的多GW太空合約。
- [S3：Anthropic初步招股文件，2026-11-17](https://ipo.anthropic.com/documents/us/prospectus.pdf)：官方PDF第193頁／印刷頁180條款已讀；日期見封面，未將初步文件視為最終版本。
- [S4：EconoTimes，2026-11-19](https://econotimes.com/Microsoft-CEO-Nadella-Says-SpaceX-Lease-Depends-on-Available-Capacity-1779316)：可讀媒體正文／索引轉述的條件式意願；本輪未核驗原始完整訪談，亦未找到合約公告，不據此設定已簽金額。
- [S5：SpaceX SEC收錄CFO訪談，2026-06-08](https://www.sec.gov/Archives/edgar/data/1181412/000162828026041761/fwp_cfointerview.htm)：原始申報逐字稿已讀；屬該日管理層前瞻目標，非2029實績。
- [S6：NVIDIA公告，2024-10-28](https://nvidianews.nvidia.com/news/spectrum-x-ethernet-networking-xai-colossus/)：供應商原始公告已讀，122天及19天為不同起訖。
- [S7：SemiAnalysis原始研究，2026-11-03](https://newsletter.semianalysis.com/p/elon-is-doing-it-again-spacex-will)：公開可讀段落已讀，未聲稱已讀付費部分；自有研究／場址觀察不是公司完工驗收文件。

搜尋記錄：`Microsoft SpaceX compute capacity deal signed November 2026`、`SpaceX Microsoft talks November 2026 four months data center 2029 primarily space`、`SpaceX 2029 majority compute space Bret Johnsen Morgan Stanley November 2026`、`site:nvidia.com Colossus 122 days four years`、`site:semianalysis.com SpaceX MiniHard Gun Range four months November 2026`。搜尋未找到，不等於證明所有未公開交易不存在。
