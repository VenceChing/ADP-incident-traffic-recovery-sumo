```markdown
# ITS Signal Control - Evaluation & Advanced Visualization Modules

This branch introduces an automated framework for tracking fine-grained simulation data and generating high-quality, academic-grade visualizations to analyze traffic signal controller performance under incident conditions.

---

## 🛠 Summary of Changes

### 1. `experiment.py` (Data Logging Enhancement)
* **Added `StepLogWriter` Integrations:** Integrated structural step-by-step logging functionality into the main evaluation loops. 
* **Granular Metrics Collection:** Captures intersection-level and network-wide states (such as `total_queue`, `mean_speed`, and agent `action` choices) at every simulation step.
* **Automated Storage:** Telemetry is structurally serialized and dumped directly into the designated `step_logs/` subdirectory for post-simulation analytics.

### 2. `plot_advanced.py` (Unified Academic Visualization Dashboard)
A newly developed, fully integrated console that processes telemetry logs to output publication-ready figures. It streamlines data from disparate evaluation sessions and visualizes them across macro (statistical) and micro (episode-specific) scales.

---

## 📊 Core Visualization Features

The plotting pipeline generates 6 distinct types of analytical charts under the `academic_plots/` directory.

### Macro-Scale Statistical Analysis
* **Incident Recovery Time (TTR) Boxplot (`1a_boxplot_ttr.png`):** Illustrates the overall distribution and density of times taken by each controller to clear congestion and return the network to free-flow states across all evaluation episodes.
* **Queue Excess Area Boxplot (`1b_boxplot_queue_excess.png`):** Measures the total cumulative queue stress (congestion cost), offering an intuitive look into the severity of delays under different policies.
* **Recovery Time Cumulative Distribution Function (`1c_cdf_ttr.png`):** A CDF curve mapping the probability distribution of recovery success over time, highlighting empirical stochastic dominance between controllers.

### Micro-Scale & Episode-Specific Telemetry
The core time-series modules support **dual-version renderings**—dynamically generating plots both **including and excluding** the baseline Fixed-Time controller (`fixed_time_rr`) to enable unbiased comparisons between advanced adaptive heuristics.

1.  **Network Queue Evolution (`2_queue_evolution_*.png`):**
    * Tracks the total network-wide vehicle queue length over simulation steps.
    * *Versions:* `with_fixed_time` (global benchmark) and `without_fixed_time` (fine-grained comparison among adaptive policies).
2.  **Average Speed Recovery Curve (`3_speed_recovery_*.png`):**
    * Monitors the network's mean vehicular speed profile, showcasing how rapidly a system bounces back from structural gridlocks.
    * *Versions:* `with_fixed_time` and `without_fixed_time`.
3.  **Spatial Queue Variance (`4_queue_variance_*.png`):**
    * Computes the instantaneous spatial variance of queues across all intersections. Higher variance indicates uneven bottlenecks and localized congestion.
    * *Versions:* `with_fixed_time` and `without_fixed_time`.

### Controller Behavior & Spatial-Temporal Dynamics
* **Phase Switching Frequency (`5_switch_frequency_*.png`):** A summary bar chart plotting the cumulative signal phase changes made by each controller, revealing the control smoothness and mechanical wear-and-tear considerations of the policies.
* **2x2 Spatio-Temporal Queue Heatmap (`6_spatiotemporal_heatmap_*.png`):** Maps time (30-second bins) on the X-axis against individual intersection IDs on the Y-axis. Uses a standardized color gradient (`YlOrRd`) to visually trace the propagation, peak intensity, and dissipation of queues across the entire network layout.

---

## 🚀 Usage & Execution

Ensure your environment path alignment matches the directory mappings defined inside `its_signal_control.config`.

### 1. Run the Evaluation Pipeline
Execute your standard simulation runs. This populates the step-by-step logs via the newly embedded hooks inside `experiment.py`:
```bash
python -m its_signal_control.experiment --mode eval