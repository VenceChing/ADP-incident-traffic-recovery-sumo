# Evaluation Results README

This document compares the evaluation outputs produced under `outputs/runs`. For the directory/file structure, see `outputs/README.md`. This file focuses on what the results mean.

## Compared Experiments

Main result folders:

```text
outputs/runs/real_world_final_reproduction_rate1000/
outputs/runs/real_world2_final_reproduction_rate1000/
```

Each map was evaluated with 24 incident-recovery episodes per method. The reported comparison chart and CSV are located at:

```text
<run_root>/selected_methods_vs_baselines/
```

Important files:

- `selected_methods_vs_baselines_horizontal_v2.svg`: final visual comparison chart.
- `combined_summary.csv`: numeric summary for all compared methods.
- `pairwise_vs_greedy.csv`: paired comparison against greedy when matching episode keys exist.

The comparison includes six methods:

| Method | Type | Meaning |
|---|---:|---|
| `checkerboard_ckpt_20` | ADP | Real-map ADP trained for 50 episodes, evaluated from checkpoint 20. |
| `random_zero` | ADP variant | ADP evaluation path with random/zero baseline weights. |
| `grid4x4_transfer` | Transfer | Original 4x4-grid checkpoint transferred to the real map. |
| `greedy` | Baseline | Greedy traffic-light controller. |
| `max_pressure` | Baseline | Max-pressure controller. |
| `fixed_time` | Baseline | Fixed-time round-robin controller. |

## Metrics

The final comparison chart uses four metrics:

| Metric | Better Direction | Meaning |
|---|---:|---|
| `success_rate` | Higher | Fraction of episodes that recovered before timeout. |
| `mean_ttr_success_only` | Lower | Mean time-to-recovery, computed only on successful episodes. Blank or `n/a` means there were no successful episodes. |
| `mean_queue_excess_area` | Lower | Average accumulated queue excess after the incident. Lower means less congestion pressure. |
| `mean_throughput_recovery` | Higher | Average post-incident throughput recovery score. |

`gridlock_rate` is still available in `combined_summary.csv`, but it is intentionally excluded from the final chart format. In these real-map runs, all compared methods had `gridlock_rate = 0.0`.

## Realmap1 Results

Source:

```text
outputs/runs/real_world_final_reproduction_rate1000/selected_methods_vs_baselines/combined_summary.csv
```

| Method | Success Rate | Mean TTR | Mean Queue Excess Area | Mean Throughput Recovery |
|---|---:|---:|---:|---:|
| `checkerboard_ckpt_20` | 0.0417 | 212.0 | 5791.4 | 2.4686 |
| `random_zero` | 0.0000 | n/a | 5759.6 | 2.5553 |
| `grid4x4_transfer` | 0.0000 | n/a | 5748.7 | 2.5405 |
| `greedy` | 0.0833 | 375.0 | 3502.9 | 2.9760 |
| `max_pressure` | 0.1250 | 328.3 | 3551.5 | 3.0049 |
| `fixed_time` | 0.0000 | n/a | 5914.5 | 2.8517 |

### Realmap1 Interpretation

`max_pressure` performed best overall on realmap1. It had the highest success rate, the highest throughput recovery, and a low queue excess area. `greedy` was very close in queue control and had the second-best success rate.

The trained ADP checkpoint did recover one episode, but its overall success rate was lower than both `greedy` and `max_pressure`. The 4x4-grid transfer did not produce successful recoveries on realmap1. Its queue and throughput metrics were close to `random_zero`, which suggests that transferring the 4x4 policy directly to realmap1 did not generalize well.

For realmap1, the practical ranking from these outputs is:

1. `max_pressure`
2. `greedy`
3. `checkerboard_ckpt_20`
4. `fixed_time`
5. `random_zero` / `grid4x4_transfer`

The exact ranking can shift depending on which metric is prioritized. If queue excess is the main metric, `greedy` and `max_pressure` are nearly tied.

## Realmap2 Results

Source:

```text
outputs/runs/real_world2_final_reproduction_rate1000/selected_methods_vs_baselines/combined_summary.csv
```

| Method | Success Rate | Mean TTR | Mean Queue Excess Area | Mean Throughput Recovery |
|---|---:|---:|---:|---:|
| `checkerboard_ckpt_20` | 0.7500 | 243.7 | 4631.7 | 2.0560 |
| `random_zero` | 0.4167 | 274.6 | 5189.1 | 2.8281 |
| `grid4x4_transfer` | 0.4167 | 219.7 | 5936.6 | 2.4753 |
| `greedy` | 0.0417 | 211.0 | 7930.5 | 2.1472 |
| `max_pressure` | 0.0417 | 211.0 | 8226.3 | 2.1358 |
| `fixed_time` | 0.0000 | n/a | 7812.1 | 3.4309 |

### Realmap2 Interpretation

`checkerboard_ckpt_20` clearly performed best on realmap2. It had the highest success rate by a large margin and the lowest queue excess area. Its throughput recovery was not the highest, but it recovered far more incidents than the baselines.

`random_zero` and `grid4x4_transfer` both reached a 0.4167 success rate. The transfer model recovered faster on successful episodes, but it produced higher queue excess than `random_zero`. This means the 4x4 policy carried some useful recovery behavior to realmap2, but it did not control congestion as cleanly as the realmap2-trained ADP checkpoint.

`fixed_time` had the highest throughput recovery score, but no successful recoveries. This is a good example of why throughput recovery should not be read alone; high throughput does not necessarily mean incident recovery succeeded.

For realmap2, the practical ranking from these outputs is:

1. `checkerboard_ckpt_20`
2. `random_zero` / `grid4x4_transfer`
3. `greedy`
4. `max_pressure`
5. `fixed_time`

## Cross-Map Comparison

The ADP checkpoint generalized very differently across the two real maps:

| Map | ADP Success Rate | Best Baseline Success Rate | Best Method |
|---|---:|---:|---|
| realmap1 | 0.0417 | 0.1250 | `max_pressure` |
| realmap2 | 0.7500 | 0.0417 | `checkerboard_ckpt_20` |

Main takeaway:

- On realmap1, the trained ADP policy underperformed the strongest baselines.
- On realmap2, the trained ADP policy strongly outperformed all baselines.
- The 4x4-grid transfer was not useful on realmap1, but it showed partial transferability on realmap2.

This suggests that map topology and incident distribution matter a lot. A controller that is effective on one real map is not guaranteed to be effective on another real map without retraining or retuning.

## Seed Search Results

Seed-search folders:

```text
outputs/runs/real_world_seed_search/
outputs/runs/real_world2_seed_search/
```

The seed search was ADP-only and short:

- Seeds tested: 7, 17, 27
- Episodes per seed: 4
- Ranking priority: success rate, gridlock rate, TTR, queue excess, throughput recovery

### Realmap1 Seed Ranking

| Rank | Seed | Success Rate | Mean TTR | Mean Queue Excess Area | Mean Throughput Recovery |
|---:|---:|---:|---:|---:|---:|
| 1 | 7 | 0.25 | 212.0 | 4231.9 | 2.5871 |
| 2 | 27 | 0.25 | 238.0 | 4073.7 | 2.7489 |
| 3 | 17 | 0.00 | n/a | 5840.0 | 2.1746 |

Selected seed: `7`

Seed 7 and seed 27 had the same success rate, but seed 7 ranked first because it had lower TTR among successful episodes.

### Realmap2 Seed Ranking

| Rank | Seed | Success Rate | Mean TTR | Mean Queue Excess Area | Mean Throughput Recovery |
|---:|---:|---:|---:|---:|---:|
| 1 | 17 | 1.00 | 268.8 | 2895.8 | 2.1739 |
| 2 | 7 | 0.75 | 261.7 | 4836.2 | 1.9717 |
| 3 | 27 | 0.50 | 235.0 | 6480.1 | 1.9244 |

Selected seed: `17`

Seed 17 was selected because it achieved 100% success in the short seed sweep.

## How To Read The SVG Comparison Charts

Open:

```text
outputs/runs/real_world_final_reproduction_rate1000/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
outputs/runs/real_world2_final_reproduction_rate1000/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```

Each chart has four panels:

1. Success rate
2. Mean TTR, success only
3. Mean queue excess area
4. Mean throughput recovery

For success rate and throughput recovery, longer bars are better. For TTR and queue excess area, shorter values are better, even though the bar itself grows with the numeric value. The `best` label marks the best method according to each panel's direction.

When a method has `n/a` for TTR, it means that method had zero successful episodes, so there was no successful recovery time to average.

## Recommended Reporting Summary

Use these two figures in the report:

```text
outputs/runs/real_world_final_reproduction_rate1000/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
outputs/runs/real_world2_final_reproduction_rate1000/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```

Recommended short conclusion:

```text
Under the realmap1 scenario, max-pressure and greedy baselines outperformed the trained ADP checkpoint, indicating that the learned policy did not transfer cleanly to that topology and incident distribution. Under realmap2, the trained ADP checkpoint achieved the highest success rate and lowest queue excess area, clearly outperforming the three baselines. The 4x4-grid transferred weights showed limited generalization: no successful recovery on realmap1, but partial recovery performance on realmap2.
```

## GUI Demo Recording Commands

Use these commands to open two visible SUMO GUI demo windows for one map at a time. Each command compares ADP against the fixed-time baseline, which is useful for screen recording.

The GUI demos intentionally use denser demo-only traffic (`RATE: 2500`, `TIME: 1180`, incident at step `150`) so the vehicles and controller differences are visible on screen. This does not change the final reported evaluation outputs.

If your VSCode terminal is currently at:

```powershell
C:\ai\final_project\final_version
```

run:

```powershell
powershell -ExecutionPolicy Bypass -File .\ADP-incident-traffic-recovery-sumo\scripts\launch_real_map_demo_compare.ps1 -Map real_world
```

```powershell
powershell -ExecutionPolicy Bypass -File .\ADP-incident-traffic-recovery-sumo\scripts\launch_real_map_demo_compare.ps1 -Map real_world2
```

If your VSCode terminal is already at the project root:

```powershell
C:\ai\final_project\final_version\ADP-incident-traffic-recovery-sumo
```

run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\launch_real_map_demo_compare.ps1 -Map real_world
powershell -ExecutionPolicy Bypass -File scripts\launch_real_map_demo_compare.ps1 -Map real_world2
```

Each command opens two windows:

- ADP demo
- `fixed_time_rr` demo

`SUMO_HOME` must be set before launching the demos.
