import os
from pathlib import Path
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# 從專案設定檔匯入參數
from its_signal_control.config import EVAL_EPISODES_PER_CONTROLLER, RESULTS_DIR

# ==========================================
# 1. 全域設定與路徑配置
# ==========================================
# 設定 Seaborn 樣式，使其具備高畫質學術論文質感
sns.set_theme(style="whitegrid", palette="muted")

# 實驗資料輸入路徑
# LOG_DIR = Path(RESULTS_DIR) / "step_logs"
# METRICS_CSV = Path(RESULTS_DIR) / "eval_metrics.csv"
LOG_DIR = Path("outputs/runs/historical_best/step_logs")
METRICS_CSV = Path("outputs/runs/historical_best/eval_metrics.csv")

# 圖片輸出路徑（統一整合到同一個視覺化資料夾）
# OUTPUT_DIR = Path(RESULTS_DIR) / "academic_plots"
OUTPUT_DIR = Path("outputs/runs/historical_best/advanced_plots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 實驗對照組方法與顏色定義
METHODS = ["fixed_time_rr", "greedy", "max_pressure", "adp_eval"]
METHOD_COLORS = {"fixed_time_rr": "#ff7f0e", "greedy": "#1f77b4", "max_pressure": "#d62728", "adp_eval": "#2ca02c"}


# ==========================================
# 2. 統計評估圖表 (針對所有 Episodes 的大數據分析)
# ==========================================
def plot_overall_statistical_metrics():
    """1. 論文主結果：匯總所有 Episode 的 Boxplots 與 CDF"""
    if not METRICS_CSV.exists():
        print(f"❌ 找不到 {METRICS_CSV}，請確認實驗是否已產出綜合指標！")
        return

    df = pd.read_csv(METRICS_CSV)

    # 1a. Time to Recovery (TTR) Boxplot
    plt.figure(figsize=(10, 6))
    sns.boxplot(
        data=df,
        x="controller",
        y="duration_after_incident",
        order=METHODS,
        hue="controller",
        palette="Set2",
        legend=False,
    )
    sns.swarmplot(
        data=df,
        x="controller",
        y="duration_after_incident",
        order=METHODS,
        color=".25",
        size=4,
    )
    plt.title(
        "Distribution of Incident Recovery Time (duration_after_incident)",
        fontsize=16,
    )
    plt.ylabel("Duration After Incident (Seconds)")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "1a_boxplot_ttr.png", dpi=300)
    plt.close()

    # 1b. Queue Excess Area Boxplot
    plt.figure(figsize=(10, 6))
    sns.boxplot(
        data=df,
        x="controller",
        y="queue_excess_area",
        order=METHODS,
        hue="controller",
        palette="Set2",
        legend=False,
    )
    sns.swarmplot(
        data=df,
        x="controller",
        y="queue_excess_area",
        order=METHODS,
        color=".25",
        size=4,
    )
    plt.title(
        "Distribution of Queue Excess Area (Total Congestion Cost)", fontsize=16
    )
    plt.ylabel("Queue Excess Area")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "1b_boxplot_queue_excess.png", dpi=300)
    plt.close()

    # 1c. CDF of Recovery Time
    plt.figure(figsize=(10, 6))
    sns.ecdfplot(
        data=df,
        x="duration_after_incident",
        hue="controller",
        hue_order=METHODS,
        linewidth=2,
    )
    plt.title(
        "Cumulative Distribution Function (CDF) of Recovery Time", fontsize=16
    )
    plt.xlabel("Duration After Incident (Seconds)")
    plt.ylabel("Proportion of Episodes Recovered")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "1c_cdf_ttr.png", dpi=300)
    plt.close()
    print("✅ 成功生成總體統計圖表 (Boxplot, CDF)")


# ==========================================
# 3. 時序演進核心圖表 (支援包含與排除 Fixed Time 雙版本)
# ==========================================
def plot_queue_evolution(episode=0, include_fixed_time=True):
    """2. 車隊排隊長度演進曲線 (Network Queue Evolution)"""
    plt.figure(figsize=(10, 6))

    # 根據參數決定是否過濾 fixed_time_rr
    active_methods = METHODS if include_fixed_time else [m for m in METHODS if m != "fixed_time_rr"]
    suffix = "with_fixed_time" if include_fixed_time else "without_fixed_time"

    for method in active_methods:
        file_path = LOG_DIR / f"eval_{method}_ep{episode}.csv"
        if not file_path.exists():
            continue

        df = pd.read_csv(file_path)
        queue_ts = df.groupby("time")["total_queue"].sum().reset_index()

        plt.plot(
            queue_ts["time"],
            queue_ts["total_queue"],
            linewidth=2,
            label=method,
            color=METHOD_COLORS.get(method),
        )

    plt.title(f"Network Queue Evolution - Episode {episode} ({suffix.replace('_', ' ')})", fontsize=14)
    plt.xlabel("Simulation Time (s)")
    plt.ylabel("Total Queue (veh)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    plt.savefig(
        OUTPUT_DIR / f"2_queue_evolution_{suffix}_ep{episode}.png", dpi=300
    )
    plt.close()


def plot_speed_recovery(episode=0, include_fixed_time=True):
    """3. 平均車速恢復曲線 (Speed Recovery Curve)"""
    plt.figure(figsize=(10, 6))

    active_methods = METHODS if include_fixed_time else [m for m in METHODS if m != "fixed_time_rr"]
    suffix = "with_fixed_time" if include_fixed_time else "without_fixed_time"

    for method in active_methods:
        file_path = LOG_DIR / f"eval_{method}_ep{episode}.csv"
        if not file_path.exists():
            continue

        df = pd.read_csv(file_path)
        speed_ts = df.groupby("time")["mean_speed"].mean().reset_index()

        plt.plot(
            speed_ts["time"],
            speed_ts["mean_speed"],
            linewidth=2,
            label=method,
            color=METHOD_COLORS.get(method),
        )

    plt.title(f"Speed Recovery Curve - Episode {episode} ({suffix.replace('_', ' ')})", fontsize=14)
    plt.xlabel("Simulation Time (s)")
    plt.ylabel("Average Speed (m/s)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    plt.savefig(
        OUTPUT_DIR / f"3_speed_recovery_{suffix}_ep{episode}.png", dpi=300
    )
    plt.close()


def plot_queue_variance(episode=0, include_fixed_time=True):
    """4. 空間排隊變異數曲線 (Spatial Queue Variance - 衡量路網不均勻度)"""
    plt.figure(figsize=(10, 6))

    active_methods = METHODS if include_fixed_time else [m for m in METHODS if m != "fixed_time_rr"]
    suffix = "with_fixed_time" if include_fixed_time else "without_fixed_time"

    for method in active_methods:
        file_path = LOG_DIR / f"eval_{method}_ep{episode}.csv"
        if not file_path.exists():
            continue

        df = pd.read_csv(file_path)
        variance_ts = df.groupby("time")["total_queue"].var().reset_index()

        plt.plot(
            variance_ts["time"],
            variance_ts["total_queue"],
            linewidth=2,
            label=method,
            color=METHOD_COLORS.get(method),
        )

    plt.title(f"Spatial Queue Variance - Episode {episode} ({suffix.replace('_', ' ')})", fontsize=14)
    plt.xlabel("Simulation Time (s)")
    plt.ylabel("Variance of Queue")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    plt.savefig(
        OUTPUT_DIR / f"4_queue_variance_{suffix}_ep{episode}.png", dpi=300
    )
    plt.close()


# ==========================================
# 4. 控制器行為與時空熱圖分析
# ==========================================
def plot_switching_frequency(episode=0):
    """5. 訊號燈號切換頻率條形圖 (Phase Switching Frequency)"""
    switch_data = []

    for method in METHODS:
        file_path = LOG_DIR / f"eval_{method}_ep{episode}.csv"
        if not file_path.exists():
            continue

        df = pd.read_csv(file_path)
        switches = 0

        for agent_id, group in df.groupby("agent_id"):
            group = group.sort_values("time")
            switches += group["action"].ne(group["action"].shift()).sum()

        switch_data.append({"method": method, "switches": switches})

    if not switch_data:
        return

    switch_df = pd.DataFrame(switch_data)

    plt.figure(figsize=(8, 5))
    sns.barplot(data=switch_df, x="method", y="switches", hue="method", palette=METHOD_COLORS, legend=False)
    plt.title(f"Phase Switching Frequency (Episode {episode})", fontsize=14)
    plt.ylabel("Number of Switches")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"5_switch_frequency_ep{episode}.png", dpi=300)
    plt.close()


def plot_spatiotemporal_heatmap(episode=0):
    """6. 2x2 路口排隊時空熱圖 (Spatio-Temporal Queue Heatmap)"""
    dfs = {}
    max_agent_q = 0
    max_time_bin = 0

    # 預讀取並計算全局最大值以統一坐標軸
    for method in METHODS:
        file_path = LOG_DIR / f"eval_{method}_ep{episode}.csv"
        if not file_path.exists():
            continue
        df = pd.read_csv(file_path)
        df["time_bin"] = (df["time"] // 30) * 30
        dfs[method] = df

        max_agent_q = max(
            max_agent_q,
            df.groupby(["agent_id", "time_bin"])["total_queue"].mean().max(),
        )
        max_time_bin = max(max_time_bin, df["time_bin"].max())

    if not dfs:
        print(f"⚠️ 找不到 Episode {episode} 的資料，跳過熱圖繪製。")
        return

    all_time_bins = np.arange(0, max_time_bin + 30, 30)

    fig, axes = plt.subplots(2, 2, figsize=(14, 12), constrained_layout=True)
    fig.suptitle(
        f"Spatio-Temporal Queue Heatmap - Episode {episode}",
        fontsize=20,
        fontweight="bold",
    )
    axes = axes.flatten()

    for i, method in enumerate(METHODS):
        ax = axes[i]
        if method not in dfs:
            ax.set_title(f"{method}\n(No Data)", fontsize=14)
            continue

        df = dfs[method]
        pivot_df = df.pivot_table(
            index="agent_id", columns="time_bin", values="total_queue", aggfunc="mean"
        )
        pivot_df = pivot_df.reindex(columns=all_time_bins)

        sns.heatmap(
            pivot_df,
            cmap="YlOrRd",
            ax=ax,
            cbar=False,
            vmin=0,
            vmax=max_agent_q,
            xticklabels=4,
        )
        ax.set_title(f"{method}", fontsize=16, fontweight="bold")
        ax.set_ylabel("Intersection (Agent ID)" if i % 2 == 0 else "")
        ax.set_xlabel("Time (30s Bins)")
        ax.tick_params(axis="x", rotation=45)

    # 建立下方統一的 Colorbar
    sm = cm.ScalarMappable(
        cmap="YlOrRd", norm=plt.Normalize(vmin=0, vmax=max_agent_q)
    )
    fig.colorbar(
        sm,
        ax=axes.tolist(),
        orientation="horizontal",
        label="Intersection Mean Queue Length",
        shrink=0.6,
        pad=0.08,
    )

    out_file = OUTPUT_DIR / f"6_spatiotemporal_heatmap_ep{episode}.png"
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ==========================================
# 5. 主程式自動化執行流程
# ==========================================
if __name__ == "__main__":
    print("🚀 開始執行整合型學術圖表繪製主控台...")

    # 執行全域統計大圖 (Boxplot & CDF)
    plot_overall_statistical_metrics()

    # 針對指定的測試 Episode 進行深度演進與行為分析
    target_episode = EVAL_EPISODES_PER_CONTROLLER - 1
    print(f"📊 正在生成重度分析圖表，指定 Episode: {target_episode}")

    # ===== 核心三個函式分別產出有、無 Fixed Time 的版本 =====
    # 1. 排隊演進圖
    plot_queue_evolution(episode=target_episode, include_fixed_time=True)
    plot_queue_evolution(episode=target_episode, include_fixed_time=False)

    # 2. 速度恢復圖
    plot_speed_recovery(episode=target_episode, include_fixed_time=True)
    plot_speed_recovery(episode=target_episode, include_fixed_time=False)

    # 3. 排隊空間變異數圖
    plot_queue_variance(episode=target_episode, include_fixed_time=True)
    plot_queue_variance(episode=target_episode, include_fixed_time=False)
    # ======================================================

    # 執行切換頻率圖
    plot_switching_frequency(episode=target_episode)

    # 執行 2x2 時空熱圖
    plot_spatiotemporal_heatmap(episode=target_episode)

    print(f"\n✅ 所有學術級圖表已成功整併並生成於: {OUTPUT_DIR}/")