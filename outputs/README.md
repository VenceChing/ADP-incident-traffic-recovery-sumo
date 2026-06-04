# Outputs Directory Guide

This directory contains generated experiment artifacts. Most raw run outputs are ignored by git because they can be large and are reproducible from the configs. The selected comparison figures and seed-ranking summaries for the real-map experiments are committed for quick review.

## Top-Level Layout

```text
outputs/
  runs/
    selected_methods_vs_baselines/
    real_world_final_reproduction_rate1000/
    real_world2_final_reproduction_rate1000/
    real_world_seed_search/
    real_world2_seed_search/
    real_world_debug_smoke_train/
```

## `runs/selected_methods_vs_baselines`

Original 4x4-grid comparison artifacts used as the visual template for the real-map comparison charts.

Important files:

- `selected_methods_vs_baselines_horizontal_v2.svg`: reference chart format.
- `selected_methods_vs_baselines.svg`: older vertical/summary comparison chart.
- `selected_methods_vs_baselines_horizontal.svg`: earlier horizontal chart.
- `combined_summary.csv`: method-level metrics used by the chart.
- `pairwise_vs_greedy.csv`: paired comparison against greedy.

## Real-Map Final Reproduction Runs

Two main real-map experiment roots were generated:

```text
runs/real_world_final_reproduction_rate1000/
runs/real_world2_final_reproduction_rate1000/
```

Both use the same experiment workflow as the final-version project, but with real SUMO maps and route files:

- `real_world`: `scenarios/real_world/map.net.xml`, route `map_rate1000_balanced_short.rou.xml`
- `real_world2`: `scenarios/real_world2/map2.net.xml`, route `map2_rate1000.rou.xml`
- Training episodes: 50
- Main evaluation episodes per controller: 24
- Main evaluation seed: 7
- Traffic demand used for real-map runs: rate 1000

Each real-map root contains these subfolders:

```text
checkerboard_train_50/
checkerboard_ckpt20_eval24/
random_zero_eval24/
grid4x4_transfer_eval24/
greedy_eval24/
max_pressure_eval24/
fixed_time_eval24/
selected_methods_vs_baselines/
```

### `checkerboard_train_50`

ADP training output for the real map.

Files:

- `train_metrics.csv`: one row per training episode.
- `training_metrics.svg`: training progress chart.
- `adp_agent_weights.json`: final trained ADP weights after 50 episodes.
- `checkpoints/episode_0001.json`: checkpoint after episode 1.
- `checkpoints/episode_0010.json`: checkpoint after episode 10.
- `checkpoints/episode_0020.json`: checkpoint used by the main ADP evaluation.
- `checkpoints/episode_0030.json`, `episode_0040.json`, `episode_0050.json`: later checkpoints.

### `checkerboard_ckpt20_eval24`

Evaluation of the real-map ADP controller loaded from `checkerboard_train_50/checkpoints/episode_0020.json`.

Files:

- `eval_metrics.csv`: episode-level evaluation records.
- `eval_summary.csv`: aggregate metrics across 24 episodes.
- `eval_paired_summary.csv`: paired comparison fields when a baseline pairing is available.
- `eval_comparison.svg`: compact summary chart for that single run.
- `eval_comparison_episodes.svg`: per-episode visualization for that single run.

### `random_zero_eval24`

Evaluation of the random-zero ADP variant. This uses the ADP evaluation path but with zero/random baseline weights.

Same file meanings as `checkerboard_ckpt20_eval24`.

### `grid4x4_transfer_eval24`

Evaluation of weights trained on the original 4x4 grid and transferred to the real map.

This uses:

- `WEIGHT_TRANSFER_MODE: feature_dim_pad_truncate`
- 4x4 checkpoint: `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json`

The transfer loader pads or truncates source feature weights so every real-map traffic-light agent receives usable weights.

Same file meanings as `checkerboard_ckpt20_eval24`.

### `greedy_eval24`

Evaluation of the greedy baseline controller.

Same file meanings as `checkerboard_ckpt20_eval24`.

### `max_pressure_eval24`

Evaluation of the max-pressure baseline controller.

Same file meanings as `checkerboard_ckpt20_eval24`.

### `fixed_time_eval24`

Evaluation of the fixed-time round-robin baseline controller.

Same file meanings as `checkerboard_ckpt20_eval24`.

## `selected_methods_vs_baselines` Inside Each Real-Map Run

Each real-map run root has a selected comparison folder:

```text
runs/real_world_final_reproduction_rate1000/selected_methods_vs_baselines/
runs/real_world2_final_reproduction_rate1000/selected_methods_vs_baselines/
```

Important files:

- `selected_methods_vs_baselines_horizontal_v2.svg`: final comparison figure using the same visual format as the original 4x4 chart.
- `combined_summary.csv`: aggregate metrics for all selected methods and baselines.
- `pairwise_vs_greedy.csv`: paired comparison against greedy, when episode keys overlap.

The final chart compares only these four metrics:

- `success_rate`: fraction of evaluation episodes that recovered before timeout.
- `mean_ttr_success_only`: mean time-to-recovery for successful episodes only.
- `mean_queue_excess_area`: average excess queue area accumulated after the incident.
- `mean_throughput_recovery`: average post-incident throughput recovery score.

The chart intentionally excludes `gridlock_rate` per the latest requested format.

## Seed Search Runs

Two short ADP-only seed sweeps were generated:

```text
runs/real_world_seed_search/
runs/real_world2_seed_search/
```

Purpose:

- Pick a good evaluation random seed candidate for each real map.
- Keep this separate from the main 24-episode evaluation.

Sweep settings:

- Seeds tested: 7, 17, 27
- Episodes per seed: 4
- Controller used for ranking: ADP

Files at each seed-search root:

- `seed_sweep_summary.csv`: all seed/controller sweep rows.
- `best_seed_ranking.csv`: ranked seed candidates.
- `best_seed.txt`: top-ranked seed and ranking rule.

Per-seed folders:

```text
seed_7/adp/
seed_17/adp/
seed_27/adp/
```

Each per-seed folder contains the normal evaluation artifacts:

- `eval_metrics.csv`
- `eval_summary.csv`
- `eval_paired_summary.csv`
- `eval_comparison.svg`
- `eval_comparison_episodes.svg`

Ranking priority:

1. Higher `success_rate`
2. Lower `gridlock_rate`
3. Lower `mean_ttr_success_only`
4. Lower `mean_queue_excess_area`
5. Higher `mean_throughput_recovery`

Selected seeds:

- `real_world`: seed 7
- `real_world2`: seed 17

## Debug Smoke Run

```text
runs/real_world_debug_smoke_train/
```

This is a short development smoke test used to confirm that the real-world SUMO map, route generation, incident selection, and ADP training loop could run. It is not part of the final reported experiment.

Files:

- `train_metrics.csv`: smoke-training episode metrics.
- `training_metrics.svg`: smoke-training chart.
- `adp_agent_weights.json`: smoke-run weights.
- `checkpoints/episode_0001.json`: smoke checkpoint.

## Main Results Snapshot

The committed summary files are the quickest way to inspect final results:

```text
runs/real_world_final_reproduction_rate1000/selected_methods_vs_baselines/combined_summary.csv
runs/real_world2_final_reproduction_rate1000/selected_methods_vs_baselines/combined_summary.csv
```

Realmap1 main evaluation summary:

- Best success rate: `max_pressure` at 0.125
- `greedy` success rate: 0.0833
- ADP checkpoint-20 success rate: 0.0417
- Grid 4x4 transfer success rate: 0.0
- All listed methods had gridlock rate 0.0 in this run.

Realmap2 main evaluation summary:

- Best success rate: `checkerboard_ckpt_20` at 0.75
- `random_zero` success rate: 0.4167
- `grid4x4_transfer` success rate: 0.4167
- `greedy` and `max_pressure` success rate: 0.0417
- `fixed_time` success rate: 0.0
- All listed methods had gridlock rate 0.0 in this run.

## File Naming Notes

- `*_train_50`: 50-episode training runs.
- `*_eval24`: 24-episode evaluation runs.
- `ckpt20`: evaluation loaded checkpoint `episode_0020.json`.
- `rate1000`: route generation demand setting used for the real-map experiments.
- `selected_methods_vs_baselines`: final comparison outputs for reporting.

## Reproducing Or Regenerating Charts

Regenerate the selected comparison chart for realmap1:

```powershell
$env:PYTHONPATH="$PWD\src;$env:SUMO_HOME\tools"
python scripts\build_real_world_comparison.py --run-root outputs\runs\real_world_final_reproduction_rate1000 --title "Realmap1 Selected methods vs baselines"
```

Regenerate the selected comparison chart for realmap2:

```powershell
$env:PYTHONPATH="$PWD\src;$env:SUMO_HOME\tools"
python scripts\build_real_world_comparison.py --run-root outputs\runs\real_world2_final_reproduction_rate1000 --title "Realmap2 Selected methods vs baselines"
```

Run the short seed sweep again:

```powershell
$env:PYTHONPATH="$PWD\src;$env:SUMO_HOME\tools"
python scripts\sweep_real_map_seeds.py --map real_world --seeds 7,17,27 --episodes 4 --controllers adp
python scripts\sweep_real_map_seeds.py --map real_world2 --seeds 7,17,27 --episodes 4 --controllers adp
```
