import os
from dataclasses import dataclass, field

@dataclass
class TrainingConfig:
    # PPO Hyperparameters
    learning_rate: float = 1e-4
    n_steps: int = 128
    batch_size: int = 2048
    n_epochs: int = 4
    gamma: float = 0.99
    clip_range: float = 0.1
    ent_coef: float = 0.02
    
    # Network Architecture
    policy_kwargs: dict = field(default_factory=lambda: dict(net_arch=dict(pi=[512, 512], vf=[512, 512])))
    
    # Training Loop Settings
    total_timesteps: int = 200_000
    save_freq: int = 25_000
    eval_freq: int = 5_000
    device: str = "auto"
    
    # Directories
    log_dir: str = "logs"
    model_dir: str = "models"
    
    def to_ppo_kwargs(self) -> dict:
        """Returns hyperparameters as a dictionary for the PPO constructor."""
        return {
            "learning_rate": self.learning_rate,
            "n_steps": self.n_steps,
            "batch_size": self.batch_size,
            "n_epochs": self.n_epochs,
            "gamma": self.gamma,
            "clip_range": self.clip_range,
            "ent_coef": self.ent_coef,
            "device": self.device,
            "policy_kwargs": self.policy_kwargs,
        }

