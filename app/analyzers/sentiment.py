"""A股智选 - 情绪面 / 市场热度分析器

基于板块排名、涨停池、板块资金流向、市场广度等维度评分（100 分）。
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
        signals: list[str] = []
        total_score = 0

        # ---------- 板块涨幅排名 (25 分) ----------
        if boards_df is not None and not boards_df.empty and industry:
            board_rank = self._find_board_rank(boards_df, industry)
            if board_rank is not None:
                if board_rank <= 5:
                    total_score += 25
                    signals.append(f"板块涨幅排名第{board_rank}(前5)")
                elif board_rank <= 15:
                    total_score += 15
                    signals.append(f"板块涨幅排名第{board_rank}(前15)")
                elif board_rank <= 30:
                    total_score += 5

        # ---------- 涨停池 (25 分) ----------
        if zt_pool_df is not None and not zt_pool_df.empty:
            code_col = "代码"
            lianban_col = "连板数"
            if code_col in zt_pool_df.columns and lianban_col in zt_pool_df.columns:
                match = zt_pool_df[
                    zt_pool_df[code_col].astype(str).str.contains(stock_code)
                ]
                if not match.empty:
                    lianban = int(match.iloc[0][lianban_col])
                    if lianban == 1:
                        total_score += 15
                        signals.append("首板涨停")
                    elif lianban == 2:
                        total_score += 20
                        signals.append("2连板")
                    elif lianban >= 3:
                        total_score += 10
                        signals.append(f"{lianban}连板(追高风险)")

        # ---------- 板块资金流排名 (20 分) ----------
        if sector_flow_df is not None and not sector_flow_df.empty and industry:
            flow_rank = self._find_sector_flow_rank(sector_flow_df, industry)
            if flow_rank is not None:
                if flow_rank <= 10:
                    total_score += 20
                    signals.append(f"板块资金流排名第{flow_rank}(前10)")
                elif flow_rank <= 20:
                    total_score += 10

        # ---------- 市场广度/整体情绪 (30 分) ----------
        # 即使没有 industry 也能得分
        market_score = self._market_breadth_score(boards_df, zt_pool_df)
        total_score += market_score
        if market_score >= 20:
            signals.append("市场情绪活跃")
        elif market_score >= 10:
            signals.append("市场情绪中性")

        total_score = min(total_score, 100)
        return {"total": total_score, "signals": signals}

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _find_board_rank(boards_df: pd.DataFrame, industry: str) -> int | None:
        col = "板块名称"
        if col not in boards_df.columns:
            return None
        sorted_df = boards_df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        matches = sorted_df[sorted_df[col].astype(str).str.contains(industry, na=False)]
        if matches.empty:
            return None
        return int(matches.index[0]) + 1

    @staticmethod
    def _find_sector_flow_rank(sector_flow_df: pd.DataFrame, industry: str) -> int | None:
        name_col = None
        for candidate in ("名称", "板块名称"):
            if candidate in sector_flow_df.columns:
                name_col = candidate
                break
        if name_col is None:
            return None
        df = sector_flow_df.reset_index(drop=True)
        matches = df[df[name_col].astype(str).str.contains(industry, na=False)]
        if matches.empty:
            return None
        return int(matches.index[0]) + 1

    @staticmethod
    def _market_breadth_score(
        boards_df: pd.DataFrame | None,
        zt_pool_df: pd.DataFrame | None,
    ) -> int:
        """市场广度评分: 基于板块涨跌比和涨停数量，最高30分"""
        score = 0

        # 板块涨跌比 (最高15分)
        if boards_df is not None and not boards_df.empty:
            col = "涨跌幅"
            if col in boards_df.columns:
                up = (boards_df[col] > 0).sum()
                down = (boards_df[col] < 0).sum()
                total = up + down
                if total > 0:
                    up_ratio = up / total
                    if up_ratio > 0.7:
                        score += 15
                    elif up_ratio > 0.5:
                        score += 10
                    elif up_ratio > 0.3:
                        score += 5

        # 涨停池活跃度 (最高15分)
        if zt_pool_df is not None and not zt_pool_df.empty:
            zt_count = len(zt_pool_df)
            if zt_count >= 80:
                score += 15
            elif zt_count >= 50:
                score += 10
            elif zt_count >= 20:
                score += 5

        return score
