# WLA Detector Test Lab

A local research prototype for exploring the WLA retail price-reset detector on synthetic scenarios and uploaded datasets.


## Start

1. Install Python 3.10+.
2. From this folder run `run_wla.bat` (Windows) or manually:
   ```bash
   cd backend
   python -m pip install -r requirements.txt
   python -m uvicorn app:APP --host 127.0.0.1 --port 8000
   ```
3. Open http://127.0.0.1:8000.

## Current capabilities
- Synthetic scenario selector and CSV/TSV/XLSX/JSON upload.
- Dataset summary, data validation, and price-series chart.
- Runs the research detector implementation adapted from `wla_sensitivity_experiment.py`.
- Raw, flag-only, and robust-treated event lists.
- Parameter controls: reset threshold, anomaly threshold, persistence.
- Synthetic event evaluation using one-to-one event matching within ±3 days.
- Run history and event CSV export.


## Detector fidelity and interpretation
- The detector logic is adapted from the functions in the original `wla_sensitivity_experiment.py`; research files are not imported or executed (avoids their output side effects).
- Defaults correspond to R30_A50_P2: reset threshold 30%, anomaly threshold 50%, persistence 2 observations.
- Local window = 3 observations; neighbor tolerance = 15%; event matching tolerance = 3 calendar days.
- Upward-only is the baseline behavior from the supplied sensitivity script. Bidirectional is offered as an extension and should not be described as the exact baseline.
- Synthetic evaluation compares detector events with scenario expectation metadata, not human-annotated real-world ground truth. Metrics are indicative of the synthetic test pack only.
- The current research baseline detector's reset rule is upward-only; downward scenarios are excluded from baseline metrics. In bidirectional extension mode, downward expectations are evaluated too.
- This is a prototype, not a production monitoring or consumer price analytics system.

## Recommended demo sequence for presentation
1. Choose **gap_then_change** from the synthetic scenario selector. Keep the research baseline: reset 30%, anomaly 50%, persistence 2, upward-only.
2. Click **Run detector**. Open **Events** to show Raw / Flag-only / Robust-treated counts and the event table.
3. Open **Evaluation**. The gap scenario is designed to contain an upward reset; evaluation is event-level with a ±3-day match window.
4. Switch to **permanent_increase** and run with the reset threshold at **20%** to demonstrate threshold sensitivity (the generated jump can be below 30% after noise, so baseline 30% may correctly miss it).
5. Switch to **permanent_decrease** and select **Bidirectional (extension)** at reset threshold 20% to demonstrate the downward detection extension.
6. **Experiments** shows run history. Export detected events from Events.

Do not present synthetic metrics as empirical real-retail accuracy.

## Update: country comparison + working synthetic evaluation/sensitivity
- Explore with **All countries** now plots separate country lines for the selected product instead of silently restricting to the first country-product.
- Country-specific selection chooses a valid product in that country; product options update from that country.
- Real-data Evaluation clearly states ground truth is unavailable instead of showing synthetic empty-state metrics.
- Synthetic Evaluation shows the scenario's TP/FP/FN and precision/recall/F1 after detector run.
- Experiments now includes a working **Run 36 configurations** sensitivity grid (4 reset thresholds × 3 anomaly thresholds × 3 persistence values), with aggregate TP/FP/FN and P/R/F1 for the selected synthetic scenario.

## Synthetic evaluation fix (v0.2.1)
- Evaluation now checks the selected scenario/run ID and will not display metrics from a previous synthetic scenario.
- The Evaluation tab shows a scenario-specific interpretation and a status after a run: PASS for expected no-reset scenarios with zero detections, PASS/MISS for expected upward or gap changes, partial/pass for multiple resets, and an explicit baseline note for downward scenarios.
- The backend exposes `/api/scenario-analysis` for scenario expectation, interpretation, and outcome status.
- Real-data mode remains explicitly unscored without ground-truth labels.
