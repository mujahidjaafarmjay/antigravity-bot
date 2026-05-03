import config
from datetime import datetime, timedelta

class RiskManager:
    """
    Professional Risk Management System.
    Protects capital and ensures high-quality trade execution.
    """

    def __init__(self):
        self.max_open_trades = config.MAX_OPEN_TRADES
        self.daily_loss_limit = config.DAILY_LOSS_LIMIT_PERCENT
        self.consecutive_losses = 0
        self.kill_switch_time = None

    def get_score_weight(self, score, performance_summary=None):
        """
        Dynamic weight based on signal score.
        If sufficient data exists, weights become data-driven.
        """
        # 1. Check if we have data-driven weights (Institutional tier)
        if performance_summary and score in performance_summary:
            stats = performance_summary[score]
            if stats['trades'] >= 20:
                exp = stats['expectancy']
                if exp <= 0: return 0.5
                if exp < 0.5: return 0.8
                if exp < 1.0: return 1.0
                return 1.2

        # 2. Fallback to Static Strategic Weights
        weights = {
            3: 0.5,
            4: 1.0,
            5: 1.2,
            6: 1.5
        }
        return weights.get(score, 1.0)

    def calculate_position(self, balance, entry_price, stop_loss, score=3, symbol_weight=1.0, performance_summary=None):
        """
        Calculates the quantity based on dynamic risk rules, score weight, and symbol rank.
        """
        if balance <= 0:
            return 0, "Invalid Balance"

        # 1. Base Risk per Trade
        risk_percent = 0.03 # Calibration baseline 3%
        if balance < 30:
            risk_percent = 0.015 # 1.5% for small balance

        # 2. Score-Based Risk Weighting
        score_mult = self.get_score_weight(score, performance_summary)

        # 3. Symbol-Based Weight (from PairRanker)
        final_risk_percent = risk_percent * score_mult * symbol_weight

        risk_amount = balance * final_risk_percent
        
        # 2. Risk per Unit
        risk_per_unit = entry_price - stop_loss
        if risk_per_unit <= 0:
            return 0, "Invalid Stop Loss (must be below entry)"

        # 3. Quantity based on Risk
        qty = risk_amount / risk_per_unit
        
        # 4. Max Position Size Constraint (Percentage and Hard USD Cap)
        max_notional_perc = balance * (config.MAX_POSITION_SIZE_PERCENT / 100)
        max_notional_usdt = config.MAX_POSITION_SIZE_USDT
        max_notional = min(max_notional_perc, max_notional_usdt)

        actual_notional = qty * entry_price
        
        if actual_notional > max_notional:
            qty = max_notional / entry_price
        # 5. Min Position Size Constraint (Bybit requires ~$5 minimum notional)
        if (qty * entry_price) < config.MIN_TRADE_USDT:
            return 0, "SMALL_TRADE_WATCH"
            
        return round(qty, 6), "OK"

    def validate_trade(self, decision, balance, current_open_trades, bid, ask):
        """
        Final check before execution.
        """
        # 1. Open Trade Limit
        if current_open_trades >= self.max_open_trades:
            return False, f"Max open trades ({self.max_open_trades}) reached"

        # 2. Minimum Balance
        if balance < 10: # Minimum to trade effectively on Spot
            return False, f"Balance too low (${balance:.2f})"

        # 3. Risk:Reward Ratio Filter (Min 1:2.2 gross)
        entry = decision['entry']
        sl = decision['stop_loss']
        tp = decision['take_profit']
        
        risk = entry - sl
        reward = tp - entry
        
        if risk <= 0:
            return False, "Invalid SL/Entry"
            
        rr = reward / risk
        # Hard Tier 3 Filter: Min RR must be 2.0 or better
        min_rr = max(2.0, config.REWARD_TO_RISK_RATIO)
        if rr < min_rr:
            return False, f"RR too low ({rr:.2f} < {min_rr})"

        # 4. Spread Protection
        if bid <= 0:
            return False, "Invalid Bid Price (0)"
            
        spread = (ask - bid) / bid
        if spread > config.SPREAD_LIMIT:
            return False, f"Spread too high ({spread:.2%})"

        return True, "Validated"

    def reset_daily_halt(self):
        """Resets the daily halt flag."""
        # This is used by the command handler to resume trading
        pass

    def update_loss_streak(self, outcome):
        """Tracks consecutive losses for the Smart Kill Switch."""
        if outcome == "LOSS":
            self.consecutive_losses += 1
            if self.consecutive_losses >= 3:
                self.kill_switch_time = datetime.now()
        else:
            self.consecutive_losses = 0
            self.kill_switch_time = None

    def is_kill_switch_active(self):
        """
        Kill switch triggers after 3 consecutive losses.
        Auto-recovers after KILL_SWITCH_COOLDOWN_HOURS.
        """
        if self.consecutive_losses < 3:
            return False

        if self.kill_switch_time:
            elapsed = datetime.now() - self.kill_switch_time
            if elapsed > timedelta(hours=config.KILL_SWITCH_COOLDOWN_HOURS):
                self.consecutive_losses = 0 # Auto-reset
                self.kill_switch_time = None
                return False

        return True

    def is_volatility_too_high(self, df):
        """
        Volatility Filter: Detects sudden price spikes or extreme wicks.
        Skips entry if current candle volatility is > 2.5x ATR.
        """
        if df is None or len(df) < 20:
            return False

        # 1. Calculate ATR (Simplified)
        high_low = df['high'] - df['low']
        atr = high_low.rolling(window=config.VOLATILITY_LOOKBACK).mean().iloc[-2]

        # 2. Current Candle Volatility
        current_vol = df['high'].iloc[-1] - df['low'].iloc[-1]

        if current_vol > (atr * config.VOLATILITY_LIMIT_MULT):
            return True
        return False

    def is_equity_under_pressure(self, performance_summary):
        """
        Equity Curve Protection:
        Uses the 'GLOBAL' container for absolute consistency.
        """
        if not performance_summary or "GLOBAL" not in performance_summary:
            return False

        g = performance_summary["GLOBAL"]
        if g['trades'] < config.EQUITY_PROTECT_TRADES:
            return False

        if g['gross_loss_pnl'] > 0:
            pf = g['gross_win_pnl'] / g['gross_loss_pnl']
            if pf < config.EQUITY_PROTECT_THRESHOLD:
                return True
        return False

    def is_market_toxic(self, performance_summary):
        """
        Bad Market Filter:
        Detects if recent global Profit Factor is below critical threshold.
        """
        if not performance_summary or "GLOBAL" not in performance_summary:
            return False

        g = performance_summary["GLOBAL"]
        if g['trades'] < 10:
            return False

        if g['gross_loss_pnl'] > 0:
            pf = g['gross_win_pnl'] / g['gross_loss_pnl']
            if pf < 0.8: # Market is toxic if we're losing > 20% more than we win
                return True
        return False

    def check_daily_loss(self, current_pnl, starting_balance):
        """
        Checks if the daily loss limit has been hit.
        """
        if starting_balance <= 0:
            return False
            
        loss_percent = (abs(current_pnl) / starting_balance) * 100
        if current_pnl < 0 and loss_percent >= self.daily_loss_limit:
            return True
        return False
