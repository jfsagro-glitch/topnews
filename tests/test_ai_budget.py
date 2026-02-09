import importlib

from db.database import NewsDatabase


def _reload_budget(monkeypatch, usd: str, reserve: str, tokens: str):
    monkeypatch.setenv("AI_DAILY_BUDGET_USD", usd)
    monkeypatch.setenv("AI_DAILY_MIN_RESERVE_USD", reserve)
    monkeypatch.setenv("AI_DAILY_BUDGET_TOKENS", tokens)
    import config.config as cfg
    importlib.reload(cfg)
    import core.services.ai_budget as ai_budget
    return importlib.reload(ai_budget)


def test_budget_ok_cost(monkeypatch):
    ai_budget = _reload_budget(monkeypatch, usd="1.0", reserve="0.25", tokens="0")
    db = NewsDatabase(db_path=":memory:")
    mgr = ai_budget.AIBudgetManager(db)

    mgr.record_usage(tokens_in=100, tokens_out=50, cost_usd=0.8)
    assert not mgr.budget_ok("summary", estimated_tokens=10)
    assert set(mgr.degrade_policy()) == {"summary", "cleanup", "hashtags_ai"}


def test_budget_ok_tokens(monkeypatch):
    ai_budget = _reload_budget(monkeypatch, usd="0", reserve="0", tokens="100")
    db = NewsDatabase(db_path=":memory:")
    mgr = ai_budget.AIBudgetManager(db)

    mgr.record_usage(tokens_in=80, tokens_out=10, cost_usd=0.0)
    assert not mgr.budget_ok("cleanup", estimated_tokens=20)
