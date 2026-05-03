
import logging
from logic.optimizer import StrategyOptimizer

def test_optimizer():
    logging.basicConfig(level=logging.INFO)
    optimizer = StrategyOptimizer(min_trades_required=5)

    # Mock performance summary
    summary = {
        "GLOBAL": {"trades": 20},
        3: {"trades": 6, "expectancy": -0.1, "profit_factor": 0.8, "win_rate": 0.3},
        4: {"trades": 4, "expectancy": 0.5, "profit_factor": 2.0, "win_rate": 0.5},
        5: {"trades": 2, "expectancy": -3.0, "profit_factor": 0.1, "win_rate": 0.0}
    }

    disabled = optimizer.analyze_and_optimize(summary)
    print(f"Disabled scores: {disabled}")

    assert 3 in disabled, "Score 3 should be disabled (trades >= 5 and expectancy <= 0)"
    assert 4 not in disabled, "Score 4 should be enabled (trades < 5)"
    assert 5 in disabled, "Score 5 should be disabled (early safety trigger for extreme negative edge)"

    print("Optimizer test passed!")

if __name__ == "__main__":
    test_optimizer()
