import numpy as np
from unittest.mock import MagicMock
from src.training.config import TrainingConfig
from src.utils.metrics import BalatroMetricsCallback

def test_training_config_defaults():
    config = TrainingConfig()
    assert config.learning_rate == 3e-4
    assert config.n_steps == 4096
    assert config.batch_size == 256
    assert config.ent_coef == 0.01
    assert config.device == "auto"

def test_training_config_to_ppo_kwargs():
    config = TrainingConfig(learning_rate=1e-4, device="cpu")
    kwargs = config.to_ppo_kwargs()
    assert kwargs["learning_rate"] == 1e-4
    assert kwargs["device"] == "cpu"
    assert "total_timesteps" not in kwargs

def test_metrics_callback_on_step():
    callback = BalatroMetricsCallback()
    callback.locals = {
        "infos": [
            {"episode_metrics": {"won": True, "ante": 3, "money": 15.0, "round": 5, "chips": 3000.0}},
            {"episode_metrics": {"won": False, "ante": 2, "money": 8.0, "round": 3, "chips": 1200.0}}
        ]
    }
    
    # Run _on_step
    result = callback._on_step()
    assert result is True
    
    # Check that history lists are correctly populated
    assert callback.episode_wons == [1.0, 0.0]
    assert callback.episode_antes == [3.0, 2.0]
    assert callback.episode_moneys == [15.0, 8.0]
    assert callback.episode_rounds == [5.0, 3.0]
    assert callback.episode_chips == [3000.0, 1200.0]

def test_metrics_callback_on_rollout_end():
    callback = BalatroMetricsCallback()
    callback.model = MagicMock()
    
    # Mock history data
    callback.episode_wons = [1.0, 0.0]
    callback.episode_antes = [3.0, 2.0]
    callback.episode_moneys = [15.0, 8.0]
    callback.episode_rounds = [5.0, 3.0]
    callback.episode_chips = [3000.0, 1200.0]
    
    # Call rollout end
    callback._on_rollout_end()
    
    # Assert logs recorded correct means
    callback.model.logger.record.assert_any_call("balatro/win_rate", 0.5)
    callback.model.logger.record.assert_any_call("balatro/mean_max_ante", 2.5)
    callback.model.logger.record.assert_any_call("balatro/mean_money", 11.5)
    callback.model.logger.record.assert_any_call("balatro/mean_round_num", 4.0)
    callback.model.logger.record.assert_any_call("balatro/mean_final_chips", 2100.0)
    
    # Assert lists were cleared
    assert len(callback.episode_wons) == 0
    assert len(callback.episode_antes) == 0
    assert len(callback.episode_moneys) == 0
    assert len(callback.episode_rounds) == 0
    assert len(callback.episode_chips) == 0
