# A股智选 — 真实数据对接实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 A股智选 从 Mock 原型升级为使用 AKShare 真实数据的完整系统，包含数据采集、指标计算、多因子评分、定时调度，全程保持前端模板零修改。

**Architecture:** SQLite (via SQLAlchemy) 持久化 → AKShare 采集层写入 → pandas_ta 计算技术指标 → 4 维评分引擎打分 → FastAPI 路由从 DB 读取替代内存 Mock → APScheduler 每日盘后自动执行。数据流: AKShare → Collectors → DB → Analyzers → DB → API Routes → Templates。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, AKShare, pandas, pandas_ta, APScheduler, SQLite, Docker

**执行方式:** 使用 Agent Teams 并行开发。团队结构见下方 §0。

---

## §0 Agent Teams 执行结构

```
┌─────────────────────────────────────────────────────┐
│                   team-lead (主控)                    │
│         协调任务分配、代码审查、集成测试               │
├─────────────┬──────────────┬────────────┬────────────┤
│ foundation  │  collector   │  analyzer  │   infra    │
│   Agent     │    Agent     │   Agent    │   Agent    │
│             │              │            │            │
│ Task 1-3    │  Task 4-7    │ Task 8-12  │ Task 13-15│
│ 配置+DB+依赖 │ 4个采集模块   │ 4个评分+综合 │ 调度+集成  │
└─────────────┴──────────────┴────────────┴────────────┘
```

**并行策略:**
- **Wave 1** (并行): foundation-agent (Task 1-3) 独立执行
- **Wave 2** (并行): collector-agent (Task 4-7) + analyzer-agent (Task 8-12) 同时启动
  - analyzer 依赖 DB schema (Task 2), 不依赖 collector 实际数据
  - analyzer 用测试 fixtures 开发，不等 collector 完成
- **Wave 3**: infra-agent (Task 13-15) 负责 main.py 重构 + 调度器 + Docker
  - 依赖 Wave 2 完成

**每个 Agent 的 subagent_type:** `general-purpose` (需要读写文件 + 运行命令)

---

## §1 项目现状

```
炒股/
├── app/
│   ├── main.py              ← 941行, 全部 Mock 数据 + 路由 (将被重构)
│   ├── templates/            ← 5个 Jinja2 模板 (不改)
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── detail.html
│   │   ├── history.html
│   │   └── settings.html
│   └── static/css/, static/js/
├── requirements.txt          ← 仅 fastapi, uvicorn, jinja2
└── docs/plans/
```

**目标结构 (新增文件用 ✨ 标记):**

```
炒股/
├── app/
│   ├── main.py              ← 重构: 路由从 DB 读数据
│   ├── config.py            ✨ 配置管理
│   ├── models/
│   │   ├── __init__.py      ✨
│   │   └── database.py      ✨ SQLAlchemy 模型 (5张表)
│   ├── collectors/
│   │   ├── __init__.py      ✨
│   │   ├── base.py          ✨ 采集基类 (限速/重试)
│   │   ├── market.py        ✨ 行情+K线采集
│   │   ├── fundamental.py   ✨ 财务数据采集
│   │   ├── money_flow.py    ✨ 资金流向采集
│   │   └── sentiment.py     ✨ 市场情绪采集
│   ├── analyzers/
│   │   ├── __init__.py      ✨
│   │   ├── technical.py     ✨ 技术面评分 (100分)
│   │   ├── fundamental.py   ✨ 基本面评分 (100分)
│   │   ├── money_flow.py    ✨ 资金面评分 (100分)
│   │   ├── sentiment.py     ✨ 情绪面评分 (100分)
│   │   └── scorer.py        ✨ 综合评分 + 排名
│   ├── scheduler/
│   │   ├── __init__.py      ✨
│   │   └── jobs.py          ✨ APScheduler 任务定义
│   ├── templates/            (不改)
│   └── static/               (不改)
├── data/
│   └── stock.db             ✨ SQLite 数据文件
├── tests/
│   ├── __init__.py          ✨
│   ├── conftest.py          ✨ pytest fixtures
│   ├── test_config.py       ✨
│   ├── test_models.py       ✨
│   ├── test_collectors.py   ✨
│   ├── test_analyzers.py    ✨
│   └── test_scorer.py       ✨
├── requirements.txt          ← 更新
├── Dockerfile               ✨
└── docker-compose.yml       ✨
```

---

## §2 AKShare 接口参考

### 日K线数据
```python
import akshare as ak
df = ak.stock_zh_a_hist(symbol="000858", period="daily",
                         start_date="20250101", end_date="20260220",
                         adjust="qfq")
# 列: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
```

### 全A股实时快照
```python
df = ak.stock_zh_a_spot_em()
# 列: 序号, 代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅,
#     最高, 最低, 今开, 昨收, 量比, 换手率, 市盈率-动态, 市净率,
#     总市值, 流通市值, 60日涨跌幅, 年初至今涨跌幅
```

### 财务指标
```python
df = ak.stock_financial_analysis_indicator(symbol="000858", start_year="2023")
# ⚠️ 必须传 start_year，默认值 "1900" 会返回空 DataFrame (已知bug)
# 列: 日期, 摊薄每股收益(元), 净资产收益率(%), 主营业务利润率(%),
#     销售净利率(%), 资产负债率(%), 流动比率, ...  (40+列)
```

### 个股资金流
```python
df = ak.stock_individual_fund_flow(stock="000858", market="sz")
# 列: 日期, 收盘价, 涨跌幅, 主力净流入-净额, 主力净流入-净占比,
#     超大单净流入-净额, 超大单净流入-净占比, 大单净流入-净额, ...
```

### 板块资金流
```python
df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
# 列: 序号, 名称, 今日涨跌幅, ..., 今日主力净流入-净额, 今日主力净流入-净占比, ...
```

### 行业板块列表
```python
df = ak.stock_board_industry_name_em()
# 列: 排名, 板块名称, 板块代码, 最新价, 涨跌幅, ...
```

### 涨停池
```python
df = ak.stock_zt_pool_em(date="20260220")
# 列: 序号, 代码, 名称, 涨跌幅, 最新价, 成交额, 流通市值, 总市值,
#     换手率, 封板资金, 首次封板时间, 最后封板时间, 炸板次数, 涨停统计, 连板数, 所属行业
```

### 北向资金
```python
df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪股通")
# ⚠️ 注意函数名带 _em 后缀 (2024年8月后更新)
# 列: 日期, 数值 (单位: 亿元)
```

**通用注意事项:**
- AKShare 列名全部为中文
- 请求间隔建议 0.3-0.5 秒 (避免被东方财富封 IP)
- 部分接口交易时段数据不完整，建议 15:30 后采集
- market 参数: "sh"=上交所, "sz"=深交所, 根据代码首位判断

---

## Task 1: 项目依赖与配置模块

**Files:**
- Modify: `requirements.txt`
- Create: `app/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`
- Create: `tests/conftest.py`

**Step 1: 更新 requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
jinja2==3.1.4
akshare>=1.14.0
pandas>=2.2.0
pandas_ta>=0.3.14b
sqlalchemy>=2.0.0
apscheduler>=3.10.0
pytest>=8.0.0
httpx>=0.27.0
```

**Step 2: 安装依赖**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pip install -r requirements.txt --break-system-packages`
Expected: 全部安装成功，特别关注 akshare 是否正常

**Step 3: 写 config.py 的测试**

```python
# tests/test_config.py
from app.config import Settings

def test_default_settings():
    s = Settings()
    assert s.db_url.startswith("sqlite:///")
    assert s.stock_pool_size == 100
    assert abs(s.weight_technical + s.weight_fundamental + s.weight_money_flow + s.weight_sentiment - 1.0) < 0.01

def test_data_dir_created(tmp_path):
    s = Settings(data_dir=str(tmp_path / "data"))
    s.ensure_dirs()
    assert (tmp_path / "data").exists()
```

**Step 4: 运行测试确认失败**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

**Step 5: 实现 config.py**

```python
# app/config.py
"""A股智选 - 配置管理"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 炒股/
DATA_DIR = BASE_DIR / "data"


class Settings:
    """应用配置，可通过环境变量覆盖"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.db_url = f"sqlite:///{self.data_dir / 'stock.db'}"

        # 股票池
        self.stock_pool_size = 100

        # 评分权重 (总和 = 1.0)
        self.weight_technical = float(os.getenv("WEIGHT_TECH", "0.30"))
        self.weight_fundamental = float(os.getenv("WEIGHT_FUND", "0.25"))
        self.weight_money_flow = float(os.getenv("WEIGHT_MONEY", "0.25"))
        self.weight_sentiment = float(os.getenv("WEIGHT_SENT", "0.20"))

        # 采集参数
        self.akshare_delay = 0.4  # 秒, 请求间隔
        self.akshare_retry = 3
        self.kline_days = 250  # 拉取天数 (含计算 MA250 所需)

        # 过滤规则
        self.filter_st = True
        self.filter_new_days = 60
        self.filter_max_turnover = 20.0
        self.filter_min_market_cap = 20.0  # 亿
        self.filter_max_change_pct = 9.5

        # 调度
        self.schedule_collect_hour = 15
        self.schedule_collect_minute = 30

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
```

**Step 6: 运行测试确认通过**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_config.py -v`
Expected: PASS

**Step 7: 写 conftest.py**

```python
# tests/conftest.py
"""Shared pytest fixtures"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.database import Base


@pytest.fixture
def test_settings(tmp_path):
    s = Settings(data_dir=str(tmp_path / "data"))
    s.ensure_dirs()
    return s


@pytest.fixture
def db_engine(test_settings):
    engine = create_engine(test_settings.db_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
```

**Step 8: Commit**

```bash
git add requirements.txt app/config.py tests/__init__.py tests/test_config.py tests/conftest.py
git commit -m "feat: add project config module with settings and test fixtures"
```

---

## Task 2: 数据库模型 (5 张表)

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/database.py`
- Create: `tests/test_models.py`

**Step 1: 写模型测试**

```python
# tests/test_models.py
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.database import (
    Base, StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation,
)


def test_create_all_tables(db_engine):
    """5张表全部创建成功"""
    inspector = db_engine.dialect.get_columns
    from sqlalchemy import inspect as sa_inspect
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
    """同一股票同一日期不能重复插入"""
    import sqlalchemy
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


import pytest
```

**Step 2: 运行测试确认失败**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'`

**Step 3: 实现模型**

```python
# app/models/__init__.py
from .database import Base, StockDaily, StockTechnical, StockFundamental, StockMoneyFlow, DailyRecommendation
```

```python
# app/models/database.py
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
    """日线行情"""
    __tablename__ = "stock_daily"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_daily_code_date"),
        Index("ix_daily_date", "trade_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(20), nullable=False, default="")
    trade_date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)       # 成交量 (手)
    amount = Column(Float)       # 成交额 (元)
    turnover_rate = Column(Float)  # 换手率 %
    amplitude = Column(Float)    # 振幅 %
    change_pct = Column(Float)   # 涨跌幅 %
    created_at = Column(DateTime, default=datetime.now)


class StockTechnical(Base):
    """技术指标 (由 analyzers 计算后写入)"""
    __tablename__ = "stock_technical"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_tech_code_date"),
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
    """基本面数据"""
    __tablename__ = "stock_fundamental"
    __table_args__ = (
        UniqueConstraint("stock_code", "report_date", name="uq_fund_code_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    report_date = Column(Date, nullable=False)
    pe_ttm = Column(Float)
    pb = Column(Float)
    ps_ttm = Column(Float)
    roe = Column(Float)           # %
    gross_margin = Column(Float)  # %
    net_margin = Column(Float)    # %
    revenue_yoy = Column(Float)   # %
    profit_yoy = Column(Float)    # %
    debt_ratio = Column(Float)    # %
    current_ratio = Column(Float)
    operating_cashflow = Column(Float)  # 亿
    industry = Column(String(20))
    market_cap = Column(Float)         # 亿
    float_market_cap = Column(Float)   # 亿
    created_at = Column(DateTime, default=datetime.now)


class StockMoneyFlow(Base):
    """资金流向"""
    __tablename__ = "stock_money_flow"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_mf_code_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    trade_date = Column(Date, nullable=False)
    main_net_inflow = Column(Float)    # 万
    main_net_ratio = Column(Float)     # %
    super_large_net = Column(Float)    # 万
    large_net = Column(Float)          # 万
    medium_net = Column(Float)         # 万
    small_net = Column(Float)          # 万
    created_at = Column(DateTime, default=datetime.now)


class DailyRecommendation(Base):
    """每日推荐结果"""
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
    risk_level = Column(String(4))     # 低/中/高
    industry = Column(String(20))
    analysis_text = Column(Text)
    signals_json = Column(Text)        # JSON: {"bullish": [...], "bearish": [...]}
    created_at = Column(DateTime, default=datetime.now)
```

**Step 4: 运行测试确认通过**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_models.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add app/models/ tests/test_models.py
git commit -m "feat: add SQLAlchemy database models for 5 tables"
```

---

## Task 3: 采集基类 (限速 + 重试)

**Files:**
- Create: `app/collectors/__init__.py`
- Create: `app/collectors/base.py`
- Create: `tests/test_collectors.py` (基类部分)

**Step 1: 写测试**

```python
# tests/test_collectors.py (初始版本，后续 Task 追加)
import time
import pytest
from unittest.mock import patch, MagicMock
from app.collectors.base import BaseCollector


class DummyCollector(BaseCollector):
    def collect(self):
        return self._call_ak("dummy_func", arg1="test")


def test_rate_limiting():
    """两次请求间隔不小于 delay"""
    c = DummyCollector(delay=0.3)
    with patch("app.collectors.base.BaseCollector._call_ak_raw", return_value="ok"):
        t0 = time.time()
        c._call_ak("f1")
        c._call_ak("f2")
        elapsed = time.time() - t0
        assert elapsed >= 0.25  # 至少有一次 delay


def test_retry_on_failure():
    """失败后自动重试"""
    c = DummyCollector(delay=0.1, retry=3)
    call_count = 0

    def flaky(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("timeout")
        return "success"

    with patch("app.collectors.base.BaseCollector._call_ak_raw", side_effect=flaky):
        result = c._call_ak("f1")
        assert result == "success"
        assert call_count == 3
```

**Step 2: 运行测试确认失败**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_collectors.py::test_rate_limiting -v`
Expected: FAIL

**Step 3: 实现基类**

```python
# app/collectors/__init__.py
```

```python
# app/collectors/base.py
"""采集基类 - 限速、重试、日志"""

import time
import logging
import akshare as ak

logger = logging.getLogger(__name__)


class BaseCollector:

    def __init__(self, delay: float = 0.4, retry: int = 3):
        self.delay = delay
        self.retry = retry
        self._last_call = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _call_ak_raw(self, func_name: str, **kwargs):
        """直接调用 akshare 函数"""
        fn = getattr(ak, func_name)
        return fn(**kwargs)

    def _call_ak(self, func_name: str, **kwargs):
        """带限速 + 重试的 akshare 调用"""
        last_err = None
        for attempt in range(1, self.retry + 1):
            try:
                self._rate_limit()
                result = self._call_ak_raw(func_name, **kwargs)
                logger.debug(f"[{func_name}] 成功 (第{attempt}次)")
                return result
            except Exception as e:
                last_err = e
                logger.warning(f"[{func_name}] 第{attempt}次失败: {e}")
                if attempt < self.retry:
                    time.sleep(1.0 * attempt)  # 退避
        raise last_err

    def collect(self):
        raise NotImplementedError


def stock_market(code: str) -> str:
    """根据股票代码判断交易所: sh / sz"""
    if code.startswith(("6", "9")):
        return "sh"
    return "sz"
```

**Step 4: 运行测试确认通过**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_collectors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/collectors/ tests/test_collectors.py
git commit -m "feat: add base collector with rate limiting and retry"
```

---

## Task 4: 行情数据采集器 (market.py)

**Files:**
- Create: `app/collectors/market.py`
- Modify: `tests/test_collectors.py` (追加)

**Step 1: 写测试**

追加到 `tests/test_collectors.py`:

```python
import pandas as pd
from datetime import date
from app.collectors.market import MarketCollector


def test_parse_kline_row():
    """验证 AKShare 中文列名映射到英文"""
    raw_row = {
        "日期": "2026-02-20", "开盘": 168.5, "收盘": 170.3,
        "最高": 172.5, "最低": 167.0, "成交量": 85000,
        "成交额": 1450000000.0, "振幅": 3.27,
        "涨跌幅": 1.35, "涨跌额": 2.3, "换手率": 1.82,
    }
    c = MarketCollector.__new__(MarketCollector)
    result = c._map_kline_row("000858", "五粮液", raw_row)
    assert result["stock_code"] == "000858"
    assert result["close"] == 170.3
    assert result["trade_date"] == date(2026, 2, 20)


def test_parse_spot_row():
    """验证实时快照行映射"""
    raw_row = {
        "代码": "000858", "名称": "五粮液", "最新价": 170.3,
        "涨跌幅": 1.35, "涨跌额": 2.3, "成交量": 85000,
        "成交额": 1450000000, "振幅": 3.27, "最高": 172.5,
        "最低": 167.0, "今开": 168.5, "昨收": 168.0,
        "量比": 1.2, "换手率": 1.82, "市盈率-动态": 28.5,
        "市净率": 5.2, "总市值": 6600e8, "流通市值": 6200e8,
    }
    c = MarketCollector.__new__(MarketCollector)
    result = c._map_spot_row(raw_row)
    assert result["code"] == "000858"
    assert result["name"] == "五粮液"
    assert result["pe_ttm"] == 28.5
```

**Step 2: 运行测试确认失败**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_collectors.py::test_parse_kline_row -v`
Expected: FAIL

**Step 3: 实现 market.py**

```python
# app/collectors/market.py
"""行情数据采集: K线 + 实时快照 + 涨停池"""

import logging
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, stock_market
from app.models.database import StockDaily

logger = logging.getLogger(__name__)

# AKShare 中文列 → 英文字段映射
_KLINE_COL_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "change_pct",
    "换手率": "turnover_rate",
}


class MarketCollector(BaseCollector):
    """行情采集器"""

    def _map_kline_row(self, code: str, name: str, row: dict) -> dict:
        mapped = {"stock_code": code, "stock_name": name}
        for cn_col, en_col in _KLINE_COL_MAP.items():
            val = row.get(cn_col)
            if en_col == "trade_date" and isinstance(val, str):
                val = datetime.strptime(val, "%Y-%m-%d").date()
            elif en_col == "trade_date" and hasattr(val, "date"):
                val = val.date() if not isinstance(val, date) else val
            mapped[en_col] = val
        return mapped

    def _map_spot_row(self, row: dict) -> dict:
        return {
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": row.get("最新价"),
            "change_pct": row.get("涨跌幅"),
            "volume": row.get("成交量"),
            "amount": row.get("成交额"),
            "turnover_rate": row.get("换手率"),
            "pe_ttm": row.get("市盈率-动态"),
            "pb": row.get("市净率"),
            "market_cap": row.get("总市值"),
            "float_market_cap": row.get("流通市值"),
            "volume_ratio": row.get("量比"),
        }

    def collect_kline(self, code: str, name: str, session: Session,
                      days: int = 250) -> int:
        """采集单只股票日K线并写入 DB，返回新增行数"""
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        df = self._call_ak(
            "stock_zh_a_hist",
            symbol=code, period="daily",
            start_date=start_date, end_date=end_date,
            adjust="qfq",
        )
        if df is None or df.empty:
            logger.warning(f"[{code}] K线数据为空")
            return 0

        count = 0
        for _, row in df.iterrows():
            mapped = self._map_kline_row(code, name, row.to_dict())
            # UPSERT: 跳过已存在的
            exists = session.query(StockDaily).filter_by(
                stock_code=code, trade_date=mapped["trade_date"]
            ).first()
            if exists:
                continue
            session.add(StockDaily(**mapped))
            count += 1

        session.commit()
        logger.info(f"[{code} {name}] 新增 {count} 条K线")
        return count

    def collect_snapshot(self) -> pd.DataFrame:
        """采集全A股实时快照，返回 DataFrame (不写DB，供过滤用)"""
        df = self._call_ak("stock_zh_a_spot_em")
        return df

    def collect_zt_pool(self, trade_date: str) -> pd.DataFrame:
        """采集涨停池"""
        df = self._call_ak("stock_zt_pool_em", date=trade_date)
        return df if df is not None else pd.DataFrame()

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        """批量采集 K线
        stock_list: [(code, name), ...]
        """
        total = 0
        for code, name in stock_list:
            try:
                n = self.collect_kline(code, name, session)
                total += n
            except Exception as e:
                logger.error(f"[{code}] K线采集失败: {e}")
        logger.info(f"K线采集完成, 共新增 {total} 条")
        return total
```

**Step 4: 运行测试确认通过**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_collectors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/collectors/market.py tests/test_collectors.py
git commit -m "feat: add market data collector with kline and snapshot"
```

---

## Task 5: 财务数据采集器 (fundamental.py)

**Files:**
- Create: `app/collectors/fundamental.py`
- Modify: `tests/test_collectors.py` (追加)

**Step 1: 写测试**

```python
# 追加到 tests/test_collectors.py
from app.collectors.fundamental import FundamentalCollector


def test_map_financial_row():
    raw = {
        "日期": "2025-09-30",
        "净资产收益率(%)": 22.5,
        "主营业务利润率(%)": 68.2,
        "销售净利率(%)": 35.8,
        "资产负债率(%)": 32.5,
        "流动比率": 2.8,
    }
    c = FundamentalCollector.__new__(FundamentalCollector)
    result = c._map_financial_row("000858", raw)
    assert result["stock_code"] == "000858"
    assert result["roe"] == 22.5
    assert result["debt_ratio"] == 32.5
```

**Step 2: 实现**

```python
# app/collectors/fundamental.py
"""财务数据采集"""

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.models.database import StockFundamental

logger = logging.getLogger(__name__)


class FundamentalCollector(BaseCollector):

    def _map_financial_row(self, code: str, row: dict) -> dict:
        report_str = str(row.get("日期", ""))
        try:
            report_date = datetime.strptime(report_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            report_date = date.today()

        return {
            "stock_code": code,
            "report_date": report_date,
            "roe": row.get("净资产收益率(%)"),
            "gross_margin": row.get("主营业务利润率(%)"),
            "net_margin": row.get("销售净利率(%)"),
            "debt_ratio": row.get("资产负债率(%)"),
            "current_ratio": row.get("流动比率"),
        }

    def collect_one(self, code: str, session: Session) -> int:
        """采集单只股票财务指标，取最近4个报告期"""
        df = self._call_ak("stock_financial_analysis_indicator",
                           symbol=code, start_year="2023")
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.head(4).iterrows():
            mapped = self._map_financial_row(code, row.to_dict())
            exists = session.query(StockFundamental).filter_by(
                stock_code=code, report_date=mapped["report_date"]
            ).first()
            if exists:
                continue
            session.add(StockFundamental(**mapped))
            count += 1

        session.commit()
        return count

    def enrich_from_spot(self, code: str, spot_row: dict, session: Session):
        """从实时快照补充 PE/PB/市值 到最近一条记录"""
        latest = session.query(StockFundamental).filter_by(
            stock_code=code
        ).order_by(StockFundamental.report_date.desc()).first()

        if latest:
            latest.pe_ttm = spot_row.get("市盈率-动态")
            latest.pb = spot_row.get("市净率")
            latest.market_cap = (spot_row.get("总市值") or 0) / 1e8
            latest.float_market_cap = (spot_row.get("流通市值") or 0) / 1e8
            session.commit()

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        total = 0
        for code, name in stock_list:
            try:
                n = self.collect_one(code, session)
                total += n
            except Exception as e:
                logger.error(f"[{code}] 财务采集失败: {e}")
        logger.info(f"财务采集完成, 共 {total} 条")
        return total
```

**Step 3: 运行测试确认通过**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_collectors.py::test_map_financial_row -v`

**Step 4: Commit**

```bash
git add app/collectors/fundamental.py tests/test_collectors.py
git commit -m "feat: add fundamental data collector"
```

---

## Task 6: 资金流向采集器 (money_flow.py)

**Files:**
- Create: `app/collectors/money_flow.py`
- Modify: `tests/test_collectors.py` (追加)

**Step 1: 写测试**

```python
from app.collectors.money_flow import MoneyFlowCollector


def test_map_fund_flow_row():
    raw = {
        "日期": "2026-02-20", "收盘价": 170.3, "涨跌幅": 1.35,
        "主力净流入-净额": 23500.0,
        "主力净流入-净占比": 8.5,
        "超大单净流入-净额": 15000.0,
        "大单净流入-净额": 8500.0,
        "中单净流入-净额": -5000.0,
        "小单净流入-净额": -18500.0,
    }
    c = MoneyFlowCollector.__new__(MoneyFlowCollector)
    result = c._map_flow_row("000858", raw)
    assert result["main_net_inflow"] == 23500.0
    assert result["super_large_net"] == 15000.0
```

**Step 2: 实现**

```python
# app/collectors/money_flow.py
"""资金流向采集"""

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, stock_market
from app.models.database import StockMoneyFlow

logger = logging.getLogger(__name__)


class MoneyFlowCollector(BaseCollector):

    def _map_flow_row(self, code: str, row: dict) -> dict:
        date_str = str(row.get("日期", ""))
        try:
            trade_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            trade_date = date.today()

        return {
            "stock_code": code,
            "trade_date": trade_date,
            "main_net_inflow": row.get("主力净流入-净额"),
            "main_net_ratio": row.get("主力净流入-净占比"),
            "super_large_net": row.get("超大单净流入-净额"),
            "large_net": row.get("大单净流入-净额"),
            "medium_net": row.get("中单净流入-净额"),
            "small_net": row.get("小单净流入-净额"),
        }

    def collect_one(self, code: str, session: Session, days: int = 10) -> int:
        market = stock_market(code)
        df = self._call_ak("stock_individual_fund_flow",
                           stock=code, market=market)
        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.tail(days).iterrows():
            mapped = self._map_flow_row(code, row.to_dict())
            exists = session.query(StockMoneyFlow).filter_by(
                stock_code=code, trade_date=mapped["trade_date"]
            ).first()
            if exists:
                continue
            session.add(StockMoneyFlow(**mapped))
            count += 1

        session.commit()
        return count

    def collect(self, stock_list: list[tuple[str, str]], session: Session):
        total = 0
        for code, name in stock_list:
            try:
                n = self.collect_one(code, session)
                total += n
            except Exception as e:
                logger.error(f"[{code}] 资金流采集失败: {e}")
        logger.info(f"资金流采集完成, 共 {total} 条")
        return total
```

**Step 3: Commit**

```bash
git add app/collectors/money_flow.py tests/test_collectors.py
git commit -m "feat: add money flow collector"
```

---

## Task 7: 市场情绪采集器 (sentiment.py)

**Files:**
- Create: `app/collectors/sentiment.py`

**Step 1: 实现**

```python
# app/collectors/sentiment.py
"""市场情绪数据采集: 板块资金、涨停池、北向资金"""

import logging
from datetime import datetime

import pandas as pd

from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class SentimentCollector(BaseCollector):

    def collect_sector_flow(self) -> pd.DataFrame:
        """板块资金流排名"""
        df = self._call_ak("stock_sector_fund_flow_rank",
                           indicator="今日", sector_type="行业资金流")
        return df if df is not None else pd.DataFrame()

    def collect_board_names(self) -> pd.DataFrame:
        """行业板块列表 + 涨跌幅"""
        df = self._call_ak("stock_board_industry_name_em")
        return df if df is not None else pd.DataFrame()

    def collect_zt_pool(self, trade_date: str) -> pd.DataFrame:
        """涨停池"""
        df = self._call_ak("stock_zt_pool_em", date=trade_date)
        return df if df is not None else pd.DataFrame()

    def collect_north_flow(self) -> pd.DataFrame:
        """北向资金净流入"""
        try:
            df = self._call_ak("stock_hsgt_north_net_flow_in",
                               indicator="沪股通")
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"北向资金接口失败: {e}")
            return pd.DataFrame()

    def collect(self) -> dict:
        """采集所有情绪数据，返回原始 DataFrame 字典"""
        return {
            "sector_flow": self.collect_sector_flow(),
            "boards": self.collect_board_names(),
            "zt_pool": self.collect_zt_pool(datetime.now().strftime("%Y%m%d")),
            "north_flow": self.collect_north_flow(),
        }
```

**Step 2: Commit**

```bash
git add app/collectors/sentiment.py
git commit -m "feat: add sentiment data collector"
```

---

## Task 8: 技术面评分引擎 (analyzers/technical.py)

**Files:**
- Create: `app/analyzers/__init__.py`
- Create: `app/analyzers/technical.py`
- Create: `tests/test_analyzers.py`

**Step 1: 写测试**

```python
# tests/test_analyzers.py
import pandas as pd
import numpy as np
from app.analyzers.technical import TechnicalAnalyzer


def _make_kline_df(days=120, trend="up"):
    """构造测试用 K线 DataFrame"""
    dates = pd.date_range("2025-10-01", periods=days, freq="B")
    base = 100.0
    closes = []
    for i in range(days):
        if trend == "up":
            base *= 1 + np.random.uniform(0, 0.02)
        elif trend == "down":
            base *= 1 - np.random.uniform(0, 0.02)
        else:
            base *= 1 + np.random.uniform(-0.01, 0.01)
        closes.append(round(base, 2))

    opens = [c * np.random.uniform(0.995, 1.005) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.0, 1.02) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.98, 1.0) for o, c in zip(opens, closes)]
    volumes = [int(np.random.uniform(50000, 200000)) for _ in range(days)]

    return pd.DataFrame({
        "trade_date": dates,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "amount": [v * c for v, c in zip(volumes, closes)],
        "turnover_rate": [np.random.uniform(0.5, 5.0) for _ in range(days)],
        "change_pct": [0] + [round((closes[i] - closes[i-1]) / closes[i-1] * 100, 2)
                              for i in range(1, days)],
    })


def test_score_returns_0_to_100():
    df = _make_kline_df(120, "up")
    analyzer = TechnicalAnalyzer()
    result = analyzer.score(df)
    assert 0 <= result["total"] <= 100
    assert "trend" in result
    assert "volume" in result
    assert "channel" in result
    assert "overbought" in result
    assert isinstance(result["signals"], list)


def test_uptrend_scores_higher():
    analyzer = TechnicalAnalyzer()
    up_df = _make_kline_df(120, "up")
    down_df = _make_kline_df(120, "down")
    up_score = analyzer.score(up_df)["total"]
    down_score = analyzer.score(down_df)["total"]
    assert up_score > down_score, f"Up {up_score} should > Down {down_score}"
```

**Step 2: 实现**

```python
# app/analyzers/__init__.py
```

```python
# app/analyzers/technical.py
"""技术面评分引擎 (总分 100 = 趋势40 + 量能25 + 通道15 + 超买超卖20)
参考 PRD §4.2
"""

import pandas as pd
import pandas_ta as ta


class TechnicalAnalyzer:

    def _calc_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算全部技术指标, 就地添加列"""
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # 均线
        df["ma5"] = ta.sma(c, 5)
        df["ma10"] = ta.sma(c, 10)
        df["ma20"] = ta.sma(c, 20)
        df["ma60"] = ta.sma(c, 60)

        # MACD
        macd = ta.macd(c, fast=12, slow=26, signal=9)
        if macd is not None:
            df["macd_dif"] = macd.iloc[:, 0]
            df["macd_dea"] = macd.iloc[:, 2]
            df["macd_hist"] = macd.iloc[:, 1]

        # BOLL
        bbands = ta.bbands(c, length=20, std=2)
        if bbands is not None:
            df["boll_upper"] = bbands.iloc[:, 2]
            df["boll_mid"] = bbands.iloc[:, 1]
            df["boll_lower"] = bbands.iloc[:, 0]

        # RSI
        df["rsi_6"] = ta.rsi(c, 6)
        df["rsi_12"] = ta.rsi(c, 12)
        df["rsi_24"] = ta.rsi(c, 24)

        # KDJ
        stoch = ta.stoch(h, l, c, k=9, d=3, smooth_k=3)
        if stoch is not None:
            df["kdj_k"] = stoch.iloc[:, 0]
            df["kdj_d"] = stoch.iloc[:, 1]
            df["kdj_j"] = 3 * stoch.iloc[:, 0] - 2 * stoch.iloc[:, 1]

        # OBV
        df["obv"] = ta.obv(c, v)

        # ATR
        df["atr_14"] = ta.atr(h, l, c, 14)

        return df

    def _score_trend(self, r: pd.Series) -> tuple[int, list[str]]:
        """趋势类 (40分)"""
        score = 0
        signals = []

        # 均线排列
        ma5, ma10, ma20, ma60 = r.get("ma5"), r.get("ma10"), r.get("ma20"), r.get("ma60")
        if all(v is not None and pd.notna(v) for v in [ma5, ma10, ma20, ma60]):
            if ma5 > ma10 > ma20 > ma60:
                score += 15
                signals.append("均线多头排列 ✅")
            elif ma5 > ma10 > ma20:
                score += 8
                signals.append("均线部分多头")

        # MACD
        dif, dea = r.get("macd_dif"), r.get("macd_dea")
        if dif is not None and dea is not None and pd.notna(dif) and pd.notna(dea):
            if dif > dea and dif > 0:
                score += 15
                signals.append("MACD水上金叉 ✅")
            elif dif > dea:
                score += 8
                signals.append("MACD水下金叉")
            elif dif < dea and dif > 0:
                score += 3
            # else: 0

        # MA20 斜率
        if ma20 is not None and pd.notna(ma20) and ma20 > 0:
            score += 10 if r.get("close", 0) > ma20 else 0
            if r.get("close", 0) > ma20:
                signals.append("价格在MA20之上 ✅")

        return min(score, 40), signals

    def _score_volume(self, r: pd.Series, df: pd.DataFrame) -> tuple[int, list[str]]:
        """量能类 (25分)"""
        score = 0
        signals = []

        # 量比 (当日成交量 / 近5日均量)
        vol = r.get("volume", 0)
        if len(df) >= 6:
            avg5_vol = df["volume"].iloc[-6:-1].mean()
            if avg5_vol > 0:
                vol_ratio = vol / avg5_vol
                if 1.2 <= vol_ratio <= 3.0 and r.get("change_pct", 0) > 0:
                    score += 10
                    signals.append(f"量比{vol_ratio:.1f}温和放量 ✅")
                elif vol_ratio < 0.8 and r.get("change_pct", 0) > 0:
                    score += 5

        # OBV 趋势
        if len(df) >= 20 and "obv" in df.columns:
            obv_5 = df["obv"].iloc[-5:].mean()
            obv_20 = df["obv"].iloc[-20:].mean()
            if obv_5 > obv_20:
                score += 8
                signals.append("OBV上升趋势 ✅")

        # 量价配合 (连续3日量升价升)
        if len(df) >= 4:
            last3 = df.iloc[-3:]
            vol_up = all(last3["volume"].iloc[i] > last3["volume"].iloc[i-1]
                         for i in range(1, 3))
            price_up = all(last3["close"].iloc[i] > last3["close"].iloc[i-1]
                           for i in range(1, 3))
            if vol_up and price_up:
                score += 7
                signals.append("量价配合良好 ✅")

        return min(score, 25), signals

    def _score_channel(self, r: pd.Series) -> tuple[int, list[str]]:
        """通道类 (15分)"""
        score = 0
        signals = []

        upper = r.get("boll_upper")
        mid = r.get("boll_mid")
        lower = r.get("boll_lower")
        close = r.get("close", 0)

        if all(v is not None and pd.notna(v) for v in [upper, mid, lower]) and upper > lower:
            pct_b = (close - lower) / (upper - lower)
            if 0.5 <= pct_b <= 0.8:
                score += 8
                signals.append(f"BOLL中上轨运行(%B={pct_b:.2f}) ✅")
            elif pct_b < 0.2:
                score += 6
                signals.append("BOLL下轨支撑")
            elif pct_b > 1.0:
                score += 3

            # 带宽
            bw = (upper - lower) / mid if mid else 0
            if bw > 0.05:
                score += 4
                signals.append("BOLL开口扩大")

        # ATR
        atr = r.get("atr_14")
        if atr and close and pd.notna(atr) and close > 0:
            if atr / close < 0.05:
                score += 3

        return min(score, 15), signals

    def _score_overbought(self, r: pd.Series) -> tuple[int, list[str]]:
        """超买超卖 (20分)"""
        score = 0
        signals = []

        rsi = r.get("rsi_12")
        if rsi is not None and pd.notna(rsi):
            if 40 <= rsi <= 70:
                score += 6
                signals.append(f"RSI(12)={rsi:.0f}健康区间 ✅")
            elif rsi < 30:
                score += 8
                signals.append(f"RSI超卖({rsi:.0f})可能反弹")
            elif rsi > 80:
                signals.append(f"⚠️ RSI超买({rsi:.0f})")

        k, d, j = r.get("kdj_k"), r.get("kdj_d"), r.get("kdj_j")
        if all(v is not None and pd.notna(v) for v in [k, d, j]):
            if k > d and j < 80:
                score += 6
                signals.append("KDJ金叉 ✅")
            elif k > d and j < 20:
                score += 8
                signals.append("KDJ超卖金叉 ✅")

        return min(score, 20), signals

    def score(self, df: pd.DataFrame) -> dict:
        """对一只股票的 K线 DataFrame 打分
        返回: {"total": 0-100, "trend": .., "volume": .., "channel": ..,
               "overbought": .., "signals": [...]}
        """
        df = self._calc_indicators(df.copy())
        if df.empty:
            return {"total": 0, "trend": 0, "volume": 0, "channel": 0,
                    "overbought": 0, "signals": []}

        last = df.iloc[-1]

        trend_s, trend_sig = self._score_trend(last)
        vol_s, vol_sig = self._score_volume(last, df)
        chan_s, chan_sig = self._score_channel(last)
        ob_s, ob_sig = self._score_overbought(last)

        return {
            "total": trend_s + vol_s + chan_s + ob_s,
            "trend": trend_s,
            "volume": vol_s,
            "channel": chan_s,
            "overbought": ob_s,
            "signals": trend_sig + vol_sig + chan_sig + ob_sig,
        }

    def get_latest_indicators(self, df: pd.DataFrame) -> dict:
        """返回最新一行的技术指标 dict, 用于写入 stock_technical 表"""
        df = self._calc_indicators(df.copy())
        if df.empty:
            return {}
        last = df.iloc[-1]
        cols = ["ma5", "ma10", "ma20", "ma60", "macd_dif", "macd_dea",
                "macd_hist", "boll_upper", "boll_mid", "boll_lower",
                "rsi_6", "rsi_12", "rsi_24", "kdj_k", "kdj_d", "kdj_j",
                "atr_14", "obv"]
        result = {}
        for col in cols:
            v = last.get(col)
            result[col] = float(v) if v is not None and pd.notna(v) else None
        return result
```

**Step 3: 运行测试**

Run: `cd /Users/shelton/Desktop/炒股 && python3 -m pytest tests/test_analyzers.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add app/analyzers/ tests/test_analyzers.py
git commit -m "feat: add technical analyzer with full scoring engine"
```

---

## Task 9: 基本面评分引擎 (analyzers/fundamental.py)

**Files:**
- Create: `app/analyzers/fundamental.py`
- Modify: `tests/test_analyzers.py` (追加)

**Step 1: 写测试**

```python
# 追加到 tests/test_analyzers.py
from app.analyzers.fundamental import FundamentalAnalyzer


def test_fundamental_score_range():
    data = {
        "pe_ttm": 25.0, "pb": 3.0, "roe": 22.0,
        "gross_margin": 65.0, "net_margin": 35.0,
        "revenue_yoy": 25.0, "profit_yoy": 30.0,
        "debt_ratio": 35.0, "current_ratio": 2.5,
        "operating_cashflow": 50.0,
    }
    analyzer = FundamentalAnalyzer()
    result = analyzer.score(data, industry_avg_pe=32.0)
    assert 0 <= result["total"] <= 100
    assert "valuation" in result
    assert "profitability" in result


def test_low_pe_high_roe():
    """低PE高ROE应该得高分"""
    analyzer = FundamentalAnalyzer()
    good = {"pe_ttm": 10, "pb": 1.5, "roe": 25, "gross_margin": 70,
            "net_margin": 40, "revenue_yoy": 35, "profit_yoy": 45,
            "debt_ratio": 30, "current_ratio": 3.0, "operating_cashflow": 60}
    bad = {"pe_ttm": 100, "pb": 8, "roe": 5, "gross_margin": 15,
           "net_margin": 3, "revenue_yoy": -5, "profit_yoy": -10,
           "debt_ratio": 85, "current_ratio": 0.5, "operating_cashflow": -10}
    assert analyzer.score(good, 32)["total"] > analyzer.score(bad, 32)["total"]
```

**Step 2: 实现**

```python
# app/analyzers/fundamental.py
"""基本面评分引擎 (总分 100 = 估值30 + 盈利30 + 成长20 + 健康20)
参考 PRD §4.1
"""


class FundamentalAnalyzer:

    def _score_valuation(self, d: dict, avg_pe: float) -> tuple[int, list[str]]:
        score = 0
        signals = []
        pe = d.get("pe_ttm") or 999
        pb = d.get("pb") or 999

        if avg_pe > 0:
            if pe < avg_pe * 0.5:
                score += 12; signals.append("PE远低于行业均值 ✅")
            elif pe < avg_pe:
                score += 8; signals.append("PE低于行业均值")
            elif pe < avg_pe * 2:
                score += 4

        if pb < 1:
            score += 10; signals.append("PB<1破净 ✅")
        elif pb < 2:
            score += 7
        elif pb < 5:
            score += 3

        # PEG 简化版
        profit_yoy = d.get("profit_yoy") or 0
        if profit_yoy > 0:
            peg = pe / profit_yoy
            if peg < 0.5:
                score += 8; signals.append(f"PEG={peg:.1f}极低 ✅")
            elif peg < 1:
                score += 6
            elif peg < 1.5:
                score += 3

        return min(score, 30), signals

    def _score_profitability(self, d: dict) -> tuple[int, list[str]]:
        score = 0
        signals = []
        roe = d.get("roe") or 0
        if roe >= 20:
            score += 12; signals.append(f"ROE={roe:.1f}%优秀 ✅")
        elif roe >= 15:
            score += 9
        elif roe >= 10:
            score += 5
        else:
            score += 2

        gm = d.get("gross_margin") or 0
        if gm > 50:
            score += 8; signals.append(f"毛利率{gm:.0f}%高 ✅")
        elif gm > 30:
            score += 5
        else:
            score += 2

        nm = d.get("net_margin") or 0
        if nm > 20:
            score += 7
        elif nm > 10:
            score += 4
        else:
            score += 1

        return min(score, 30), signals

    def _score_growth(self, d: dict) -> tuple[int, list[str]]:
        score = 0
        signals = []
        rev = d.get("revenue_yoy") or 0
        if rev > 30:
            score += 8; signals.append(f"营收增速{rev:.0f}% ✅")
        elif rev > 20:
            score += 6
        elif rev > 10:
            score += 3
        else:
            score += 1

        profit = d.get("profit_yoy") or 0
        if profit > 40:
            score += 7; signals.append(f"净利润增速{profit:.0f}% ✅")
        elif profit > 25:
            score += 5
        elif profit > 10:
            score += 3
        else:
            score += 1

        return min(score, 20), signals

    def _score_health(self, d: dict) -> tuple[int, list[str]]:
        score = 0
        signals = []
        debt = d.get("debt_ratio") or 100
        if debt < 40:
            score += 7; signals.append(f"负债率{debt:.0f}%健康 ✅")
        elif debt < 60:
            score += 5
        elif debt < 80:
            score += 2

        cf = d.get("operating_cashflow") or 0
        if cf > 0:
            score += 7
            if cf > 10:
                signals.append("经营现金流充裕 ✅")
        cr = d.get("current_ratio") or 0
        if cr > 2:
            score += 6
        elif cr > 1.5:
            score += 4
        elif cr > 1:
            score += 2

        return min(score, 20), signals

    def score(self, data: dict, industry_avg_pe: float = 30.0) -> dict:
        v_s, v_sig = self._score_valuation(data, industry_avg_pe)
        p_s, p_sig = self._score_profitability(data)
        g_s, g_sig = self._score_growth(data)
        h_s, h_sig = self._score_health(data)
        return {
            "total": v_s + p_s + g_s + h_s,
            "valuation": v_s, "profitability": p_s,
            "growth": g_s, "health": h_s,
            "signals": v_sig + p_sig + g_sig + h_sig,
        }
```

**Step 3: Commit**

```bash
git add app/analyzers/fundamental.py tests/test_analyzers.py
git commit -m "feat: add fundamental analyzer scoring engine"
```

---

## Task 10: 资金面评分引擎 (analyzers/money_flow.py)

**Files:**
- Create: `app/analyzers/money_flow.py`

**Step 1: 实现**

```python
# app/analyzers/money_flow.py
"""资金面评分引擎 (总分 100)
参考 PRD §4.3
"""

from app.models.database import StockMoneyFlow
from sqlalchemy.orm import Session


class MoneyFlowAnalyzer:

    def score(self, rows: list[dict]) -> dict:
        """rows: 最近 N 天的资金流数据 (dict list, 按日期升序)"""
        if not rows:
            return {"total": 0, "signals": []}

        score = 0
        signals = []

        # 主力净流入 (3日累计) → 0-25
        recent3 = rows[-3:] if len(rows) >= 3 else rows
        main_3d = sum(r.get("main_net_inflow", 0) or 0 for r in recent3)
        if main_3d > 50000:   # 5000万 (单位:万)
            score += 25; signals.append(f"主力3日净流入{main_3d/10000:.1f}亿 ✅")
        elif main_3d > 10000:
            score += 15; signals.append(f"主力3日净流入{main_3d/10000:.1f}亿")
        elif main_3d > 0:
            score += 8

        # 连续净流入 → 0-15
        if len(recent3) >= 3:
            all_positive = all((r.get("main_net_inflow", 0) or 0) > 0 for r in recent3)
            if all_positive:
                score += 15; signals.append("主力连续3日净流入 ✅")

        # 超大单占比 → 0-15
        latest = rows[-1]
        main_total = abs(latest.get("main_net_inflow", 0) or 1)
        super_large = latest.get("super_large_net", 0) or 0
        if main_total > 0:
            ratio = abs(super_large) / main_total * 100
            if ratio > 10 and super_large > 0:
                score += 15; signals.append("超大单占比高 ✅")

        # 主力净占比 → 0-20 (简化: 用最新一天)
        net_ratio = latest.get("main_net_ratio", 0) or 0
        if net_ratio > 10:
            score += 20; signals.append(f"主力净占比{net_ratio:.1f}%强势 ✅")
        elif net_ratio > 5:
            score += 12
        elif net_ratio > 0:
            score += 5

        return {
            "total": min(score, 100),
            "signals": signals,
        }
```

**Step 2: Commit**

```bash
git add app/analyzers/money_flow.py
git commit -m "feat: add money flow analyzer scoring engine"
```

---

## Task 11: 情绪面评分引擎 (analyzers/sentiment.py)

**Files:**
- Create: `app/analyzers/sentiment.py`

```python
# app/analyzers/sentiment.py
"""市场情绪评分引擎 (总分 100)
参考 PRD §4.4
"""

import pandas as pd


class SentimentAnalyzer:

    def score(self, stock_code: str, industry: str,
              sector_flow_df: pd.DataFrame,
              zt_pool_df: pd.DataFrame,
              boards_df: pd.DataFrame) -> dict:
        score = 0
        signals = []

        # 板块热度 (所属板块涨幅前5) → 0-30
        if not boards_df.empty and "板块名称" in boards_df.columns:
            board_row = boards_df[boards_df["板块名称"].str.contains(industry, na=False)]
            if not board_row.empty:
                rank = board_row.index[0] + 1
                if rank <= 5:
                    score += 30; signals.append(f"板块热度第{rank}名 ✅")
                elif rank <= 15:
                    score += 15
                elif rank <= 30:
                    score += 5

        # 涨停/连板 → 0-20
        if not zt_pool_df.empty and "代码" in zt_pool_df.columns:
            zt_row = zt_pool_df[zt_pool_df["代码"] == stock_code]
            if not zt_row.empty:
                lianban = zt_row.iloc[0].get("连板数", 1)
                if lianban == 1:
                    score += 15; signals.append("首板涨停 ✅")
                elif lianban == 2:
                    score += 20; signals.append("2连板 ✅")
                else:
                    score += 10; signals.append(f"⚠️ {lianban}连板(追高风险)")

        # 板块资金净流入 → 0-20
        if not sector_flow_df.empty and "名称" in sector_flow_df.columns:
            sec_row = sector_flow_df[sector_flow_df["名称"].str.contains(industry, na=False)]
            if not sec_row.empty:
                sec_rank = sec_row.index[0] + 1
                if sec_rank <= 10:
                    score += 20; signals.append(f"板块资金流入前{sec_rank} ✅")
                elif sec_rank <= 20:
                    score += 10

        return {
            "total": min(score, 100),
            "signals": signals,
        }
```

**Commit:**

```bash
git add app/analyzers/sentiment.py
git commit -m "feat: add sentiment analyzer scoring engine"
```

---

## Task 12: 综合评分器 (analyzers/scorer.py)

**Files:**
- Create: `app/analyzers/scorer.py`
- Create: `tests/test_scorer.py`

**Step 1: 写测试**

```python
# tests/test_scorer.py
from app.analyzers.scorer import CompositeScorer
from app.config import Settings


def test_composite_score():
    s = Settings()
    scorer = CompositeScorer(s)
    result = scorer.compute(
        technical={"total": 80, "signals": ["均线多头 ✅"]},
        fundamental={"total": 90, "signals": ["ROE高 ✅"]},
        money_flow={"total": 70, "signals": ["主力净流入"]},
        sentiment={"total": 60, "signals": ["板块热度前5"]},
    )
    expected = 80*0.3 + 90*0.25 + 70*0.25 + 60*0.2
    assert abs(result["total_score"] - expected) < 0.1
    assert result["risk_level"] in ("低", "中", "高")
    assert len(result["signals_bullish"]) > 0


def test_risk_level():
    s = Settings()
    scorer = CompositeScorer(s)

    high = scorer.compute(
        technical={"total": 90, "signals": []},
        fundamental={"total": 90, "signals": []},
        money_flow={"total": 90, "signals": []},
        sentiment={"total": 90, "signals": []},
    )
    assert high["risk_level"] == "低"

    low = scorer.compute(
        technical={"total": 20, "signals": []},
        fundamental={"total": 20, "signals": []},
        money_flow={"total": 20, "signals": []},
        sentiment={"total": 20, "signals": []},
    )
    assert low["risk_level"] == "高"
```

**Step 2: 实现**

```python
# app/analyzers/scorer.py
"""多因子综合评分器
最终得分 = 技术面(30%) + 基本面(25%) + 资金面(25%) + 情绪(20%)
"""

import json
from app.config import Settings


class CompositeScorer:

    def __init__(self, settings: Settings | None = None):
        s = settings or Settings()
        self.w_tech = s.weight_technical
        self.w_fund = s.weight_fundamental
        self.w_money = s.weight_money_flow
        self.w_sent = s.weight_sentiment

    def compute(self, technical: dict, fundamental: dict,
                money_flow: dict, sentiment: dict) -> dict:
        tech_s = technical.get("total", 0)
        fund_s = fundamental.get("total", 0)
        money_s = money_flow.get("total", 0)
        sent_s = sentiment.get("total", 0)

        total = round(
            tech_s * self.w_tech + fund_s * self.w_fund +
            money_s * self.w_money + sent_s * self.w_sent, 1
        )

        if total >= 80:
            risk = "低"
            advice = "强烈看多"
        elif total >= 70:
            risk = "低"
            advice = "偏多"
        elif total >= 55:
            risk = "中"
            advice = "中性偏多"
        elif total >= 40:
            risk = "中"
            advice = "中性"
        else:
            risk = "高"
            advice = "偏空"

        all_signals = (
            technical.get("signals", []) + fundamental.get("signals", []) +
            money_flow.get("signals", []) + sentiment.get("signals", [])
        )
        bullish = [s for s in all_signals if "✅" in s]
        bearish = [s for s in all_signals if "⚠️" in s]

        return {
            "total_score": total,
            "technical_score": tech_s,
            "fundamental_score": fund_s,
            "money_flow_score": money_s,
            "sentiment_score": sent_s,
            "risk_level": risk,
            "advice": advice,
            "signals_bullish": bullish,
            "signals_bearish": bearish,
            "signals_json": json.dumps(
                {"bullish": bullish, "bearish": bearish},
                ensure_ascii=False,
            ),
        }
```

**Step 3: Commit**

```bash
git add app/analyzers/scorer.py tests/test_scorer.py
git commit -m "feat: add composite scorer with weighted multi-factor scoring"
```

---

## Task 13: 重构 main.py (从 DB 读数据)

**Files:**
- Modify: `app/main.py` (大规模重构)
- Create: `app/db.py` (引擎工厂)

这是最关键的一步。保持所有模板变量名不变，只替换数据源。

**Step 1: 创建 db.py**

```python
# app/db.py
"""数据库引擎管理"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models.database import Base

settings.ensure_dirs()
engine = create_engine(settings.db_url, echo=False)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    return SessionLocal()
```

**Step 2: 重构 main.py**

将整个 `main.py` 替换为从 DB 读取的版本。关键改动:

1. 删除所有 Mock 常量 (STOCK_POOL, RECOMMENDATIONS, 各 generate_* 函数)
2. 路由函数从 DB 查询
3. 保持模板变量名100%不变

核心路由改动示例:

```python
# app/main.py (关键片段)

from app.db import get_session
from app.models.database import (
    StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation,
)
import json

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = get_session()
    try:
        today = datetime.now().date()
        # 取最近有推荐数据的日期
        latest = session.query(DailyRecommendation.trade_date)\
            .order_by(DailyRecommendation.trade_date.desc()).first()
        trade_date = latest[0] if latest else today

        recs = session.query(DailyRecommendation)\
            .filter_by(trade_date=trade_date)\
            .order_by(DailyRecommendation.rank).all()

        recommendations = []
        for r in recs:
            sigs = json.loads(r.signals_json) if r.signals_json else {}
            recommendations.append({
                "rank": r.rank,
                "code": r.stock_code,
                "name": r.stock_name,
                "industry": r.industry or "",
                "total_score": r.total_score,
                "technical_score": r.technical_score,
                "fundamental_score": r.fundamental_score,
                "money_flow_score": r.money_flow_score,
                "sentiment_score": r.sentiment_score,
                "close_price": r.close_price,
                "change_pct": r.change_pct,
                "risk_level": r.risk_level,
                "advice": "强烈看多" if r.total_score >= 80 else "偏多" if r.total_score >= 70 else "中性",
                "bullish": sigs.get("bullish", []),
                "bearish": sigs.get("bearish", []),
                "warning": sigs.get("bearish", ["注意仓位控制"])[:1],
            })

        industries = sorted(set(r["industry"] for r in recommendations if r["industry"]))

        # 市场概况从快照数据构建 (或缓存)
        # ... 省略, 完整代码见实际文件

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "today": str(trade_date),
            "indices": _build_indices(),  # 从 DB/缓存构建
            "sectors": json.dumps(_build_sectors(session), ensure_ascii=False),
            "sankey": json.dumps(_build_sankey(session), ensure_ascii=False),
            "recommendations": recommendations,
            "sentiment": _build_sentiment(session),
            "industries_json": json.dumps(industries, ensure_ascii=False),
            "all_recommendations_json": json.dumps(recommendations, ensure_ascii=False),
        })
    finally:
        session.close()
```

**详细重构清单:**

| 原 Mock | 替换为 | 模板变量名 (不变) |
|---------|--------|----------------|
| `RECOMMENDATIONS` | `DailyRecommendation` 表查询 | `recommendations` |
| `STOCK_KLINES` | `StockDaily` 表 → pandas → 指标 | `kline_json`, `ma5_json`, ... |
| `STOCK_FUNDAMENTALS` | `StockFundamental` 表 | `fundamentals` |
| `STOCK_MONEY_FLOW` | `StockMoneyFlow` 表 | `money_flow` |
| `STOCK_ANALYSIS` | `DailyRecommendation.analysis_text` | `analysis` |
| `MARKET_INDICES` | 实时快照构建 | `indices` |
| `SECTORS` | `stock_board_industry_name_em` 缓存 | `sectors` |
| `SANKEY_DATA` | 板块资金流构建 | `sankey` |
| `SENTIMENT` | 涨跌统计构建 | `sentiment` |

**Step 3: 兼容降级 — 无数据时显示空状态**

如果 DB 为空 (尚未运行采集)，路由返回空列表而不是报错，前端显示"暂无数据，请运行数据采集"提示。

**Step 4: Commit**

```bash
git add app/main.py app/db.py
git commit -m "refactor: replace all mock data with database-backed queries"
```

---

## Task 14: 定时调度器 (scheduler/jobs.py)

**Files:**
- Create: `app/scheduler/__init__.py`
- Create: `app/scheduler/jobs.py`

**Step 1: 实现每日流水线**

```python
# app/scheduler/jobs.py
"""盘后定时任务: 采集 → 计算 → 评分 → 写入"""

import logging
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.collectors.market import MarketCollector
from app.collectors.fundamental import FundamentalCollector
from app.collectors.money_flow import MoneyFlowCollector
from app.collectors.sentiment import SentimentCollector
from app.analyzers.technical import TechnicalAnalyzer
from app.analyzers.fundamental import FundamentalAnalyzer
from app.analyzers.money_flow import MoneyFlowAnalyzer
from app.analyzers.sentiment import SentimentAnalyzer
from app.analyzers.scorer import CompositeScorer
from app.models.database import (
    StockDaily, StockTechnical, StockFundamental,
    StockMoneyFlow, DailyRecommendation,
)

logger = logging.getLogger(__name__)


def run_daily_pipeline():
    """每日盘后完整流水线"""
    logger.info("===== 每日流水线启动 =====")
    session = get_session()

    try:
        # --- Phase 1: 采集 ---
        logger.info("[1/4] 数据采集...")
        mc = MarketCollector()
        snapshot_df = mc.collect_snapshot()

        # 过滤: 排除 ST、停牌、市值<20亿
        pool = _filter_stock_pool(snapshot_df)
        stock_list = [(r["code"], r["name"]) for r in pool]
        logger.info(f"过滤后股票池: {len(stock_list)} 只")

        mc.collect(stock_list, session)

        fc = FundamentalCollector()
        fc.collect(stock_list, session)

        mfc = MoneyFlowCollector()
        mfc.collect(stock_list, session)

        sc = SentimentCollector()
        sentiment_data = sc.collect()

        # --- Phase 2: 计算+评分 ---
        logger.info("[2/4] 指标计算+评分...")
        tech_analyzer = TechnicalAnalyzer()
        fund_analyzer = FundamentalAnalyzer()
        money_analyzer = MoneyFlowAnalyzer()
        sent_analyzer = SentimentAnalyzer()
        scorer = CompositeScorer()

        trade_date = datetime.now().date()
        results = []

        for code, name in stock_list:
            try:
                # 技术面
                kline_rows = session.query(StockDaily).filter_by(
                    stock_code=code
                ).order_by(StockDaily.trade_date).all()

                if len(kline_rows) < 60:
                    continue

                kline_df = pd.DataFrame([{
                    "trade_date": r.trade_date, "open": r.open,
                    "high": r.high, "low": r.low, "close": r.close,
                    "volume": r.volume, "amount": r.amount,
                    "turnover_rate": r.turnover_rate,
                    "change_pct": r.change_pct,
                } for r in kline_rows])

                tech_result = tech_analyzer.score(kline_df)

                # 基本面
                fund_row = session.query(StockFundamental).filter_by(
                    stock_code=code
                ).order_by(StockFundamental.report_date.desc()).first()
                fund_data = {
                    "pe_ttm": fund_row.pe_ttm if fund_row else None,
                    "pb": fund_row.pb if fund_row else None,
                    "roe": fund_row.roe if fund_row else None,
                    "gross_margin": fund_row.gross_margin if fund_row else None,
                    "net_margin": fund_row.net_margin if fund_row else None,
                    "revenue_yoy": fund_row.revenue_yoy if fund_row else None,
                    "profit_yoy": fund_row.profit_yoy if fund_row else None,
                    "debt_ratio": fund_row.debt_ratio if fund_row else None,
                    "current_ratio": fund_row.current_ratio if fund_row else None,
                    "operating_cashflow": fund_row.operating_cashflow if fund_row else None,
                } if fund_row else {}
                fund_result = fund_analyzer.score(fund_data)

                # 资金面
                mf_rows = session.query(StockMoneyFlow).filter_by(
                    stock_code=code
                ).order_by(StockMoneyFlow.trade_date.desc()).limit(10).all()
                mf_dicts = [{"main_net_inflow": r.main_net_inflow,
                             "main_net_ratio": r.main_net_ratio,
                             "super_large_net": r.super_large_net}
                            for r in reversed(mf_rows)]
                money_result = money_analyzer.score(mf_dicts)

                # 情绪面
                industry = _get_industry(code, snapshot_df)
                sent_result = sent_analyzer.score(
                    code, industry,
                    sentiment_data.get("sector_flow", pd.DataFrame()),
                    sentiment_data.get("zt_pool", pd.DataFrame()),
                    sentiment_data.get("boards", pd.DataFrame()),
                )

                # 综合
                composite = scorer.compute(tech_result, fund_result,
                                           money_result, sent_result)
                composite["stock_code"] = code
                composite["stock_name"] = name
                composite["industry"] = industry
                composite["close_price"] = kline_df.iloc[-1]["close"]
                composite["change_pct"] = kline_df.iloc[-1].get("change_pct", 0)
                results.append(composite)

            except Exception as e:
                logger.error(f"[{code}] 评分失败: {e}")

        # --- Phase 3: 排名 + 写入 ---
        logger.info(f"[3/4] 排名... ({len(results)} 只)")
        results.sort(key=lambda x: x["total_score"], reverse=True)

        # 取 Top N
        top_n = min(settings.stock_pool_size, len(results))

        # 清除当天旧推荐
        session.query(DailyRecommendation).filter_by(
            trade_date=trade_date).delete()

        for i, r in enumerate(results[:top_n], 1):
            rec = DailyRecommendation(
                trade_date=trade_date,
                stock_code=r["stock_code"],
                stock_name=r["stock_name"],
                rank=i,
                total_score=r["total_score"],
                technical_score=r["technical_score"],
                fundamental_score=r["fundamental_score"],
                money_flow_score=r["money_flow_score"],
                sentiment_score=r["sentiment_score"],
                close_price=r["close_price"],
                change_pct=r["change_pct"],
                risk_level=r["risk_level"],
                industry=r.get("industry", ""),
                analysis_text=_build_analysis_text(r),
                signals_json=r["signals_json"],
            )
            session.add(rec)

        session.commit()
        logger.info(f"[4/4] 完成! 写入 {top_n} 条推荐")

    except Exception as e:
        logger.error(f"流水线异常: {e}")
        session.rollback()
    finally:
        session.close()


def _filter_stock_pool(df: pd.DataFrame) -> list[dict]:
    """过滤股票池 (PRD §4.6)"""
    if df is None or df.empty:
        return []
    filtered = df.copy()
    # 排除 ST
    filtered = filtered[~filtered["名称"].str.contains("ST", na=False)]
    # 排除停牌 (最新价为0或NaN)
    filtered = filtered[filtered["最新价"] > 0]
    # 市值 > 20亿
    filtered = filtered[filtered["总市值"] > 20e8]
    # 换手率 < 20%
    filtered = filtered[filtered["换手率"] < 20]
    # 涨跌幅 < 9.5% (排除已涨停)
    filtered = filtered[filtered["涨跌幅"].abs() < 9.5]

    return [{"code": str(r["代码"]), "name": str(r["名称"])}
            for _, r in filtered.iterrows()]


def _get_industry(code: str, snapshot_df: pd.DataFrame) -> str:
    """从快照获取行业 (简化版)"""
    # 实际可从 board 接口获取更准确的行业归属
    return ""


def _build_analysis_text(r: dict) -> str:
    """构建分析文字"""
    bullish = r.get("signals_bullish", [])
    bearish = r.get("signals_bearish", [])
    lines = [f"【综合评分 {r['total_score']}/100 - {r.get('advice', '')}】"]
    if bullish:
        lines.append("看多信号: " + ", ".join(bullish[:5]))
    if bearish:
        lines.append("风险提示: " + ", ".join(bearish[:3]))
    return "\n".join(lines)
```

**Step 2: 注册调度器到 FastAPI**

在 `main.py` 的 `startup` 事件中启动 APScheduler:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from app.scheduler.jobs import run_daily_pipeline

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.add_job(run_daily_pipeline, "cron",
                  hour=15, minute=30,
                  day_of_week="mon-fri",
                  id="daily_pipeline")

@app.on_event("startup")
def startup():
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
```

**手动触发 API** (`/api/task/run`):

```python
@app.post("/api/task/run")
async def api_task_run():
    from app.scheduler.jobs import run_daily_pipeline
    import threading
    t = threading.Thread(target=run_daily_pipeline, daemon=True)
    t.start()
    return {"code": 0, "message": "任务已启动"}
```

**Step 3: Commit**

```bash
git add app/scheduler/ app/main.py
git commit -m "feat: add APScheduler daily pipeline with full data flow"
```

---

## Task 15: Docker 部署

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `nginx/nginx.conf`

**Step 1: Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/ ./data/ 2>/dev/null || true

RUN mkdir -p /app/data /app/logs

ENV TZ=Asia/Shanghai
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: docker-compose.yml**

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - TZ=Asia/Shanghai
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./app/static:/usr/share/nginx/static
    depends_on:
      - app
    restart: unless-stopped
```

**Step 3: nginx.conf**

```nginx
events { worker_connections 64; }

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    server {
        listen 80;

        location /static/ {
            alias /usr/share/nginx/static/;
            expires 7d;
        }

        location / {
            proxy_pass http://app:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml nginx/
git commit -m "feat: add Docker deployment with nginx reverse proxy"
```

---

## 执行顺序总结

```
Wave 1 (foundation-agent):
  Task 1 → Task 2 → Task 3                    [顺序]

Wave 2 (并行):
  collector-agent: Task 4 → Task 5 → Task 6 → Task 7   [顺序]
  analyzer-agent:  Task 8 → Task 9 → Task 10 → Task 11 → Task 12  [顺序]

Wave 3 (infra-agent, 等 Wave 2 完成):
  Task 13 → Task 14 → Task 15                 [顺序]
```

**预估总量:** 15 个 Task, 约 20 个新文件, ~2500 行新代码

---

*计划结束 | A股智选 真实数据对接 | 2026-02-20*
