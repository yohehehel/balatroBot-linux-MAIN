import os
import json
import time
import numpy as np
import psutil
from stable_baselines3.common.callbacks import BaseCallback

class BalatroMetricsCallback(BaseCallback):
    """
    Custom callback for logging Balatro-specific metrics (win rate, max ante, money, etc.)
    to TensorBoard and the console, maintaining a local high-score file, and managing
    checkpoints (keeping only the latest to save disk space).
    """
    def __init__(self, save_freq: int = 10000, model_dir: str = "models", verbose: int = 0):
        super().__init__(verbose)
        self.episode_wons = []
        self.episode_antes = []
        self.episode_moneys = []
        self.episode_rounds = []
        self.episode_chips = []
        
        self.save_freq = save_freq
        self.model_dir = model_dir
        self.last_saved_path = None
        self.last_saved_step = 0
        self.start_time = time.time()
        self.initial_steps = 0
        
        self.records_path = "logs/best_records.json"
        self.best_records = {
            "best_ante": 1,
            "best_money": 0.0,
            "best_chips": 0.0,
            "total_episodes": 0
        }
        self._load_records()
        self._last_live_step = 0
        self._live_print_freq = 100  # print live speed every N steps
        self._process = psutil.Process()  # current Python process
        psutil.cpu_percent(interval=None)  # prime the non-blocking CPU measurement

    def _load_records(self):
        if os.path.exists(self.records_path):
            try:
                with open(self.records_path, "r", encoding="utf-8") as f:
                    self.best_records.update(json.load(f))
            except Exception:
                pass

    def _save_records(self):
        os.makedirs(os.path.dirname(self.records_path), exist_ok=True)
        try:
            with open(self.records_path, "w", encoding="utf-8") as f:
                json.dump(self.best_records, f, indent=4)
        except Exception:
            pass

    def _on_training_start(self) -> None:
        self.initial_steps = self.num_timesteps
        self.start_time = time.time()
        self._last_live_step = self.num_timesteps

    def _on_step(self) -> bool:
        # Check if there are any environment info updates (SB3 VecEnv passes infos)
        for info in self.locals.get("infos", []):
            if "episode_metrics" in info:
                metrics = info["episode_metrics"]
                won = bool(metrics.get("won", False))
                ante = int(metrics.get("ante", 1))
                money = float(metrics.get("money", 0.0))
                round_num = int(metrics.get("round", 0))
                chips = float(metrics.get("chips", 0.0))

                self.episode_wons.append(float(won))
                self.episode_antes.append(float(ante))
                self.episode_moneys.append(money)
                self.episode_rounds.append(float(round_num))
                self.episode_chips.append(chips)

                # Check and update historical best records
                updated = False
                self.best_records["total_episodes"] += 1
                if ante > self.best_records["best_ante"]:
                    self.best_records["best_ante"] = ante
                    updated = True
                if money > self.best_records["best_money"]:
                    self.best_records["best_money"] = money
                    updated = True
                if chips > self.best_records["best_chips"]:
                    self.best_records["best_chips"] = chips
                    updated = True

                if updated:
                    self._save_records()

        # Handle checkpoint saving
        if self.save_freq > 0 and self.num_timesteps - self.last_saved_step >= self.save_freq:
            self.last_saved_step = self.num_timesteps
            new_save_path = os.path.join(self.model_dir, f"ppo_balatro_{self.num_timesteps}_steps.zip")
            try:
                self.model.save(new_save_path)
                print(f"\n[Saver] Checkpoint saved: {new_save_path}")
                self.last_saved_path = new_save_path
            except Exception as e:
                print(f"[Saver] Error saving checkpoint: {e}")

        # Live steps/sec display (printed every _live_print_freq steps on the same line)
        if self.num_timesteps - self._last_live_step >= self._live_print_freq:
            self._last_live_step = self.num_timesteps
            elapsed = time.time() - self.start_time
            steps_current = self.num_timesteps - self.initial_steps
            live_fps = steps_current / elapsed if elapsed > 0 else 0.0
            # _total_timesteps = target for the current learn() call (what was passed to model.learn())
            # total_timesteps   = cumulative steps trained across all learn() calls (not what we want here)
            total_steps = getattr(self.model, "_total_timesteps", None) or getattr(self.model, "total_timesteps", 0)
            percent = (self.num_timesteps / total_steps * 100) if isinstance(total_steps, (int, float)) and total_steps > 0 else 0.0
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            print(
                f"\r⏱  [{self.num_timesteps:>8}/{total_steps}] "
                f"{percent:5.1f}%  |  ⚡ {live_fps:6.1f} steps/s  "
                f"|  🖥  CPU {cpu:4.1f}%  RAM {ram:4.1f}%",
                end="", flush=True
            )

        return True

    def _on_rollout_end(self) -> None:
        """
        Called when a rollout ends. Logs to console/TensorBoard and clears history.
        """
        # _total_timesteps = target for the current learn() call
        total_steps = getattr(self.model, "_total_timesteps", None) or getattr(self.model, "total_timesteps", 0)
        current_steps = self.num_timesteps
        
        # Guard against MagicMock or non-number objects in tests
        if not isinstance(total_steps, (int, float)):
            total_steps = 0
        if not isinstance(current_steps, (int, float)):
            current_steps = 0
            
        percent = (current_steps / total_steps) * 100 if total_steps > 0 else 0
        
        # Calculate speed (FPS)
        elapsed_time = time.time() - self.start_time
        steps_current = current_steps - self.initial_steps
        fps = steps_current / elapsed_time if elapsed_time > 0 else 0.0
        
        # Get mean reward from SB3's ep_info_buffer
        mean_reward = 0.0
        if len(self.model.ep_info_buffer) > 0:
            mean_reward = np.mean([ep_info["r"] for ep_info in self.model.ep_info_buffer])
            
        print("\n================== TRAINING MONITOR ==================")
        print(f"Progress:  {current_steps}/{total_steps} steps ({percent:.1f}%)")
        print(f"Speed:     {fps:.1f} steps/second")
        # VM performance snapshot
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        proc_ram_mb = self._process.memory_info().rss / (1024 * 1024)
        print(f"CPU:       {cpu:.1f}%")
        print(f"RAM:       {ram.percent:.1f}%  ({ram.used // (1024**2)}/{ram.total // (1024**2)} MB)  [Python: {proc_ram_mb:.0f} MB]")
        print(f"Mean Reward (last 100 eps): {mean_reward:.2f}")
        
        if len(self.episode_wons) > 0:
            win_rate = np.mean(self.episode_wons) * 100
            mean_ante = np.mean(self.episode_antes)
            mean_money = np.mean(self.episode_moneys)
            mean_chips = np.mean(self.episode_chips)
            print(f"Win Rate:  {win_rate:.1f}%")
            print(f"Mean Max Ante: {mean_ante:.1f}")
            print(f"Mean Money: ${mean_money:.2f}")
            print(f"Mean Chips: {mean_chips:.1f}")
        
        print(f"Best Records: Ante {self.best_records['best_ante']} | Money ${self.best_records['best_money']:.2f} | Chips {self.best_records['best_chips']:.1f}")
        print("======================================================\n")

        if len(self.episode_wons) > 0:
            self.logger.record("balatro/win_rate", np.mean(self.episode_wons))
            self.logger.record("balatro/mean_max_ante", np.mean(self.episode_antes))
            self.logger.record("balatro/mean_money", np.mean(self.episode_moneys))
            self.logger.record("balatro/mean_round_num", np.mean(self.episode_rounds))
            self.logger.record("balatro/mean_final_chips", np.mean(self.episode_chips))
            
            # Clear history
            self.episode_wons.clear()
            self.episode_antes.clear()
            self.episode_moneys.clear()
            self.episode_rounds.clear()
            self.episode_chips.clear()
