"""A股智选 - SQLAlchemy ORM 模型"""

from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, Float, Text, Date, DateTime, UniqueConstraint,
    Index, String,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class StockDaily(Base):
    __tablename__ = "stock_daily"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_daily_code_date"),
        Index("ix_daily_date", "trade_date"),
        Index("ix_daily_stock_code", "stock_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(20), nullable=False, default="")
    trade_date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    turnover_rate = Column(Float)
    amplitude = Column(Float)
    change_pct = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class StockTechnical(Base):
    __tablename__ = "stock_technical"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_tech_code_date"),
        Index("ix_tech_stock_code", "stock_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    trade_date = Column(Date, nullable=False)
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    ma60 = Column(Float)
    ma120 = Column(Float)
    ma250 = Column(Float)
    ema12 = Column(Float)
    ema26 = Column(Float)
    macd_dif = Column(Float)
    macd_dea = Column(Float)
    macd_hist = Column(Float)
    boll_upper = Column(Float)
    boll_mid = Column(Float)
    boll_lower = Column(Float)
    rsi_6 = Column(Float)
    rsi_12 = Column(Float)
    rsi_24 = Column(Float)
    kdj_k = Column(Float)
    kdj_d = Column(Float)
    kdj_j = Column(Float)
    atr_14 = Column(Float)
    obv = Column(Float)
    volume_ratio = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class StockFundamental(Base):
    __tablename__ = "stock_fundamental"
    __table_args__ = (
        UniqueConstraint("stock_code", "report_date", name="uq_fund_code_date"),
        Index("ix_fund_stock_code", "stock_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    report_date = Column(Date, nullable=False)
    pe_ttm = Column(Float)
    pb = Column(Float)
    ps_ttm = Column(Float)
    roe = Column(Float)
    gross_margin = Column(Float)
    net_margin = Column(Float)
    revenue_yoy = Column(Float)
    profit_yoy = Column(Float)
    debt_ratio = Column(Float)
    current_ratio = Column(Float)
    operating_cashflow = Column(Float)
    industry = Column(String(20))
    market_cap = Column(Float)
    float_market_cap = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class StockMoneyFlow(Base):
    __tablename__ = "stock_money_flow"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_mf_code_date"),
        Index("ix_mf_stock_code", "stock_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    trade_date = Column(Date, nullable=False)
    main_net_inflow = Column(Float)
    main_net_ratio = Column(Float)
    super_large_net = Column(Float)
    large_net = Column(Float)
    medium_net = Column(Float)
    small_net = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class DailyRecommendation(Base):
    __tablename__ = "daily_recommendation"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_rec_date_code"),
        Index("ix_rec_date_rank", "trade_date", "rank"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(20), nullable=False)
    rank = Column(Integer, nullable=False)
    total_score = Column(Float, nullable=False)
    technical_score = Column(Float)
    fundamental_score = Column(Float)
    money_flow_score = Column(Float)
    sentiment_score = Column(Float)
    close_price = Column(Float)
    change_pct = Column(Float)
    risk_level = Column(String(4))
    industry = Column(String(20))
    analysis_text = Column(Text)
    signals_json = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class RecommendationResult(Base):
    """推荐结果回测表 - 记录推荐股票的真实 T+1/T+3/T+5 收益"""
    __tablename__ = "recommendation_result"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_result_date_code"),
        Index("ix_result_date", "trade_date"),
        Index("ix_result_stock_code", "stock_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(50))
    recommend_score = Column(Float)
    close_at_recommend = Column(Float)
    close_t1 = Column(Float)
    close_t3 = Column(Float)
    close_t5 = Column(Float)
    return_t1 = Column(Float)
    return_t3 = Column(Float)
    return_t5 = Column(Float)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
