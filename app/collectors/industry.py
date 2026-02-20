"""行业映射: stock_code -> industry_name"""

import logging
import time
from pathlib import Path

import akshare as ak

logger = logging.getLogger(__name__)

# Module-level cache
_INDUSTRY_MAP: dict[str, str] = {}
_LOADED = False


def get_industry_map() -> dict[str, str]:
    """获取 stock_code -> industry 映射（带缓存）"""
    global _INDUSTRY_MAP, _LOADED
    if _LOADED:
        return _INDUSTRY_MAP

    # Try loading from cache file
    cache_path = Path("data/industry_cache.txt")
    if cache_path.exists():
        try:
            for line in cache_path.read_text().strip().split("\n"):
                if "," in line:
                    code, ind = line.split(",", 1)
                    _INDUSTRY_MAP[code] = ind
            if len(_INDUSTRY_MAP) > 100:
                _LOADED = True
                logger.info(f"行业映射缓存加载: {len(_INDUSTRY_MAP)} 只")
                return _INDUSTRY_MAP
        except Exception:
            _INDUSTRY_MAP.clear()

    # Build from API
    _build_industry_map()
    _LOADED = True

    # Save to cache
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{code},{ind}" for code, ind in _INDUSTRY_MAP.items()]
        cache_path.write_text("\n".join(lines))
        logger.info(f"行业映射缓存已保存: {len(_INDUSTRY_MAP)} 只")
    except Exception as e:
        logger.warning(f"缓存保存失败: {e}")

    return _INDUSTRY_MAP


def _build_industry_map():
    """从 AKShare 构建行业映射"""
    global _INDUSTRY_MAP
    logger.info("正在构建行业映射...")

    try:
        boards = ak.stock_board_industry_name_em()
        # Filter out sub-level duplicates (Ⅱ/Ⅲ)
        boards = boards[~boards["板块名称"].str.contains("Ⅱ|Ⅲ", na=False)]
        # Use all industry boards for full coverage
        boards = boards.sort_values("总市值", ascending=False)

        for _, row in boards.iterrows():
            name = str(row["板块名称"])
            try:
                df = ak.stock_board_industry_cons_em(symbol=name)
                for _, stock in df.iterrows():
                    code = str(stock["代码"])
                    if code not in _INDUSTRY_MAP:
                        _INDUSTRY_MAP[code] = name
                time.sleep(0.3)
            except Exception:
                pass

        logger.info(f"行业映射构建完成: {len(_INDUSTRY_MAP)} 只")
    except Exception as e:
        logger.error(f"行业映射构建失败: {e}")


def refresh_cache():
    """强制刷新缓存"""
    global _INDUSTRY_MAP, _LOADED
    _INDUSTRY_MAP.clear()
    _LOADED = False
    cache_path = Path("data/industry_cache.txt")
    if cache_path.exists():
        cache_path.unlink()
    return get_industry_map()
