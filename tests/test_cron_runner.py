"""Static contract checks for the fail-loud cron wrapper."""

from pathlib import Path


def test_cron_runner_enables_alerts_spine_and_daily_gates():
    script = (Path(__file__).parents[1] / "scripts" / "cron-runner.sh").read_text()
    assert 'run_cmd "process" twag process --notify' in script
    assert 'run_cmd "spine" twag spine emit' in script
    assert ".maintenance-$(date +%Y-%m-%d)" in script
    assert ".ctx-check-$(date +%Y-%m-%d)" in script
    assert 'run_cmd "doctor" twag doctor --quiet' in script
