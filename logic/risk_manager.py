import config

class RiskManager:
    """
    Professional Risk Management System.
    Protects capital and ensures high-quality trade execution.
    """

    def __init__(self):
        self.max_open_trades = config.MAX_OPEN_TRADES
        self.daily_loss_limit = config.DAILY_LOSS_LIMIT_PERCENT

    def calculate_position(self, balance, entry_price, stop_loss):
        """
        Calculates the quantity based on dynamic risk rules.
        """
        if balance <= 0:
            return 0, "Invalid Balance"

        # 1. Dynamic Risk per Trade
        risk_percent = 0.02 # Default 2%
        if balance < 30:
            risk_percent = 0.01 # 1% for very small accounts
        
        risk_amount = balance * risk_percent
        
        # 2. Risk per Unit
        risk_per_unit = entry_price - stop_loss
        if risk_per_unit <= 0:
            return 0, "Invalid Stop Loss (must be below entry)"

        # 3. Quantity based on Risk
        qty = risk_amount / risk_per_unit
        
        # 4. Max Position Size Constraint (40% of balance)
        max_notional = balance * (config.MAX_POSITION_SIZE_PERCENT / 100)
        actual_notional = qty * entry_price
        
        if actual_notional > max_notional:
            qty = max_notional / entry_price
            
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
        if rr < config.REWARD_TO_RISK_RATIO:
            return False, f"RR too low ({rr:.2f} < {config.REWARD_TO_RISK_RATIO})"

        # 4. Spread Protection
        spread = (ask - bid) / bid
        if spread > config.SPREAD_LIMIT:
            return False, f"Spread too high ({spread:.2%})"

        return True, "Validated"

    def reset_daily_halt(self):
        """Resets the daily halt flag."""
        # This is used by the command handler to resume trading
        pass

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
