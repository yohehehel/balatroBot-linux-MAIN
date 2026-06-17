import os
import sys
import argparse
import logging
import torch

try:
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.callbacks import CallbackList

from src.env.balatro_env import BalatroEnv
from src.training.config import TrainingConfig
from src.utils.metrics import BalatroMetricsCallback

def main():
    parser = argparse.ArgumentParser(description="Train a PPO agent to play Balatro.")
    parser.add_argument("--api-url", type=str, default="http://127.0.0.1:12346", help="Balatro JSON-RPC API URL.")
    parser.add_argument("--total-timesteps", type=int, default=None, help="Override total training timesteps.")
    parser.add_argument("--learning-rate", type=float, default=None, help="Override PPO learning rate.")
    parser.add_argument("--ent-coef", type=float, default=None, help="Override entropy coefficient.")
    parser.add_argument("--resume", type=str, default=None, help="Path to a saved PPO model to resume training from.")
    parser.add_argument("--device", type=str, default=None, help="Override target device (cpu/cuda/auto).")
    parser.add_argument("--deck", type=str, default="YELLOW", help="Deck to use for training (RED, BLUE, YELLOW, GREEN, etc.). Default: YELLOW.")
    parser.add_argument("--stake", type=str, default="WHITE", help="Stake level for training. Default: WHITE.")
    parser.add_argument("--num-instances", type=int, default=1, help="Number of parallel Balatro instances.")
    args = parser.parse_args()

    # 1. Setup logging (root is WARNING, main trainer logger is INFO)
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("TrainPPO")
    logger.setLevel(logging.INFO)

    # 2. Load configuration
    config = TrainingConfig()
    if args.total_timesteps is not None:
        config.total_timesteps = args.total_timesteps
    if args.learning_rate is not None:
        config.learning_rate = args.learning_rate
    if args.ent_coef is not None:
        config.ent_coef = args.ent_coef
    if args.device is not None:
        config.device = args.device

    # Ensure output directories exist and clean up old logs/models if starting fresh
    if not args.resume:
        logger.info("Fresh run detected. Cleaning up old logs and checkpoints...")
        import shutil
        if os.path.exists(config.log_dir):
            try:
                shutil.rmtree(config.log_dir)
            except Exception as e:
                logger.warning(f"Could not clear logs directory: {e}")
        if os.path.exists(config.model_dir):
            try:
                shutil.rmtree(config.model_dir)
            except Exception as e:
                logger.warning(f"Could not clear models directory: {e}")

    os.makedirs(config.log_dir, exist_ok=True)
    os.makedirs(config.model_dir, exist_ok=True)

    logger.info("Initializing Balatro Environment(s)...")
    # 3. Setup environment and detect active instances
    api_urls = []
    
    # If the user overrode --api-url, use only that one.
    # Otherwise, scan for active instances.
    if args.api_url != "http://127.0.0.1:12346":
        api_urls = [args.api_url]
    else:
        logger.info(f"Scanning for active Balatro API instances on ports 12346-{12346 + args.num_instances - 1}...")
        import httpx
        base_port = 12346
        for p in range(base_port, base_port + args.num_instances):
            url = f"http://127.0.0.1:{p}"
            try:
                # We use a short timeout so scanning doesn't take too long.
                with httpx.Client(timeout=0.3) as client:
                    r = client.post(url, json={"jsonrpc": "2.0", "method": "health", "id": 1})
                    if r.status_code == 200:
                        api_urls.append(url)
            except Exception:
                pass
        
        if not api_urls:
            # Fallback to default port if none detected
            api_urls = ["http://127.0.0.1:12346"]

    logger.info(f"Active Balatro instance(s) detected: {api_urls}")

    # Helper function to create an env with logging configured
    deck = args.deck
    stake = args.stake
    logger.info(f"Training with deck={deck}, stake={stake}")

    def make_env(url):
        def _init():
            # Configure logging in subprocess workers to be quiet (WARNING level)
            import logging as _logging
            if not _logging.getLogger().handlers:
                _logging.basicConfig(
                    level=_logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    handlers=[_logging.StreamHandler()],
                )
            else:
                _logging.getLogger().setLevel(_logging.WARNING)
            _logging.getLogger("BalatroEnv").setLevel(_logging.WARNING)
            _logging.getLogger("BalatroClient").setLevel(_logging.WARNING)
            _logging.getLogger("httpx").setLevel(_logging.WARNING)
            return Monitor(BalatroEnv(base_url=url, deck=deck, stake=stake))
        return _init

    if len(api_urls) > 1:
        # Use SubprocVecEnv for true parallelism across processes.
        logger.info(f"Initializing SubprocVecEnv with {len(api_urls)} parallel environments...")
        env = SubprocVecEnv([make_env(url) for url in api_urls])
    else:
        logger.info("Initializing DummyVecEnv for a single environment.")
        # Ensure we can connect to the single instance before proceeding
        try:
            temp_env = BalatroEnv(base_url=api_urls[0], deck=deck, stake=stake)
            health = temp_env.client.health()
            logger.info(f"API Connection established on {api_urls[0]}. Health check: {health}")
        except Exception as e:
            logger.error(f"Could not connect to Balatro JSON-RPC API on {api_urls[0]}. Ensure Balatro is running with the mod loaded!")
            logger.error(str(e))
            sys.exit(1)
        env = DummyVecEnv([make_env(api_urls[0])])

    # 4. Initialize or Load Model
    n_envs = len(api_urls)
    max_batch_size = config.n_steps * n_envs

    if args.resume:
        logger.info(f"Resuming training from model checkpoint: {args.resume}")
        
        # Build custom_objects to override hyperparameters on the loaded model
        custom_objects = {
            "n_steps": config.n_steps,
            "n_epochs": config.n_epochs,
            "clip_range": config.clip_range,
            "target_kl": config.target_kl,
        }
        
        # Ensure batch_size is compatible with n_steps * n_envs to avoid SB3 assertion error
        target_batch_size = config.batch_size
        if target_batch_size > max_batch_size:
            logger.warning(
                f"batch_size ({target_batch_size}) is larger than n_steps * n_envs ({max_batch_size}). "
                f"Capping batch_size to {max_batch_size} to prevent SB3 crash."
            )
            target_batch_size = max_batch_size
        custom_objects["batch_size"] = target_batch_size
        
        if args.learning_rate is not None:
            custom_objects["learning_rate"] = args.learning_rate
        else:
            custom_objects["learning_rate"] = config.learning_rate
            
        if args.ent_coef is not None:
            custom_objects["ent_coef"] = args.ent_coef
            
        model = PPO.load(
            args.resume,
            env=env,
            device=config.device,
            tensorboard_log=config.log_dir,
            custom_objects=custom_objects,
        )
        model.verbose = 0
    else:
        logger.info("Creating a new PPO model with MultiInputPolicy...")
        ppo_kwargs = config.to_ppo_kwargs()
        
        # Ensure batch_size is compatible with n_steps * n_envs
        if ppo_kwargs["batch_size"] > max_batch_size:
            logger.warning(
                f"batch_size ({ppo_kwargs['batch_size']}) is larger than n_steps * n_envs ({max_batch_size}). "
                f"Capping batch_size to {max_batch_size} to prevent SB3 crash."
            )
            ppo_kwargs["batch_size"] = max_batch_size
            
        model = PPO(
            "MultiInputPolicy",
            env,
            verbose=0,
            tensorboard_log=config.log_dir,
            **ppo_kwargs
        )

    logger.info(f"Using device: {model.device}")

    # 5. Set up callbacks
    metrics_callback = BalatroMetricsCallback(
        save_freq=max(1, config.save_freq),
        model_dir=config.model_dir
    )
    callbacks = CallbackList([metrics_callback])

    # 6. Start training
    logger.info(f"Starting training loop for {config.total_timesteps} steps...")
    try:
        model.learn(
            total_timesteps=config.total_timesteps,
            callback=callbacks,
            tb_log_name="PPO_Balatro",
            reset_num_timesteps=not args.resume
        )
        
        # Save final model
        final_model_path = os.path.join(config.model_dir, "ppo_balatro_final")
        model.save(final_model_path)
        logger.info(f"Training completed. Final model saved to {final_model_path}")
        
    except KeyboardInterrupt:
        logger.info("Training interrupted by user. Saving current model state...")
        interrupted_path = os.path.join(config.model_dir, "ppo_balatro_interrupted")
        model.save(interrupted_path)
        logger.info(f"Model saved to {interrupted_path}")
        
    except Exception as e:
        logger.error(f"Training crashed: {e}")
        raise e

if __name__ == "__main__":
    main()
