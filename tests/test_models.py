import pytest
from datetime import date
from sqlalchemy import inspect as sa_inspect
import sqlalchemy
from app.models.database import (
    Base, StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation,
)


def test_create_all_tables(db_engine):
    insp = sa_inspect(db_engine)
    tables = insp.get_table_names()
    assert "stock_daily" in tables
    assert "stock_technical" in tables
    assert "stock_fundamental" in tables
    assert "stock_money_flow" in tables
    assert "daily_recommendation" in tables


def test_insert_stock_daily(db_session):
    row = StockDaily(
        stock_code="000858", stock_name="五粮液",
        trade_date=date(2026, 2, 20),
        open=168.0, high=172.5, low=167.0, close=170.3,
        volume=85000.0, amount=1450000000.0,
        turnover_rate=1.82, amplitude=3.27, change_pct=1.35,
    )
    db_session.add(row)
    db_session.commit()
    result = db_session.query(StockDaily).filter_by(stock_code="000858").first()
    assert result is not None
    assert result.close == 170.3
    assert result.trade_date == date(2026, 2, 20)


def test_insert_recommendation(db_session):
    row = DailyRecommendation(
        trade_date=date(2026, 2, 20),
        stock_code="600519", stock_name="贵州茅台",
        rank=1, total_score=87.5,
        technical_score=82.0, fundamental_score=95.0,
        money_flow_score=85.0, sentiment_score=78.0,
        close_price=1856.0, change_pct=2.35,
        risk_level="低", industry="白酒",
        analysis_text="【技术面82分-偏多】均线多头排列...",
    )
    db_session.add(row)
    db_session.commit()
    result = db_session.query(DailyRecommendation).filter_by(rank=1).first()
    assert result.stock_name == "贵州茅台"
    assert result.total_score == 87.5


def test_unique_constraint_stock_daily(db_session):
    row1 = StockDaily(stock_code="000858", stock_name="五粮液",
                      trade_date=date(2026, 2, 20),
                      open=168.0, high=172.5, low=167.0, close=170.3,
                      volume=85000.0, amount=1450000000.0)
    row2 = StockDaily(stock_code="000858", stock_name="五粮液",
                      trade_date=date(2026, 2, 20),
                      open=169.0, high=173.0, low=166.5, close=171.0,
                      volume=90000.0, amount=1500000000.0)
    db_session.add(row1)
    db_session.commit()
    db_session.add(row2)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.commit()
