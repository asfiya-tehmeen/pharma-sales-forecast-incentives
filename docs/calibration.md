# Calibration sources and assumptions

> All rep-level sales, targets and payouts in this project are **simulated**. Only the market-level inputs below come from public sources. Every source was checked on the web on 2026-11-11. The status column says how far each figure was verified.

**Status labels**
- **verified:** the figure was seen on the cited page.
- **verified (secondary):** the figure was seen on a page that republishes the primary source; the primary page itself could not be reached.
- **unverified:** seen only in a search snippet. Not used for calibration.
- **assumption:** no usable public figure; the value was chosen by the author.

## Sources used

| ID | Figure | Value used | Ref. period | Source | Status |
|---|---|---|---|---|---|
| S1 | KSA population by region (13 regions, total 32,175,224) | `data/calibration/regions.csv` | Census 2022 (GASTAT) | GLMM table "Population by nationality and administrative region, 2022", citing GASTAT Saudi Census 2022: https://gulfmigration.grc.net/?p=9681. The GASTAT census portal (saudicensus.sa) did not resolve at check time. | verified (secondary). The 13 regions sum exactly to the total. |
| S2 | Dubai population | 4,580,000 | end-2025 | Dubai Data and Statistics Establishment release, via Zawya: https://www.zawya.com/en/press-release/government-news/dubai-digital-dubais-population-tops-4580mln-by-the-end-of-2025-recording-75-growth-415335 | verified |
| S3 | Abu Dhabi population | 4,135,985 | 2024 | Statistics Centre Abu Dhabi: https://scad.gov.ae/w/abu-dhabi-population-in-2024-grows-7-5-to-reach-4-14m | verified |
| S4 | Adults (20–79) with diabetes | KSA 5,344.6k (crude prevalence 21.4%); UAE 1,274.2k (16.5%) | 2024 | IDF Diabetes Atlas 11th ed. (2025), MENA factsheet: https://international-diabetes-federation.s3.eu-west-1.amazonaws.com/media/uploads/sites/3/2025/08/IDF_Atlas_11_2025_MENA_Factsheet.pdf | verified |
| S5 | Saudi pharma market growth | about 5% a year (used as the volume trend) | 2024 → 2030 | Germany Trade & Invest (GTAI), citing Fitch Solutions, page dated 15 Jan 2026: https://www.gtai.de/de/trade/saudi-arabien/branchen/markttrends-940980 | verified |
| S6 | Ramadan and Eid dates, 2023–2025 (Saudi, Umm al-Qura) | Ramadan starts 23 Mar 2023, 11 Mar 2024, 1 Mar 2025; Eid al-Fitr 21 Apr 2023, 10 Apr 2024, 30 Mar 2025; Eid al-Adha 28 Jun 2023, 16 Jun 2024, 6 Jun 2025 | 2023–2025 | Several outlets agree, e.g. Al Jazeera (2023 start), Al-Monitor (2024 Eid al-Fitr), Arab News (2025 Eid al-Fitr; 2023 and 2024 Eid al-Adha). The calendar itself is computed with `hijridate` (Umm al-Qura), and `tests/test_calendar.py` checks it against these dates. | verified (some dates from snippets; all agree across outlets) |
| S7 | SFDA list prices (SAR per pack) | Glucora = median sitagliptin 100 mg = **84.20**; Semavia = median semaglutide pen 0.25/0.5/1 mg = **418.65**; Cardivex = median atorvastatin 20 mg = **43.45** | scraped 2026-11-09 | Public SFDA drugs list (https://www.sfda.gov.sa/en/drugs-list), scraped by Project A (`../a-sfda-drug-price-analysis`); rows copied to `data/calibration/sfda_reference_prices.csv` by `scripts/extract_sfda_prices.py` | verified (from scraped data). Project A's scrape is partial, so a molecule's full price range may be missing. |

## Assumptions (not verified)

| ID | Assumption | Why |
|---|---|---|
| A1 | "Sharjah & Northern Emirates" = 3,000,000 people | Sharjah Census 2025 (2,135,888) was seen only in snippets. Ajman, Fujairah and Umm Al Quwain figures are unverified or outdated, and no official Ras Al Khaimah figure was found. Used only as a relative weight for splitting UAE territories. |
| A2 | Diabetes prevalence is the same in every region of a country | IDF publishes national figures only. |
| A3 | UAE prices equal KSA SFDA prices, and prices are constant over 2023–2025 | Keeps one currency (SAR). 2026 list prices are applied to 2023–2025. |
| A4 | The brand Glucora is priced like the sitagliptin 100 mg packs in the scrape, which are generics | Project A's partial scrape has no originator sitagliptin row. |
| A5 | Company uptake: monthly packs per adult with diabetes = 0.020 (Glucora), 0.010 at Semavia's peak, 0.030 (Cardivex) | Sets each product's scale. Not a market-share claim. |
| A6 | UAE volume growth = KSA (5%/yr) | No verified UAE growth figure was found. |
| A7 | On-target bonus SAR 40,000 per rep per year; payout curve as in `config.py` | Typical plan shape. Not a benchmark claim. |

## Not used (could not be verified, or low reliability)

- **IQVIA KSA forecast of SAR 83.3 bn by 2029 (10.8% CAGR):** the source PDF returned 404.
- **Market sizes from market-research vendor marketing pages** (IMARC, Fortune Business Insights and others): they disagree with each other by more than 2×.
- **UAE pharma market size (AED 17.2 bn, JLL 2025):** the page cites no data source. Not needed for calibration.
