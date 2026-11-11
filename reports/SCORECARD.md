# Effect recovery scorecard

> Simulated data. This compares estimates made WITHOUT the answer key against the planted truth.

| Effect | Planted | Estimated from data | Status |
|---|---|---|---|
| E1 Ramadan / pre-Ramadan / Eid (Hijri) | ramadan x0.85, pre_ramadan x1.1, eid x0.4 | ramadan x0.87 (95% CI 0.82-0.92), pre_ramadan x1.07 (95% CI 0.99-1.15), eid x0.41 (95% CI 0.26-0.65); Hijri LightGBM WAPE in Feb-Apr 2025 10.3% vs Gregorian 12.1% | **recovered** |
| E2 Semavia launch ramp | midpoint month 18.0, scale 3.5 | midpoint month 18.1, scale 3.45 | **recovered** |
| E3 Semavia stock-out months | months [21, 22, 33] | flagged [('SEM', 21), ('SEM', 22), ('SEM', 33)]; precision 100%, recall 100% | **recovered** |
| E4 Glucora generic entry | month 20, max volume loss 45%, tau 4.0 | month 20, max volume loss 47%, tau 5.5 | **recovered** |
| E5 Rep vacancies | 4 windows, sales x0.65 | 4/4 windows matched from roster; sales x0.654 (95% CI 0.636-0.674) | **recovered** |
| E6 Unfairly targeted territories | 5 territories (3 easy, 2 hard) | 22 flagged; precision 23%, recall 100%, direction correct 5/5; false positives ['KSA-BAH-01', 'KSA-EAS-01', 'KSA-EAS-02', 'KSA-HAI-01', 'KSA-JAZ-01', 'KSA-MAK-02', 'KSA-MAK-03', 'KSA-MAK-07', 'KSA-MED-01', 'KSA-NAJ-01', 'KSA-NBR-01', 'KSA-QAS-01', 'KSA-RIY-02', 'KSA-RIY-03', 'KSA-RIY-07', 'UAE-AUH-01', 'UAE-DXB-03']; missed none | **partially recovered** |
| Feed messiness (data validation) | quarantined_non_positive_sale 8; quarantined_unknown_product 6; duplicate_rows_removed 200; restated_lines_resolved 117; valid_return_lines_kept 4034 | quarantined_non_positive_sale 8; quarantined_unknown_product 6; duplicate_rows_removed 200; restated_lines_resolved 117; valid_return_lines_kept 4034 | **recovered** |
