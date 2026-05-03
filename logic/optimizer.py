import logging

class StrategyOptimizer:
    """
    Automated Strategy Optimization Layer.
    Analyzes performance data to enable/disable score levels based on statistical edge.
    """

    def __init__(self, min_trades_required=10):
        self.logger = logging.getLogger(__name__)
        self.min_trades = min_trades_required
        self.disabled_scores = set()
        self.performance_cache = {}

    def analyze_and_optimize(self, performance_summary):
        """
        Processes performance summary and updates allowed scores.
        Only disables Score 3/4 if they have enough data (min_trades).
        Score 5/6 are protected unless they show deep negative edge.
        """
        if not performance_summary:
            self.logger.info("No performance data available for optimization.")
            return

        new_disabled = set()
        self.performance_cache = performance_summary

        for key, metrics in performance_summary.items():
            if key == "GLOBAL": continue

            score = key
            trades = metrics['trades']
            expectancy = metrics['expectancy']
            profit_factor = metrics['profit_factor']

            self.logger.info(f"Analyzing Score {score}: {trades} trades, Expectancy: {expectancy:.4f}, PF: {profit_factor:.2f}")

            # Optimization Rules:
            # 1. Statistical Edge Check
            if trades >= self.min_trades:
                # Stricter for Score 3
                threshold_pf = 1.1 if score <= 4 else 0.9

                if expectancy <= 0 or profit_factor < threshold_pf:
                    self.logger.warning(f"🚫 Score {score} failed statistical edge check (Exp: {expectancy:.4f}, PF: {profit_factor:.2f}). Disabling.")
                    new_disabled.add(score)
                else:
                    self.logger.info(f"✅ Score {score} remains ENABLED (Expectancy: {expectancy:.4f}, PF: {profit_factor:.2f}).")
            else:
                # Protection for high-conviction scores with small samples
                if score >= 5 and expectancy < -2.0:
                    self.logger.error(f"🚨 Score {score} showing EXTREME negative edge early. Safety disabling.")
                    new_disabled.add(score)
                else:
                    self.logger.info(f"⏳ Score {score} still in validation phase ({trades}/{self.min_trades} trades).")

        self.disabled_scores = new_disabled
        return self.disabled_scores

    def is_score_allowed(self, score):
        """Checks if a score level is currently allowed by the optimizer (Always allow 4+ during calibration)."""
        if score >= 4: return True
        return score not in self.disabled_scores

    def get_optimization_report(self):
        """Returns a string report of the current optimization state."""
        if not self.performance_cache:
            return "No optimization data yet."

        report = ["📊 <b>Strategy Optimization Report</b>"]
        for score in sorted(self.performance_cache.keys()):
            m = self.performance_cache[score]
            status = "❌ DISABLED" if score in self.disabled_scores else "✅ ACTIVE"
            report.append(
                f"Score {score}: {status}\n"
                f"Trades: {m['trades']} | WR: {m['win_rate']:.1%} | Exp: {m['expectancy']:.2f}"
            )
        return "\n".join(report)
