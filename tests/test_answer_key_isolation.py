"""Analysis code must not read the hidden answer key; only the generator (writer) and scorecard may."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"generator.py", "scorecard.py", "config.py"}  # config only defines the path


def test_only_scorecard_reads_answer_key():
    offenders = []
    for f in list((ROOT / "src" / "fairtargets").glob("*.py")) + list((ROOT / "sql").glob("*.sql")):
        text = f.read_text(encoding="utf-8")
        if ("answer_key" in text or "ANSWER_KEY" in text) and f.name not in ALLOWED:
            offenders.append(f.name)
    assert offenders == [], f"answer key referenced outside the scoring step: {offenders}"


def test_scorecard_runs_last():
    src = (ROOT / "src" / "fairtargets" / "run_all.py").read_text(encoding="utf-8")
    body = src[src.index("def main"):]
    assert body.index("scorecard.score()") > max(body.index(s) for s in (
        "F.backtest(", "T.simulate(", "effects.estimate_all(", "export_powerbi.export("))
