"""A股智选 - 情绪面 / 市场热度分析器

基于板块排名、涨停池、板块资金流向等维度评分（100 分）。
"""

import pandas as pd


class SentimentAnalyzer:
    """情绪面评分引擎"""

    def score(
        self,
        stock_code: str,
        industry: str,
        sector_flow_df: pd.DataFrame | None,
        zt_pool_df: pd.DataFrame | None,
        boards_df: pd.DataFrame | None,
    ) -> dict:
        """
        Args:
            stock_code: 股票代码，如 "600519"
            industry: 所属行业/板块名称，如 "白酒"
            sector_flow_df: 板块资金流向（含 "名称" 或 "板块名称"）
            zt_pool_df: 涨停池（含 "代码", "连板数"）
            boards_df: 板块涨幅排名（含 "板块名称", "涨跌幅"）

        Returns:
            {"total", "signals"}
        """
        signals: list[str] = []
        total_score = 0

        # ---------- 板块涨幅排名 (30 分) ----------
        if boards_df is not None and not boards_df.empty and industry:
            board_rank = self._find_board_rank(boards_df, industry)
            if board_rank is not None:
                if board_rank <= 5:
                    total_score += 30
                    signals.append(f"板块涨幅排名第{board_rank}(前5) \u2705")
                elif board_rank <= 15:
                    total_score += 15
                    signals.append(f"板块涨幅排名第{board_rank}(前15) \u2705")
                elif board_rank <= 30:
                    total_score += 5

        # ---------- 涨停池 (30 分) ----------
        if zt_pool_df is not None and not zt_pool_df.empty:
            code_col = "代码"
            lianban_col = "连板数"
            if code_col in zt_pool_df.columns and lianban_col in zt_pool_df.columns:
                # 股票代码可能带前缀，做模糊匹配
                match = zt_pool_df[
                    zt_pool_df[code_col].astype(str).str.contains(stock_code)
                ]
                if not match.empty:
                    lianban = int(match.iloc[0][lianban_col])
                    if lianban == 1:
                        total_score += 15
                        signals.append(f"首板涨停 \u2705")
                    elif lianban == 2:
                        total_score += 20
                        signals.append(f"2连板 \u2705")
                    elif lianban >= 3:
                        total_score += 10
                        signals.append(f"\u26a0\ufe0f {lianban}连板(追高风险)")

        # ---------- 板块资金流排名 (20 分) ----------
        if sector_flow_df is not None and not sector_flow_df.empty and industry:
            flow_rank = self._find_sector_flow_rank(sector_flow_df, industry)
            if flow_rank is not None:
                if flow_rank <= 10:
                    total_score += 20
                    signals.append(f"板块资金流排名第{flow_rank}(前10) \u2705")
                elif flow_rank <= 20:
                    total_score += 10

        total_score = min(total_score, 100)
        return {"total": total_score, "signals": signals}

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _find_board_rank(boards_df: pd.DataFrame, industry: str) -> int | None:
        """在板块涨幅 DataFrame 中查找行业排名（1-based）。"""
        col = "板块名称"
        if col not in boards_df.columns:
            return None

        sorted_df = boards_df.sort_values("涨跌幅", ascending=False).reset_index(
            drop=True
        )
        matches = sorted_df[sorted_df[col].astype(str).str.contains(industry)]
        if matches.empty:
            return None
        return int(matches.index[0]) + 1  # 1-based rank

    @staticmethod
    def _find_sector_flow_rank(
        sector_flow_df: pd.DataFrame, industry: str
    ) -> int | None:
        """在板块资金流 DataFrame 中查找排名（1-based，按原始顺序）。"""
        # 可能叫 "名称" 或 "板块名称"
        name_col = None
        for candidate in ("名称", "板块名称"):
            if candidate in sector_flow_df.columns:
                name_col = candidate
                break
        if name_col is None:
            return None

        df = sector_flow_df.reset_index(drop=True)
        matches = df[df[name_col].astype(str).str.contains(industry)]
        if matches.empty:
            return None
        return int(matches.index[0]) + 1
