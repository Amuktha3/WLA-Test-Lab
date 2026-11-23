# WLA Synthetic Prototype Test Pack

**All data in this pack is synthetic. Do not mix it with the real research dataset or report.**

## Files
- `data/synthetic_daily_prices.csv`: combined dataset using the prototype's raw-price schema (`country, product_id, day, lowest_price, shop`).
- `data/synthetic_products_catalog.csv`: product/scenario metadata.
- `data/synthetic_scenario_expectations.csv`: designed scenario transitions; use as test expectations, not ground-truth accuracy claims.
- `data/scenario_catalog.csv`: scenario descriptions.
- `scenarios/`: individual per-series CSVs.

## Scenarios represented
Stable series with small noise; permanent price increase; permanent decrease; temporary discount and restoration; one-day spike; lowest-price shop switch with near-stable level; gradual sub-threshold drift; noisy stable series; a gap before a price change; two permanent resets; short transient bump; small sub-threshold change. Several scenarios are replicated at different price scales/countries.

## How to use with WLA
1. Keep your original `pome` project untouched.
2. Open `data/synthetic_daily_prices.csv` in the Data Table Explorer (or load it separately for testing data/plots).
3. Test price-history visualization with `country` + `product_id` filters and date ranges.
4. Compare your detector's output against `synthetic_scenario_expectations.csv` **manually**. A designed synthetic scenario is useful for checking whether code responds as intended, but it is not a real-world benchmark and does not validate the research claims.
5. If you want to test the dashboard end-to-end with this pack, a separate synthetic project-root fixture is required because the dashboard reads many Phase 4–7 output files. This pack intentionally does not overwrite or imitate the real final results.

## Reproducibility
Generator seed: `20261122`. Date range: 2026-01-01 onward, 120 nominal days.
