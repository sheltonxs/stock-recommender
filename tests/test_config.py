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
