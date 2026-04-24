# ============================================================
#  strategy/brain.py
#  Fix #1: candles sorted ascending before all indicators
#  Fix #2: iloc[1] used (last CLOSED candle, not open candle)
#  Fix #10: candle data sorted properly everywhere
# ============================================================
import pandas as pd
import numpy as np
import config


class TradingBrain:
    def __init__(self):
        self.rsi_period = config.RSI_PERIOD
        self.ma_fast    = config.MA_FAST
        self.ma_slow    = config.MA_SLOW

    # ── Helpers ───────────────────────────────────────────────

    def _to_df(self, candles: list) -> pd.DataFrame:
        """
        Convert raw Bybit candle list to a clean DataFrame.
        Fix #1 + #2: Bybit returns newest-first. We sort ascending
        so rolling indicators compute correctly, then use iloc[-2]
        (second-to-last = last CLOSED candle, iloc[-1] is still open).
        """
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(
            candles,
            columns=["time", "open", "high", "low", "close", "vol", "turnover"],
        )
        for col in ["open", "high", "low", "close", "vol"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["time"] = pd.to_numeric(df["time"])
        # Sort ASCENDING so rolling() computes chronologically (Fix #1)
        df = df.sort_values("time").reset_index(drop=True)
        return df

    def _last_closed(self, df: pd.DataFrame) -> pd.Series:
        """
        Fix #2: return the last CLOSED candle (second-to-last row).
        iloc[-1] is the still-forming live candle — never use it for signals.
        """
        if len(df) < 2:
            return df.iloc[-1]
        return df.iloc[-2]

    # ── Indicators ────────────────────────────────────────────

    def _add_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ma_fast"] = df["close"].rolling(self.ma_fast).mean()
        df["ma_slow"] = df["close"].rolling(self.ma_slow).mean()
        return df

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        delta = df["close"].diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    # ── SMC detection ─────────────────────────────────────────

    def find_order_blocks(self, df: pd.DataFrame, window: int = 20) -> list:
        """
        Bullish Order Block: last bearish candle before a strong
        impulsive bullish move. Operates on sorted (ascending) df.
        Uses iloc indexing from the end, excluding the open candle.
        """
        obs   = []
        end   = len(df) - 2   # Fix #2: stop before live open candle
        start = max(window, 3)

        for i in range(end - 1, start, -1):
            row = df.iloc[i]
            # Bearish candle
            if row["close"] >= row["open"]:
                continue
            # Next 2 candles must be bullish
            if i + 2 >= len(df):
                continue
            n1 = df.iloc[i + 1]
            n2 = df.iloc[i + 2]
            if not (n1["close"] > n1["open"] and n2["close"] > n2["open"]):
                continue
            # Impulsive: move > 2× average body
            if i + 3 >= len(df):
                continue
            move      = df.iloc[i + 3]["close"] - n1["open"]
            avg_body  = (df["close"] - df["open"]).abs().rolling(20).mean().iloc[i]
            if pd.isna(avg_body) or avg_body == 0:
                continue
            if move > avg_body * 2:
                obs.append({
                    "top":    row["high"],
                    "bottom": row["low"],
                    "index":  i,
                })
        return obs

    def find_fvg(self, df: pd.DataFrame) -> list:
        """Fair Value Gaps on sorted ascending df, excluding open candle."""
        fvgs = []
        end  = len(df) - 1   # Fix #2: exclude live candle
        for i in range(2, end):
            if df["high"].iloc[i - 2] < df["low"].iloc[i]:
                fvgs.append({
                    "top":    df["low"].iloc[i],
                    "bottom": df["high"].iloc[i - 2],
                    "index":  i - 1,
                })
        return fvgs

    # ── Potential setup check ─────────────────────────────────

    def check_potential_setup(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame):
        if df_1h.empty or df_4h.empty:
            return None

        df_4h = self._add_mas(df_4h)
        last4h = self._last_closed(df_4h)   # Fix #2
        if pd.isna(last4h["ma_fast"]) or pd.isna(last4h["ma_slow"]):
            return None
        if last4h["ma_fast"] <= last4h["ma_slow"]:
            return None

        obs = self.find_order_blocks(df_1h)
        if not obs:
            return None

        # Fix #2: use last closed candle price
        current_price = self._last_closed(df_1h)["close"]
        recent_ob     = obs[0]

        df_1h = df_1h.copy()
        df_1h["vol_avg"]  = df_1h["vol"].rolling(20).mean()
        last1h            = self._last_closed(df_1h)
        vol_surge         = (
            last1h["vol"] > last1h["vol_avg"] * 1.2
            if not pd.isna(last1h["vol_avg"]) else False
        )

        distance = (current_price - recent_ob["top"]) / current_price
        if 0 < distance <= 0.02:
            sl = recent_ob["bottom"] * 0.995
            tp = current_price + (current_price - sl) * 2
            return {
                "entry":  recent_ob["top"],
                "sl":     sl,
                "tp":     tp,
                "reason": "Approaching Bullish OB" + (" + Vol Surge" if vol_surge else ""),
            }
        return None

    # ── Main analyze ──────────────────────────────────────────

    def analyze(self, candles_1h: list, candles_4h: list, candles_daily: list = None):
        """
        Triple Screen analysis.
        Fix #1: sorts candles ascending before any indicator.
        Fix #2: reads last CLOSED candle for all signal logic.
        Returns: ('BUY'|'POTENTIAL'|'HOLD', data)
        """
        if not candles_1h or not candles_4h:
            return "HOLD", None

        df_1h = self._to_df(candles_1h)
        df_4h = self._to_df(candles_4h)

        if len(df_1h) < 50 or len(df_4h) < 50:
            return "HOLD", None

        # ── Daily trend (screen 1) ────────────────────────────
        daily_trend_up = True
        if candles_daily:
            df_d = self._to_df(candles_daily)
            if len(df_d) >= self.ma_slow:
                df_d["ma_slow"]  = df_d["close"].rolling(self.ma_slow).mean()
                last_d           = self._last_closed(df_d)
                if not pd.isna(last_d["ma_slow"]):
                    daily_trend_up = last_d["close"] > last_d["ma_slow"]

        # ── 4H trend (screen 2) ───────────────────────────────
        df_4h = self._add_mas(df_4h)
        last4h = self._last_closed(df_4h)   # Fix #2

        # Guard: MA200 needs 200 candles — skip if NaN
        if pd.isna(last4h["ma_fast"]) or pd.isna(last4h["ma_slow"]):
            return "HOLD", None

        trend_4h_up = last4h["ma_fast"] > last4h["ma_slow"]

        # ── 1H entry signals (screen 3) ───────────────────────
        obs  = self.find_order_blocks(df_1h)
        fvgs = self.find_fvg(df_1h)

        last1h        = self._last_closed(df_1h)   # Fix #2
        current_price = last1h["close"]

        df_1h = df_1h.copy()
        df_1h["vol_avg"] = df_1h["vol"].rolling(20).mean()
        last1h_v = self._last_closed(df_1h)
        vol_surge = (
            last1h_v["vol"] > last1h_v["vol_avg"] * 1.2
            if not pd.isna(last1h_v["vol_avg"]) else False
        )

        near_ob = any(
            ob["bottom"] <= current_price <= ob["top"] * 1.005
            for ob in obs
        )

        # ── Decision ──────────────────────────────────────────
        if daily_trend_up and trend_4h_up and near_ob and fvgs and vol_surge:
            return "BUY", None

        potential = self.check_potential_setup(df_1h, df_4h)
        if potential:
            return "POTENTIAL", potential

        return "HOLD", None

    def get_stop_loss(self, df_1h: pd.DataFrame) -> float:
        """
        Swing low of last 10 CLOSED candles (Fix #2: exclude open candle).
        df_1h must already be sorted ascending.
        """
        # iloc[-2] is last closed; go back 10 from there
        closed = df_1h.iloc[:-1]   # drop live candle
        return float(closed["low"].tail(10).min())
