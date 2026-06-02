#!/usr/bin/env python3
"""
完整工作流：訓練 → 評估 → 報告

Usage:
  python workflow_train_and_evaluate.py
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

def run_command(cmd, description):
    """運行命令並報告進度"""
    print("\n" + "="*70)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {description}")
    print("="*70)
    
    try:
        result = subprocess.run(cmd, shell=True, check=True)
        print(f"✓ {description} 完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} 失敗 (exit code: {e.returncode})")
        return False
    except Exception as e:
        print(f"✗ {description} 異常: {e}")
        return False

def main():
    repo_root = Path(__file__).resolve().parent
    
    print("\n" + "="*70)
    print("決策順序完整訓練與評估工作流")
    print("="*70)
    print(f"\n時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目錄: {repo_root}")
    
    # Step 1: 驗證系統
    print("\n" + "="*70)
    print("[Step 1/3] 驗證系統...")
    print("="*70)
    
    if not run_command(
        f"python {repo_root / 'validate_training_evaluation.py'}",
        "系統驗證"
    ):
        print("\n✗ 系統驗證失敗。請檢查錯誤並重試。")
        return 1
    
    # Step 2: 訓練
    print("\n" + "="*70)
    print("[Step 2/3] 訓練所有策略（這將花費 2-3 小時）...")
    print("="*70)
    
    if not run_command(
        f"python {repo_root / 'scripts' / 'train_decision_orders.py'}",
        "訓練決策順序策略"
    ):
        print("\n✗ 訓練失敗。")
        return 1
    
    # 提取訓練輸出目錄
    training_dirs = sorted(
        (repo_root / "models").glob("decision_order_training_*"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    if not training_dirs:
        print("\n✗ 找不到訓練輸出目錄")
        return 1
    
    training_dir = training_dirs[0]
    print(f"\n訓練輸出目錄: {training_dir}")
    
    # Step 3: 評估
    print("\n" + "="*70)
    print("[Step 3/3] 評估並對比結果...")
    print("="*70)
    
    if not run_command(
        f"python {repo_root / 'scripts' / 'benchmark_decision_orders.py'} {training_dir}",
        "評估所有策略"
    ):
        print("\n✗ 評估失敗。")
        return 1
    
    # 完成
    print("\n" + "="*70)
    print("✓ 工作流完成！")
    print("="*70)
    
    print("\n結果位置：")
    print(f"  - 訓練: {training_dir}")
    print(f"  - 評估: outputs/decision_order_benchmark_*")
    
    print("\n查看結果：")
    print(f"  - 對比表: cat outputs/decision_order_benchmark_*/comparison_table.csv")
    print(f"  - 訓練摘要: cat {training_dir}/training_complete_summary.json | python -m json.tool")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
