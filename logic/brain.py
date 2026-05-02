import pandas as pd
import numpy as np
import config

class Brain:
    """
    Senior Quantitative Developer's Strategy Engine.
    Implements a weighted scoring system with trend, Order Blocks, FVG, and Volume Surges.
    """

    def __init__(self):
        self.halal_pairs = config.HALAL_PAIRS
        self.disabled_scores = set()

    def set_disabled_scores(self, scores):
        """Updates the set of disabled scores based on optimizer feedback."""
        self.disabled_scores = set(scores)

    def is_halal(self, symbol):
        """Checks if the symbol is in the Sharia-compliant whitelist."""
        return symbol in self.halal_pairs

    def evaluate_trade(self, symbol, df, balance):
        """
        Core strategy logic.
        Returns a decision dictionary.
        """
        if not self.is_halal(symbol):
            return self._hold(symbol, "Non-Halal Asset")

        if df is None or len(df) < config.MA_SLOW:
            return self._hold(symbol, "Insufficient Data")

        # 1. Market Structure (Trend Filter)
        df['ma50'] = df['close'].rolling(window=config.MA_FAST).mean()
        df['ma200'] = df['close'].rolling(window=config.MA_SLOW).mean()
        
        current_ma50 = df['ma50'].iloc[-2]
        current_ma200 = df['ma200'].iloc[-2]

        trend_ok = current_ma50 > current_ma200

        # 2. Weighted Scoring System
        score = 0
        reasons = []

        # Near Order Block (Support Zone)
        # Look for the lowest low in the last 10 CLOSED candles
        recent_df = df.iloc[-config.OB_WINDOW-1:-1]
        support_zone = recent_df['low'].min()
        current_price = df['close'].iloc[-2]
        
        # Check if current price is within 2% of the support zone (using abs as per user request)
        distance_to_ob = abs(current_price - support_zone) / current_price
        near_ob = distance_to_ob <= 0.02
        if near_ob:
            score += 2
            reasons.append(f"Near Order Block (+2, dist: {distance_to_ob:.2%})")

        # Fair Value Gap (Imbalance)
        # FVG is when high of candle 1 < low of candle 3 (for bullish)
        # We look at the last few candles
        fvg_detected = False
        for i in range(len(df) - config.FVG_WINDOW - 1, len(df) - 2):
            if df['high'].iloc[i-2] < df['low'].iloc[i]:
                fvg_detected = True
                break
        
        if fvg_detected:
            score += 2
            reasons.append("Fair Value Gap Detected (+2)")

        # Volume Surge
        avg_volume = df['volume'].rolling(window=config.VOL_WINDOW).mean().iloc[-2]
        current_volume = df['volume'].iloc[-2]
        volume_ok = current_volume > config.VOL_MULTIPLIER * avg_volume
        if volume_ok:
            score += 1
            reasons.append(f"Volume Surge (+1, x{current_volume/avg_volume:.2f})")

        # Session Boost (Optional/Simplified: Check if price action is expanding)
        # We'll use a simple volatility expansion check as a proxy for session boost
        atr = self._calculate_atr(df)
        volatility_boost = df['high'].iloc[-2] - df['low'].iloc[-2] > atr
        if volatility_boost:
            score += 1
            reasons.append("Volatility Expansion Boost (+1)")

        # Debug Output (Critical Fix #5)
        print(f"DEBUG: {symbol} | Trend:{trend_ok} | OB:{near_ob} | FVG:{fvg_detected} | Vol:{volume_ok} | Score:{score}")

        # 3. Decision Making
        if not trend_ok:
            return self._hold(symbol, f"Trend Fail: MA50 ({current_ma50:.2f}) <= MA200 ({current_ma200:.2f})")

        action = "HOLD"
        if score in self.disabled_scores:
            action = "HOLD (DISABLED BY OPTIMIZER)"
        elif score >= config.SCORE_THRESHOLD + 1:
            action = "STRONG BUY"
        elif score >= config.SCORE_THRESHOLD:
            action = "BUY"
        elif score >= 2:
            action = "WATCH"

        # 4. SL/TP Calculation (Handled by Risk Manager, but we provide base values)
        # SL = Lowest low of last 10 candles
        stop_loss = support_zone - (0.5 * atr)
        take_profit = current_price + (current_price - stop_loss) * config.REWARD_TO_RISK_RATIO

        return {
            "symbol": symbol,
            "action": action,
            "score": score,
            "entry": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": " | ".join(reasons) if reasons else "Trend OK, but no extra signals",
            "sharia_status": "Verified"
        }

    def _hold(self, symbol, reason):
        return {
            "symbol": symbol,
            "action": "HOLD",
            "score": 0,
            "reason": reason,
            "sharia_status": "Verified"
        }

    def _calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(window=period).mean().iloc[-2]
