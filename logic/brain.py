import pandas as pd
import numpy as np
import config
from datetime import datetime
import pytz

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

    def get_market_trend(self, btc_df):
        """
        Determines the Global Market Trend using BTC as the driver.
        Returns 'bullish' or 'bearish'.
        Tier 7: Added RSI momentum filter to reduce sideways traps.
        """
        if btc_df is None or len(btc_df) < config.MA_SLOW:
            return "unknown"

        btc_df['ma50'] = btc_df['close'].rolling(window=config.MA_FAST).mean()
        btc_df['ma200'] = btc_df['close'].rolling(window=config.MA_SLOW).mean()

        # Calculate RSI (14)
        delta = btc_df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        btc_df['rsi'] = 100 - (100 / (1 + rs))

        current_ma50 = btc_df['ma50'].iloc[-2]
        current_ma200 = btc_df['ma200'].iloc[-2]
        current_rsi = btc_df['rsi'].iloc[-2]

        # Bullish only if MA50 > MA200 AND RSI > 50 (Positive Momentum)
        if current_ma50 > current_ma200 and current_rsi > 50:
            return "bullish"
        return "bearish"

    def _is_session_active(self):
        """
        Session Filter: Avoids high-noise/low-liquidity periods.
        Focuses on major market overlap (UTC 08:00 to 20:00).
        """
        now_utc = datetime.now(pytz.UTC)
        hour = now_utc.hour
        # Allow trading from 08:00 UTC (London Open) to 20:00 UTC (Post NY Close)
        return 8 <= hour < 20

    def evaluate_trade(self, symbol, df, balance):
        """
        Core strategy logic.
        Returns a decision dictionary.
        """
        if not self.is_halal(symbol):
            return self._hold(symbol, "Non-Halal Asset")

        if not self._is_session_active():
            return self._hold(symbol, "Outside Trading Session")

        if df is None or len(df) < config.MA_SLOW:
            return self._hold(symbol, "Insufficient Data")

        # 1. Market Structure (Trend Filter)
        df['ma50'] = df['close'].rolling(window=config.MA_FAST).mean()
        df['ma200'] = df['close'].rolling(window=config.MA_SLOW).mean()
        
        current_ma50 = df['ma50'].iloc[-2]
        current_ma200 = df['ma200'].iloc[-2]

        trend_ok = current_ma50 > current_ma200

        # 2. Weighted Confidence Scoring (Tier 9: Higher Resolution)
        score = 0.0
        reasons = []

        # Near Order Block (Core Signal)
        recent_df = df.iloc[-config.OB_WINDOW-1:-1]
        support_zone = recent_df['low'].min()
        current_price = df['close'].iloc[-2]
        distance_to_ob = abs(current_price - support_zone) / current_price

        if distance_to_ob <= 0.01:
            score += 2.5
            reasons.append(f"Primary OB (+2.5, dist: {distance_to_ob:.2%})")
        elif distance_to_ob <= 0.02:
            score += 1.5
            reasons.append(f"Secondary OB (+1.5, dist: {distance_to_ob:.2%})")

        # Fair Value Gap (Imbalance)
        fvg_detected = False
        for i in range(len(df) - config.FVG_WINDOW - 1, len(df) - 2):
            if df['high'].iloc[i-2] < df['low'].iloc[i]:
                fvg_detected = True
                break
        
        if fvg_detected:
            score += 2.0
            reasons.append("FVG Imbalance (+2.0)")

        # Volume Surge (Momentum)
        avg_volume = df['volume'].rolling(window=config.VOL_WINDOW).mean().iloc[-2]
        current_volume = df['volume'].iloc[-2]
        vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        if vol_ratio > 2.0:
            score += 1.5
            reasons.append(f"Extreme Vol Surge (+1.5, x{vol_ratio:.2f})")
        elif vol_ratio > 1.2:
            score += 1.0
            reasons.append(f"Vol Surge (+1.0, x{vol_ratio:.2f})")

        # Volatility Expansion
        atr = self._calculate_atr(df)
        body_size = abs(df['close'].iloc[-2] - df['open'].iloc[-2])
        if body_size > (atr * 1.5):
            score += 1.0
            reasons.append("High Vol Displacement (+1.0)")
        elif body_size > atr:
            score += 0.5
            reasons.append("Vol Expansion (+0.5)")

        # Final Rounding for action mapping
        display_score = round(score, 1)

        # Debug Output (Critical Fix #5)
        print(f"DEBUG: {symbol} | Trend:{trend_ok} | OB dist:{distance_to_ob:.2%} | FVG:{fvg_detected} | Score:{display_score}")

        # 3. Decision Making
        if not trend_ok:
            return self._hold(symbol, f"Trend Fail: MA50 ({current_ma50:.2f}) <= MA200 ({current_ma200:.2f})")

        action = "HOLD"
        # Determine action threshold (Soft Regime Filter)
        # Bullish BTC: Trade Score 3+ | Bearish BTC: Only Trade Score 5+
        # We'll need the global market trend passed in or calculated here
        market_trend = getattr(self, 'current_market_trend', "bullish")

        # During Calibration, we log Score 3 regardless of trend
        if config.CALIBRATION_MODE:
            threshold = config.MIN_SCORE_TO_TRADE
        else:
            # Tier 5 Regime Filter: Protect capital during bearish/unknown markets
            threshold = config.SCORE_THRESHOLD if market_trend == "bullish" else 5

        # Check against disabled buckets (Integer-based optimization)
        if int(display_score) in self.disabled_scores:
            action = "HOLD (DISABLED BY OPTIMIZER)"
        elif display_score >= threshold + 1:
            action = "STRONG BUY"
        elif display_score >= threshold:
            action = "BUY"
        elif display_score >= 2:
            action = "WATCH"

        # 4. SL/TP Calculation (Handled by Risk Manager, but we provide base values)
        # SL = Lowest low of last 10 candles
        stop_loss = support_zone - (0.5 * atr)
        take_profit = current_price + (current_price - stop_loss) * config.REWARD_TO_RISK_RATIO

        return {
            "symbol": symbol,
            "action": action,
            "score": display_score,
            "entry": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr": atr,
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
