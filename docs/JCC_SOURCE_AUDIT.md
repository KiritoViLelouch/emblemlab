# JCC source audit — 2026-10-10

**Outcome: BLOCKED for real JCC release.** No licensed, complete versioned JCC static export has been obtained. This is the result of the investigated sources, not a claim that no such source exists anywhere.

| Source inspected | Observed evidence | Reuse / ingestion decision |
|---|---|---|
| [Tencent official website](https://jcc.qq.com/) | Public homepage HTTP 200; SPA, copyright and registration information. Web search did not identify a documented reusable complete static-data contract. | No internal/private endpoints invoked. Official ownership does not by itself grant this project redistribution permission. No roster imported. |
| [DataTFT JCC](https://jcc.datatft.com/) | Actual browser visit: S18 navigation, homepage 18.3b label; `/units` displays patch 18.3. Footer says “All rights reserved.” “内容授权” opens a contact QR dialog; “数据集” navigates to a statistics table, not a licensed download. | User supplied this reference URL. No provider permission or export was supplied. No table copied into game records, no statistics ingested, no internal API called. Owner must contact the provider for a permitted export and redistribution scope. |
| [DataTFT TFT](https://www.datatft.com/?lang=en) | Public SPA reference; distinct international TFT site. | Does not establish JCC rules or cross-game equivalence. No data imported. |
| [MetaTFT](https://www.metatft.com/) | Public TFT reference. | No JCC-specific authorized complete export established. No scraping. |
| [Biubush/jcc_combination_selector](https://github.com/Biubush/jcc_combination_selector) | Author describes a genetic-algorithm learning project; inspected root does not show a data reuse license. | No complete reviewed patch/mode/equipment contract established; not imported. |
| [hy123666/Jcc-coach](https://github.com/hy123666/Jcc-coach) | README declares bundled S18 / 18.3 and dated ranking observations. | Application availability is not evidence of upstream data redistribution rights or independent emblem/population legality. Not imported; no scraping adapter copied. |
| [MinmusLin/Teamfight_Tactics](https://github.com/MinmusLin/Teamfight_Tactics) | MIT-labeled 2023 course implementation. | Code license and old course mechanics do not prove a complete real JCC roster/mode or game-art rights. No historical mode substituted. |
| [XJYdemons/JinChanChanTool](https://github.com/XJYdemons/JinChanChanTool) | GPL-labeled gameplay automation project. | Automation not used; code license does not establish upstream game-data/art reuse permission. Not imported. |

S18 / 18.3 is only a **provider-displayed research candidate**. No set name, release date, mode, roster completeness or current-game equivalence has been certified, so no JCC ruleset_id or active patch was invented. No alternative mode was silently selected. The existing TFT resource build is not used as a JCC source.

Exact evidence needed: an authorized source/export identifying JCC set ID/name, gameplay patch/release date, mode, complete roster (including special forms), costs, population costs, native contributions, thresholds, emblem mapping/equipment restrictions/duplicate policy, availability/unlock rules, and special nonmonotonic/conditional mechanics. Also required: public redistribution permission and icon reference rights, or a text-only export. A separate reviewer must verify the enabled scope.

No provider was contacted or messaged automatically. No private endpoint, authentication bypass, rate-limit bypass, match statistics import or real reforge EV was attempted.
