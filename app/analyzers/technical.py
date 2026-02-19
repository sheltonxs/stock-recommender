"""A股智选 - 技术面分析器

使用纯 pandas/numpy 实现全部技术指标计算（不依赖 pandas_ta）。
评分体系 100 分 = 趋势(40) + 量能(25) + 通道(15) + 超买超卖(20)
"""

import numpy as np
import pandas as pd


class TechnicalAnalyzer:
    """技术面评分引擎"""

    # ------------------------------------------------------------------
    # 指标计算（纯 pandas / numpy）
    # ------------------------------------------------------------------

    @staticmethod
    def calc_sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window).mean()

    @staticmethod
    def calc_ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def calc_macd(close: pd.Series,
                  fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        hist = (dif - dea) * 2
        return dif, dea, hist

    @staticmethod
    def calc_boll(close: pd.Series, window: int = 20, num_std: float = 2.0):
        mid = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        return upper, mid, lower

    @staticmethod
    def calc_rsi(close: pd.Series, window: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=window, min_periods=window).mean()
        avg_loss = loss.rolling(window=window, min_periods=window).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        return rsi

    @staticmethod
    def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series,
                 n: int = 9, m1: int = 3, m2: int = 3):
        lowest_low = low.rolling(window=n, min_periods=n).min()
        highest_high = high.rolling(window=n, min_periods=n).max()
        rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
        rsv = rsv.fillna(50)
        k = rsv.ewm(com=m1 - 1, adjust=False).mean()
        d = k.ewm(com=m2 - 1, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        direction = np.sign(close.diff()).fillna(0)
        return (volume * direction).cumsum()

    @staticmethod
    def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                 window: int = 14) -> pd.Series:
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=window).mean()

    # ------------------------------------------------------------------
    # 在 DataFrame 上批量计算所有指标
    # ------------------------------------------------------------------

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """为 K 线 DataFrame 添加所有技术指标列（原地修改并返回）"""
        df = df.copy().sort_values("trade_date").reset_index(drop=True)
        c = df["close"]

        # 均线
        for w in (5, 10, 20, 60, 120, 250):
            df[f"ma{w}"] = self.calc_sma(c, w)

        # EMA
        df["ema12"] = self.calc_ema(c, 12)
        df["ema26"] = self.calc_ema(c, 26)

        # MACD
        df["macd_dif"], df["macd_dea"], df["macd_hist"] = self.calc_macd(c)

        # BOLL
        df["boll_upper"], df["boll_mid"], df["boll_lower"] = self.calc_boll(c)

        # RSI
        for w in (6, 12, 24):
            df[f"rsi_{w}"] = self.calc_rsi(c, w)

        # KDJ
        df["kdj_k"], df["kdj_d"], df["kdj_j"] = self.calc_kdj(
            df["high"], df["low"], c
        )

        # OBV
        df["obv"] = self.calc_obv(c, df["volume"])
        df["obv_ma5"] = self.calc_sma(df["obv"], 5)
        df["obv_ma20"] = self.calc_sma(df["obv"], 20)

        # ATR
        df["atr_14"] = self.calc_atr(df["high"], df["low"], c)

        # 量比：当日成交量 / 过去 5 日均量
        df["volume_ma5"] = df["volume"].rolling(5).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma5"].replace(0, np.nan)

        # BOLL %B
        bw = df["boll_upper"] - df["boll_lower"]
        df["boll_pct_b"] = (c - df["boll_lower"]) / bw.replace(0, np.nan)

        # BOLL 带宽
        df["boll_bandwidth"] = bw / df["boll_mid"].replace(0, np.nan)

        return df

    # ------------------------------------------------------------------
    # 评分
    # ------------------------------------------------------------------

    def score(self, df: pd.DataFrame) -> dict:
        """对 K 线数据进行技术面评分，返回分数与信号。"""
        if df is None or len(df) < 60:
            return {
                "total": 0, "trend": 0, "volume": 0,
                "channel": 0, "overbought": 0, "signals": ["数据不足"],
            }

        df = self.compute_indicators(df)
        last = df.iloc[-1]
        signals: list[str] = []

        # ---------- 趋势 (40 分) ----------
        trend_score = 0

        # 均线多头排列
        ma5 = last.get("ma5")
        ma10 = last.get("ma10")
        ma20 = last.get("ma20")
        ma60 = last.get("ma60")
        if _all_valid(ma5, ma10, ma20, ma60) and ma5 > ma10 > ma20 > ma60:
            trend_score += 15
            signals.append("均线多头排列 \u2705")
        elif _all_valid(ma5, ma10, ma20) and ma5 > ma10 > ma20:
            trend_score += 8

        # MACD
        dif = last.get("macd_dif")
        dea = last.get("macd_dea")
        if _all_valid(dif, dea):
            if dif > dea and dif > 0:
                trend_score += 15
                signals.append("MACD水上金叉 \u2705")
            elif dif > dea and dif < 0:
                trend_score += 8
            elif dif < dea and dif > 0:
                trend_score += 3

        # 价格 vs MA20
        close_price = last["close"]
        if _all_valid(ma20) and close_price > ma20:
            trend_score += 10
            signals.append("价格在MA20之上 \u2705")

        trend_score = min(trend_score, 40)

        # ---------- 量能 (25 分) ----------
        vol_score = 0

        vr = last.get("volume_ratio")
        change = last.get("change_pct", 0) or 0
        if _all_valid(vr) and 1.2 <= vr <= 3.0 and change > 0:
            vol_score += 10
            signals.append(f"量比{vr:.1f}温和放量 \u2705")

        obv5 = last.get("obv_ma5")
        obv20 = last.get("obv_ma20")
        if _all_valid(obv5, obv20) and obv5 > obv20:
            vol_score += 8
            signals.append("OBV上升趋势 \u2705")

        # 连续 3 日量价齐升
        if len(df) >= 3:
            tail3 = df.tail(3)
            if (tail3["close"].diff().iloc[1:] > 0).all() and \
               (tail3["volume"].diff().iloc[1:] > 0).all():
                vol_score += 7
                signals.append("量价配合良好 \u2705")

        vol_score = min(vol_score, 25)

        # ---------- 通道 (15 分) ----------
        channel_score = 0

        pct_b = last.get("boll_pct_b")
        if _all_valid(pct_b):
            if 0.5 <= pct_b <= 0.8:
                channel_score += 8
                signals.append("BOLL中上轨运行 \u2705")
            elif pct_b < 0.2:
                channel_score += 6
            elif pct_b > 1.0:
                channel_score += 3

        # 带宽扩张
        if len(df) >= 2:
            prev_bw = df["boll_bandwidth"].iloc[-2]
            cur_bw = last.get("boll_bandwidth")
            if _all_valid(prev_bw, cur_bw) and cur_bw > prev_bw:
                channel_score += 4

        # ATR / 价格 < 5%
        atr = last.get("atr_14")
        if _all_valid(atr) and close_price > 0 and atr / close_price < 0.05:
            channel_score += 3

        channel_score = min(channel_score, 15)

        # ---------- 超买超卖 (20 分) ----------
        ob_score = 0

        rsi12 = last.get("rsi_12")
        if _all_valid(rsi12):
            if 40 <= rsi12 <= 70:
                ob_score += 6
                signals.append("RSI健康区间 \u2705")
            elif rsi12 < 30:
                ob_score += 8
                signals.append("RSI超卖反弹信号 \u2705")
            elif rsi12 > 80:
                ob_score += 0
                signals.append("\u26a0\ufe0f RSI超买")

        k = last.get("kdj_k")
        d_val = last.get("kdj_d")
        j = last.get("kdj_j")
        if _all_valid(k, d_val, j):
            if k > d_val and j < 80:
                ob_score += 6
                signals.append("KDJ金叉 \u2705")
            if k > d_val and j < 20:
                ob_score += 8
                signals.append("KDJ低位金叉 \u2705")

        ob_score = min(ob_score, 20)

        total = trend_score + vol_score + channel_score + ob_score
        return {
            "total": min(total, 100),
            "trend": trend_score,
            "volume": vol_score,
            "channel": channel_score,
            "overbought": ob_score,
            "signals": signals,
        }

    # ------------------------------------------------------------------
    # 获取最新一行指标（写入 stock_technical 表用）
    # ------------------------------------------------------------------

    def get_latest_indicators(self, df: pd.DataFrame) -> dict:
        """返回最后一个交易日的全部指标值（dict）。"""
        df = self.compute_indicators(df)
        last = df.iloc[-1]
        return {
            "ma5": _safe(last.get("ma5")),
            "ma10": _safe(last.get("ma10")),
            "ma20": _safe(last.get("ma20")),
            "ma60": _safe(last.get("ma60")),
            "ma120": _safe(last.get("ma120")),
            "ma250": _safe(last.get("ma250")),
            "ema12": _safe(last.get("ema12")),
            "ema26": _safe(last.get("ema26")),
            "macd_dif": _safe(last.get("macd_dif")),
            "macd_dea": _safe(last.get("macd_dea")),
            "macd_hist": _safe(last.get("macd_hist")),
            "boll_upper": _safe(last.get("boll_upper")),
            "boll_mid": _safe(last.get("boll_mid")),
            "boll_lower": _safe(last.get("boll_lower")),
            "rsi_6": _safe(last.get("rsi_6")),
            "rsi_12": _safe(last.get("rsi_12")),
            "rsi_24": _safe(last.get("rsi_24")),
            "kdj_k": _safe(last.get("kdj_k")),
            "kdj_d": _safe(last.get("kdj_d")),
            "kdj_j": _safe(last.get("kdj_j")),
            "atr_14": _safe(last.get("atr_14")),
            "obv": _safe(last.get("obv")),
            "volume_ratio": _safe(last.get("volume_ratio")),
        }


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _all_valid(*values) -> bool:
    """检查所有值非 None 且非 NaN"""
    for v in values:
        if v is None:
            return False
        try:
            if np.isnan(v):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _safe(v):
    """将 NaN 转为 None，保留正常数值"""
    if v is None:
        return None
    try:
        if np.isnan(v):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(v), 4)
