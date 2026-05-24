import csv

from its_signal_control import metrics


def test_summarize_eval_metrics_writes_controller_summary(tmp_path, monkeypatch) -> None:
    eval_path = tmp_path / "eval_metrics.csv"
    summary_path = tmp_path / "eval_summary.csv"
    paired_path = tmp_path / "paired.csv"
    rows = [
        {
            "controller": "adp_eval",
            "status": "SUCCESS",
            "ttr": "100",
            "duration_after_incident": "100",
            "queue_excess_area": "10",
            "throughput_recovery_ratio": "1.0",
        },
        {
            "controller": "adp_eval",
            "status": "GRIDLOCK",
            "ttr": "",
            "duration_after_incident": "200",
            "queue_excess_area": "30",
            "throughput_recovery_ratio": "0.5",
        },
    ]
    with eval_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    monkeypatch.setattr(metrics, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(metrics, "EVAL_METRICS_CSV_PATH", str(eval_path))
    monkeypatch.setattr(metrics, "EVAL_SUMMARY_CSV_PATH", str(summary_path))
    monkeypatch.setattr(metrics, "EVAL_PAIRED_SUMMARY_CSV_PATH", str(paired_path))

    summary = metrics.summarize_eval_metrics()

    assert summary[0]["controller"] == "adp_eval"
    assert summary[0]["success_rate"] == 0.5
    assert summary_path.exists()
