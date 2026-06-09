import os
from dataclasses import dataclass, field

@dataclass
class TrainingConfig:
    # PPO Hyperparameters
    learning_rate: float = 3e-4
    n_steps: int = 4096
    batch_size: int = 256
    n_epochs: int = 10
    gamma: float = 0.99
    clip_range: float = 0.2
    ent_coef: float = 0.01
    
    # Network Architecture
    policy_kwargs: dict = field(default_factory=lambda: dict(net_arch=dict(pi=[512, 512], vf=[512, 512])))
    
    # Training Loop Settings
    total_timesteps: int = 200_000
    save_freq: int = 10_000
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

