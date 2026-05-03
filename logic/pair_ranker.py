import logging

class PairRanker:
    """
    Ranks and filters symbols based on their individual performance history.
    Ensures capital is allocated to the most reliable assets.
    """

    def __init__(self, min_trades_required=5):
        self.min_trades = min_trades_required
        self.symbol_performance = {} # {symbol: expectancy}
        self.logger = logging.getLogger(__name__)

    def update_rankings(self, performance_data):
        """Processes raw performance data to rank symbols."""
        if not performance_data:
            return

        self.symbol_trade_counts = {}
        stats = {}
        for row in performance_data:
            symbol = row.get('Symbol')
            if not symbol: continue

            if symbol not in stats:
                stats[symbol] = {"wins": 0, "losses": 0, "win_amounts": [], "loss_amounts": []}

            s = stats[symbol]
            pnl = float(row.get('PnL', 0))
            outcome = row.get('Outcome')

            if outcome == "WIN":
                s["wins"] += 1
                s["win_amounts"].append(pnl)
            elif outcome == "LOSS":
                s["losses"] += 1
                s["loss_amounts"].append(abs(pnl))

        new_rankings = {}
        for symbol, s in stats.items():
            total_trades = s["wins"] + s["losses"]
            if total_trades >= self.min_trades:
                win_rate = s["wins"] / total_trades
                avg_win = sum(s["win_amounts"]) / len(s["win_amounts"]) if s["win_amounts"] else 0
                avg_loss = sum(s["loss_amounts"]) / len(s["loss_amounts"]) if s["loss_amounts"] else 0
                expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
                new_rankings[symbol] = expectancy
                self.symbol_trade_counts[symbol] = total_trades
                self.logger.info(f"Symbol Rank: {symbol} | Exp: {expectancy:.4f} ({total_trades} trades)")

        self.symbol_performance = new_rankings

    def get_symbol_weight(self, symbol):
        """Returns a multiplier based on symbol performance."""
        if symbol not in self.symbol_performance:
            return 1.0 # Default weight for new/unranked symbols

        exp = self.symbol_performance[symbol]
        if exp <= 0:
            return 0.5 # De-prioritize poor performers
        if exp > 2.0:
            return 1.2 # Boost top performers
        return 1.0

    def should_skip_symbol(self, symbol):
        """Hard filter for toxic symbols (Tier 7: Skip any negative expectancy)."""
        if symbol in self.symbol_performance:
            # If we have 10+ trades and expectancy is negative, it's a toxic pair for our strategy
            # Using 10 trades for a more stable statistical sample.
            trades = getattr(self, 'symbol_trade_counts', {}).get(symbol, 0)
            if trades >= 10 and self.symbol_performance[symbol] <= 0:
                return True
        return False
