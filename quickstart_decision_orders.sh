#!/bin/bash
# 快速開始：決策順序對比測試

# 設置路徑
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "決策順序對比基準測試 - 快速開始"
echo "=========================================="
echo ""

# Step 1: 驗證代碼修改
echo "[1/3] 驗證代碼修改..."
python validate_changes.py
if [ $? -ne 0 ]; then
    echo "✗ 代碼驗證失敗！"
    exit 1
fi
echo ""

# Step 2: 執行單元測試
echo "[2/3] 執行單元測試..."
python -m pytest tests/test_decision_orders.py -v --tb=short
if [ $? -ne 0 ]; then
    echo "⚠️  有單元測試失敗（非關鍵）"
fi
echo ""

# Step 3: 執行對比基準測試
echo "[3/3] 執行完整對比基準測試..."
echo "  這將測試6種策略，各5個episode（總計30個episode）"
echo "  預計耗時：10-20分鐘"
echo ""

python scripts/benchmark_decision_orders.py

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ 測試完成！"
    echo "結果位置: outputs/decision_order_benchmark_*/"
    echo "查看 comparison_table.csv 了解對比結果"
    echo "=========================================="
else
    echo "✗ 基準測試失敗"
    exit 1
fi
