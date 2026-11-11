"""Brain settings exposes only allowlisted policy values for one PAPER run."""
import json

from backend.v3_api import V3Paths, _public_brain_config


def _paths(file):
    return V3Paths(
        journal_path=None, run_id="brain-test-01", budget_db_path=None,
        heartbeat_path=None, pause_flag_path=None,
        falco_data_dir="/tmp/unused-hawk", toro_data_dir="/tmp/unused-bull",
        brain_config_path=str(file),
    )


def test_public_brain_config_reads_actual_policy_without_leaking_secrets(tmp_path):
    f = tmp_path / "runner_config.json"
    f.write_text(json.dumps({
        "initial_equity": "2000",
        "cycle_minutes": 60,
        "daily_cap_usd": "0.75",
        "model": "deepseek-flash",
        "DEEPSEEK_API_KEY": "this-never-appears",
        "risk_policy": {
            "minimum_equity": "450",
            "min_leverage": 20,
            "max_leverage": 50,
            "max_open_risk_fraction": "0.12",
            "max_loss_margin_fraction": "0.214285714285714285",
            "max_position_margin_fraction": "0.20",
            "max_total_margin_fraction": "0.55",
            "PRIVATE_TOKEN": "another-never-appears"
        }
    }))
    before = f.read_bytes()
    response = _public_brain_config(_paths(f))
    assert response['available'] is True
    assert response['initial_equity'] == '2000'
    assert response['risk']['min_leverage'] == 20
    assert response['risk']['max_leverage'] == 50
    assert response['risk']['max_open_risk_fraction'] == '0.12'
    assert response['run_id'] == 'brain-test-01'
    assert 'this-never-appears' not in json.dumps(response)
    assert 'another-never-appears' not in json.dumps(response)
    assert before == f.read_bytes()


def test_missing_or_corrupt_policy_fails_closed_without_fake_values(tmp_path):
    f = tmp_path / "missing.json"
    assert _public_brain_config(_paths(f)) == {'available': False}
    f.write_text('{"risk_policy": null}')
    assert _public_brain_config(_paths(f)) == {'available': False}


def test_nan_and_invalid_leverage_are_not_exposed_as_numbers(tmp_path):
    f = tmp_path / "runner_config.json"
    f.write_text(json.dumps({
        "initial_equity": "NaN",
        "risk_policy": {"minimum_equity":"Infinity", "min_leverage":"20",
                        "max_leverage": True, "max_open_risk_fraction":"oops"},
    }))
    p = _public_brain_config(_paths(f))
    assert p['initial_equity'] is None
    assert p['risk']['minimum_equity'] is None
    assert p['risk']['min_leverage'] is None
    assert p['risk']['max_leverage'] is None
    assert p['risk']['max_open_risk_fraction'] is None
