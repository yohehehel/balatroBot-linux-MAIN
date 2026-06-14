import gymnasium as gym
import numpy as np
import logging
import time
from typing import Dict, Any, Tuple, Optional

from src.client import BalatroClient, BalatroAPIError
from src.game_state import GameState
from src.env.observation import get_observation_space, encode_observation
from src.env.action import get_action_space, decode_action, BOOSTER_STATES

logger = logging.getLogger("BalatroEnv")

# Maximum number of shop actions per visit before forcing next_round
MAX_SHOP_ACTIONS = 20

# After this many consecutive Connection-refused errors, the instance is considered
# permanently dead (Wine process crashed). Truncate the episode so SB3 can move on.
MAX_DEAD_STEPS = 5
MAX_TIMEOUT_STEPS = 2


class BalatroEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, base_url: str = "http://127.0.0.1:12346", timeout: float = 15.0,
                 deck: str = "YELLOW", stake: str = "WHITE"):
        super().__init__()
        self.client = BalatroClient(base_url=base_url, timeout=timeout)
        self.deck = deck
        self.stake = stake
        
        # Define spaces
        self.observation_space = get_observation_space()
        self.action_space = get_action_space()
        
        # Environment state
        self.current_state: Optional[GameState] = None
        self.invalid_actions_in_a_row = 0
        self.max_invalid_actions = 20
        self._step_count = 0
        self._env_id = base_url.split(":")[-1]  # port number for logging
        
        # Phase 2: shop action counter to prevent infinite shop loops
        self._shop_actions_taken = 0
        # Dead-instance detection: counts consecutive steps that got Connection refused.
        # When it reaches MAX_DEAD_STEPS the episode is truncated so SB3 doesn't spin forever.
        self._consecutive_conn_errors = 0
        self._consecutive_timeout_errors = 0

    def _auto_skip_boosters(self, state: GameState) -> GameState:
        """Fallback: automatically skip booster pack selection if the agent
        can't handle it (e.g. unexpected booster during non-booster states).
        
        In Phase 2, this is only called as a safety net after certain actions
        (blind select, cash_out) — not after buy_pack, where the agent drives
        the booster interaction directly.
        
        Handles timing race conditions where the pack may have already auto-closed
        between the time the gamestate was reported and the time we call pack(skip=True).
        """
        max_retries = 5
        retries = 0
        while state.state in BOOSTER_STATES and retries < max_retries:
            retries += 1

            # Verify pack is actually present in gamestate data.
            if not state.pack or not state.pack.cards:
                logger.info(
                    f"Booster state '{state.state}' reported but no pack cards "
                    f"present in gamestate. Refreshing gamestate..."
                )
                try:
                    state = self.client.gamestate()
                except Exception as e:
                    logger.error(f"Failed to refresh gamestate: {e}")
                    break
                continue

            logger.info(
                f"Booster pack screen detected ({state.state}, "
                f"{len(state.pack.cards)} cards). Automatically skipping..."
            )
            try:
                state = self.client.pack(skip=True)
            except BalatroAPIError as e:
                if e.data and isinstance(e.data, dict) and e.data.get("name") == "INVALID_STATE":
                    logger.warning(
                        f"Pack already closed (INVALID_STATE). Refreshing gamestate..."
                    )
                    try:
                        state = self.client.gamestate()
                    except Exception as inner_e:
                        logger.error(f"Failed to refresh gamestate: {inner_e}")
                        break
                else:
                    logger.error(f"Failed to skip booster pack: {e}")
                    break
            except Exception as e:
                logger.error(f"Failed to skip booster pack: {e}")
                break
        return state

    def _restart_balatro_process(self):
        import subprocess
        import sys
        import os
        import time
        from pathlib import Path

        logger.warning(f"[env:{self._env_id}] Killing and restarting Balatro instance on port {self._env_id}...")
        
        # 1. Kill existing process
        if sys.platform == "linux":
            # Kill all Wine processes in this isolated wine prefix
            prefix_dir = f"/dev/shm/wine_env_{self._env_id}"
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix_dir
            env["WINEDEBUG"] = "-all"
            logger.info(f"[env:{self._env_id}] Running wineserver -k for prefix {prefix_dir}")
            subprocess.run(["wineserver", "-k"], env=env, capture_output=True)
            # Also pkill any lingering Balatro.exe processes specifically associated with this prefix/port
            subprocess.run(["pkill", "-f", f"wine.*Balatro.exe.*{self._env_id}"], capture_output=True)
        elif sys.platform == "win32":
            subprocess.run(["taskkill", "/f", "/im", "Balatro.exe"], capture_output=True)
            
        time.sleep(1.0)
        
        # 2. Relaunch process
        # Find repo root and Balatro.exe
        repo_root = Path(__file__).resolve().parent.parent.parent
        balatro_exe = repo_root / "Balatro.v1.0.0i" / "Balatro.exe"
        if not balatro_exe.exists():
            logger.error(f"[env:{self._env_id}] Balatro.exe not found at {balatro_exe}")
            return
            
        # Reconstruct env
        env = os.environ.copy()
        env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        env["GALLIUM_DRIVER"] = "llvmpipe"
        
        # Prevent inheriting PyTorch's 1-thread limit
        for thread_env in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]:
            if thread_env in env:
                del env[thread_env]
                
        env["BALATROBOT_HOST"] = "127.0.0.1"
        env["BALATROBOT_PORT"] = str(self._env_id)
        env["BALATROBOT_FAST"] = "1"
        env["BALATROBOT_GAMESPEED"] = "10"
        env["BALATROBOT_ANIMATION_FPS"] = "60"
        env["BALATROBOT_FPS_CAP"] = "250"
        env["BALATROBOT_NO_SHADERS"] = "1"
        env["BALATROBOT_HEADLESS"] = "1"
        env["BALATROBOT_RENDER_ON_API"] = "0"
        
        if sys.platform == "linux":
            prefix_dir = f"/dev/shm/wine_env_{self._env_id}"
            env["WINEPREFIX"] = prefix_dir
            env["WINEDLLOVERRIDES"] = "version=n,b"
            env["WINEDEBUG"] = "-all"
            env["ALSOFT_DRIVERS"] = "null"
            env["SDL_AUDIODRIVER"] = "dummy"
            env["DISPLAY"] = ":99"
            cmd_launch = ["wine", str(balatro_exe)]
        else:
            cmd_launch = [str(balatro_exe)]
            
        logger.info(f"[env:{self._env_id}] Launching Balatro with command: {cmd_launch}")
        try:
            subprocess.Popen(
                cmd_launch,
                cwd=str(balatro_exe.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"[env:{self._env_id}] Relaunch command spawned successfully.")
        except Exception as launch_err:
            logger.error(f"[env:{self._env_id}] Failed to relaunch Balatro: {launch_err}")

    def _log_diagnostics(self):
        import os
        import sys
        from pathlib import Path
        
        # Resolve original_balatro_dir
        if sys.platform == "linux":
            wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
            
            def find_appdata(prefix_path):
                users_dir = Path(prefix_path) / "drive_c" / "users"
                if not users_dir.exists():
                    return None
                for p in users_dir.iterdir():
                    if p.is_dir() and p.name not in (".", ".."):
                        appdata_roaming = p / "AppData" / "Roaming" / "Balatro"
                        if appdata_roaming.exists():
                            return appdata_roaming
                        appdata_alt = p / "Application Data" / "Balatro"
                        if appdata_alt.exists():
                            return appdata_alt
                return None

            original_balatro_dir = find_appdata(wineprefix)
            if not original_balatro_dir:
                logger.error(f"[env:{self._env_id}] Diagnostic: original_balatro_dir not found in {wineprefix}")
                return

            logger.error(f"[env:{self._env_id}] --- DIAGNOSTIC LOG DUMP ON TIMEOUT/ERROR ---")
            
            # Read stdout log
            stdout_log = original_balatro_dir / f"instance_{self._env_id}_stdout.log"
            if stdout_log.exists():
                try:
                    with open(stdout_log, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    logger.error(f"[env:{self._env_id}] Last 10 lines of stdout:")
                    for l in lines[-10:]:
                        logger.error(f"  stdout: {l.strip()}")
                except Exception as e:
                    logger.error(f"[env:{self._env_id}] Failed to read stdout log: {e}")

            # Read stderr log
            stderr_log = original_balatro_dir / f"instance_{self._env_id}_stderr.log"
            if stderr_log.exists():
                try:
                    with open(stderr_log, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    logger.error(f"[env:{self._env_id}] Last 10 lines of stderr:")
                    for l in lines[-10:]:
                        logger.error(f"  stderr: {l.strip()}")
                except Exception as e:
                    logger.error(f"[env:{self._env_id}] Failed to read stderr log: {e}")

            # Read Lovely log
            wineprefix_dir = Path(f"/dev/shm/wine_env_{self._env_id}")
            temp_balatro_dir = find_appdata(wineprefix_dir)
            if temp_balatro_dir:
                lovely_log_dir = temp_balatro_dir / "Mods" / "lovely" / "log"
                if lovely_log_dir.exists():
                    log_files = list(lovely_log_dir.glob("lovely-*.log"))
                    if log_files:
                        newest_log = max(log_files, key=os.path.getmtime)
                        try:
                            with open(newest_log, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                            logger.error(f"[env:{self._env_id}] Last 80 lines of Lovely log ({newest_log.name}):")
                            for l in lines[-80:]:
                                logger.error(f"  lovely: {l.strip()}")
                        except Exception as e:
                            logger.error(f"[env:{self._env_id}] Failed to read Lovely log: {e}")

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> Tuple[Dict[str, np.ndarray], dict]:
        super().reset(seed=seed)
        self.invalid_actions_in_a_row = 0
        self._step_count = 0
        self._shop_actions_taken = 0
        self._consecutive_conn_errors = 0
        self._consecutive_timeout_errors = 0
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Resetting Balatro environment (attempt {attempt}/{max_attempts})...")
                state = self.client.gamestate(timeout=5.0)
                
                # If not in main menu, return to menu first to ensure a clean start
                if state.state != "MENU":
                    logger.info("Returning to menu to start fresh run...")
                    state = self.client.menu()
                
                # Verify we successfully made it to the menu
                if state.state != "MENU":
                    raise RuntimeError(f"Expected game state to be MENU, but got {state.state}")
                
                # Start a new run
                logger.info(f"Starting new run ({self.deck} deck, {self.stake} stake)...")
                state = self.client.start(deck=self.deck, stake=self.stake)
                
                # Handle any booster screens (if any auto-opens on startup, unlikely but safe)
                state = self._auto_skip_boosters(state)
                
                self.current_state = state
                obs = encode_observation(state)
                return obs, {}
                
            except Exception as e:
                logger.warning(f"Reset attempt {attempt} failed: {e}")
                if attempt == max_attempts:
                    logger.error("All reset attempts failed.")
                    raise e
                # Attempt to restart the Balatro process
                try:
                    self._restart_balatro_process()
                except Exception as restart_err:
                    logger.error(f"Failed to run restart routine: {restart_err}")
                time.sleep(5.0)

    def step(self, action: np.ndarray) -> Tuple[Dict[str, np.ndarray], float, bool, bool, dict]:
        if self.current_state is None:
            raise RuntimeError("Environment must be reset before step can be called.")

        self._step_count += 1
        t_start = time.monotonic()

        state = self.current_state
        action_dict, is_valid = decode_action(action, state)
        action_type = action_dict.get("action", "wait")
        
        logger.debug(
            f"[env:{self._env_id}] step {self._step_count}: "
            f"state={state.state}, action={action_type}"
        )
        
        reward = 0.0
        terminated = False
        truncated = False
        
        if not is_valid:
            self.invalid_actions_in_a_row += 1
            reward = -0.1
            new_state = state
            logger.warning(f"Invalid action chosen: {action} (interpreted as {action_dict}) in state {state.state}")
            
            if self.invalid_actions_in_a_row >= self.max_invalid_actions:
                logger.warning(f"Too many invalid actions in a row ({self.invalid_actions_in_a_row}). Truncating episode.")
                truncated = True
                reward = -5.0  # Same penalty as GAME OVER (loss) to prevent exploit
        else:
            self.invalid_actions_in_a_row = 0
            
            # Track shop actions to prevent infinite loops
            if state.state == "SHOP" and action_type != "next_round":
                self._shop_actions_taken += 1
                if self._shop_actions_taken >= MAX_SHOP_ACTIONS:
                    logger.info(f"Shop action limit reached ({MAX_SHOP_ACTIONS}). Forcing next_round.")
                    action_type = "next_round"
                    action_dict = {"action": "next_round"}
            
            # Reset shop counter when leaving shop
            if action_type == "next_round" and state.state == "SHOP":
                self._shop_actions_taken = 0
            
            try:
                new_state = self._execute_action(action_type, action_dict, state)
                # Successful API call: reset dead-instance counters
                self._consecutive_conn_errors = 0
                self._consecutive_timeout_errors = 0
            except BalatroAPIError as e:
                logger.error(f"API Error during step execution: {e}. Attempting to recover state...")
                reward = -0.5
                try:
                    new_state = self.client.gamestate(timeout=3.0)
                    logger.info(f"State successfully recovered. New state: {new_state.state}")
                    self._consecutive_conn_errors = 0
                    self._consecutive_timeout_errors = 0
                except Exception as recovery_err:
                    logger.error(f"Failed to recover state: {recovery_err}")
                    new_state = state
            except Exception as e:
                logger.error(f"Unexpected connection error during step execution: {e}. Attempting to recover state...")
                
                # Log diagnostic logs immediately to pinpoint the cause
                try:
                    self._log_diagnostics()
                except Exception as diag_err:
                    logger.error(f"Failed to run diagnostic logger: {diag_err}")
                    
                reward = -0.5
                err_str = str(e).lower()
                is_conn_refused = "connection refused" in err_str or "errno 111" in err_str
                is_timeout = "timed out" in err_str or "timeout" in err_str
                
                if is_conn_refused:
                    self._consecutive_conn_errors += 1
                    self._consecutive_timeout_errors = 0
                    logger.error(
                        f"[env:{self._env_id}] Connection refused "
                        f"({self._consecutive_conn_errors}/{MAX_DEAD_STEPS}). "
                        f"Instance may be dead."
                    )
                    if self._consecutive_conn_errors >= MAX_DEAD_STEPS:
                        logger.error(
                            f"[env:{self._env_id}] Instance declared DEAD after "
                            f"{MAX_DEAD_STEPS} consecutive connection refusals. "
                            f"Truncating episode to unblock training."
                        )
                        self.current_state = state  # keep last known state
                        obs = encode_observation(state)
                        info = {
                            "episode_metrics": {
                                "won": False,
                                "ante": int(state.ante_num),
                                "round": int(state.round_num),
                                "money": float(state.money),
                                "chips": float(state.round.chips) if state.round else 0.0,
                            }
                        }
                        return obs, -5.0, False, True, info
                    new_state = state
                elif is_timeout:
                    self._consecutive_timeout_errors += 1
                    self._consecutive_conn_errors = 0
                    logger.error(
                        f"[env:{self._env_id}] Timeout error during execution "
                        f"({self._consecutive_timeout_errors}/{MAX_TIMEOUT_STEPS})."
                    )
                    if self._consecutive_timeout_errors >= MAX_TIMEOUT_STEPS:
                        logger.error(
                            f"[env:{self._env_id}] Instance declared DEAD after "
                            f"{MAX_TIMEOUT_STEPS} consecutive timeouts. "
                            f"Truncating episode to unblock training."
                        )
                        self.current_state = state  # keep last known state
                        obs = encode_observation(state)
                        info = {
                            "episode_metrics": {
                                "won": False,
                                "ante": int(state.ante_num),
                                "round": int(state.round_num),
                                "money": float(state.money),
                                "chips": float(state.round.chips) if state.round else 0.0,
                            }
                        }
                        return obs, -5.0, False, True, info
                    
                    try:
                        new_state = self.client.gamestate(timeout=3.0)
                        if action_type == "cash_out" and new_state.state == "ROUND_EVAL":
                            logger.error(
                                f"[env:{self._env_id}] Stuck in ROUND_EVAL after cash_out timeout. "
                                f"Forcing menu() escape to unblock instance..."
                            )
                            try:
                                new_state = self.client.menu()
                                logger.info(f"[env:{self._env_id}] Menu escape successful. New state: {new_state.state}")
                            except Exception as menu_err:
                                logger.error(f"[env:{self._env_id}] Menu escape also failed: {menu_err}")
                        else:
                            logger.info(f"State successfully recovered after timeout error. New state: {new_state.state}")
                    except Exception as recovery_err:
                        logger.error(f"Failed to recover state: {recovery_err}")
                        new_state = state
                else:
                    self._consecutive_conn_errors = 0
                    self._consecutive_timeout_errors = 0
                    try:
                        new_state = self.client.gamestate(timeout=3.0)
                        if action_type == "cash_out" and new_state.state == "ROUND_EVAL":
                            logger.error(
                                f"[env:{self._env_id}] Stuck in ROUND_EVAL after cash_out timeout. "
                                f"Forcing menu() escape to unblock instance..."
                            )
                            try:
                                new_state = self.client.menu()
                                logger.info(f"[env:{self._env_id}] Menu escape successful. New state: {new_state.state}")
                            except Exception as menu_err:
                                logger.error(f"[env:{self._env_id}] Menu escape also failed: {menu_err}")
                        else:
                            logger.info(f"State successfully recovered after connection error. New state: {new_state.state}")
                    except Exception as recovery_err:
                        logger.error(f"Failed to recover state: {recovery_err}")
                        new_state = state
                
            # Post-action processing: auto-skip boosters ONLY as fallback
            # (not after buy_pack or pack actions, where the agent drives interaction)
            if action_type not in ("buy_pack", "pack_select", "pack_skip"):
                new_state = self._auto_skip_boosters(new_state)
            
            # Calculate reward
            reward = self._calculate_reward(state, new_state)
            
            dt = time.monotonic() - t_start
            if dt > 3.0:
                logger.warning(
                    f"[env:{self._env_id}] step {self._step_count} slow: "
                    f"{action_type} took {dt:.1f}s (state: {state.state} -> {new_state.state})"
                )
            
        # Update current state
        self.current_state = new_state
        obs = encode_observation(new_state)
        
        info = {}
        if new_state.state == "GAME_OVER":
            terminated = True
            
        if terminated or truncated:
            info["episode_metrics"] = {
                "won": bool(new_state.won) if new_state.won is not None else False,
                "ante": int(new_state.ante_num),
                "round": int(new_state.round_num),
                "money": float(new_state.money),
                "chips": float(new_state.round.chips) if new_state.round else 0.0,
            }
            
        return obs, reward, terminated, truncated, info

    def _execute_action(self, action_type: str, action_dict: dict, state: GameState) -> GameState:
        """Execute a decoded action against the Balatro API and return the new state."""
        if action_type == "play":
            return self.client.play(action_dict["cards"])
        elif action_type == "discard":
            return self.client.discard(action_dict["cards"])
        elif action_type == "select_blind":
            return self.client.select()
        elif action_type == "skip_blind":
            return self.client.skip()
        elif action_type == "cash_out":
            return self.client.cash_out()
        elif action_type == "next_round":
            return self.client.next_round()
        elif action_type == "start_game":
            return self.client.start(deck=self.deck, stake=self.stake)
        elif action_type == "menu":
            return self.client.menu()
        # Phase 2: Shop actions
        elif action_type == "buy_card":
            return self.client.buy(card=action_dict["index"])
        elif action_type == "buy_voucher":
            return self.client.buy(voucher=action_dict["index"])
        elif action_type == "buy_pack":
            return self.client.buy(pack=action_dict["index"])
        elif action_type == "reroll":
            return self.client.reroll()
        elif action_type == "sell_joker":
            return self.client.sell(joker=action_dict["index"])
        # Phase 2: Booster pack actions
        elif action_type == "pack_select":
            return self.client.pack(card=action_dict.get("index", 0), targets=action_dict.get("targets"))
        elif action_type == "pack_skip":
            return self.client.pack(skip=True)
        else:
            return state

    def _calculate_reward(self, old_state: GameState, new_state: GameState) -> float:
        reward = 0.0
        
        # 1. Round outcome transitions (Blind won)
        if old_state.state == "SELECTING_HAND" and new_state.state == "ROUND_EVAL":
            reward += 1.0
            
        # 2. Score progression (Reward for playing cards that increase score)
        if old_state.state == "SELECTING_HAND" and new_state.state in ("SELECTING_HAND", "ROUND_EVAL"):
            target_score = 0
            for blind in old_state.blinds.values():
                if blind.status == "CURRENT":
                    target_score = blind.score
                    break
            
            if target_score > 0:
                score_diff = new_state.round.chips - old_state.round.chips
                if score_diff > 0:
                    ratio = float(score_diff) / target_score
                    # Quadratic reward to heavily incentivize higher scoring hands (e.g. 300 chips in 1 hand vs 100+100+100)
                    reward += ratio + 2.0 * (ratio ** 2)
                
        # 3. Ante progression (Defeating Boss Blind of current Ante)
        if int(new_state.ante_num) > int(old_state.ante_num):
            reward += 5.0 * (int(new_state.ante_num) - int(old_state.ante_num))
            logger.info(f"Ante increased from {old_state.ante_num} to {new_state.ante_num}! +5.0 Reward.")

        # 4. Money change — (Disabled for Phase 1)
        # money_delta = float(new_state.money) - float(old_state.money)
        # reward += 0.05 * money_delta

        # 5. Interest threshold bonus
        if (old_state.state in ("ROUND_EVAL", "SELECTING_HAND") and 
            new_state.state in ("SHOP", "BLIND_SELECT")):
            interest = min(int(new_state.money) // 5, 5)
            if interest > 0:
                reward += 0.3 * interest  # max +1.5 for maintaining $25+
        
        # 6. Joker acquisition
        old_joker_count = len(old_state.jokers.cards) if old_state.jokers else 0
        new_joker_count = len(new_state.jokers.cards) if new_state.jokers else 0
        if new_joker_count > old_joker_count:
            reward += 0.5 * (new_joker_count - old_joker_count)
            logger.debug(f"Joker acquired! {old_joker_count} -> {new_joker_count}")

        # 7. Game end conditions
        if new_state.state == "GAME_OVER":
            if new_state.won:
                reward += 10.0
                logger.info("RUN WON! Large reward given.")
            else:
                reward -= 5.0
                logger.info("GAME OVER (RUN LOST). Penalty given.")
                
        return reward
