# Walkthrough: Phase 1 Strategic Pivot

This document summarizes the changes applied to pivot `balatroBot` back to Phase 1 (Core Poker) training with architectural upgrades and enhanced feature representation.

## Changes Made

### 1. Network Architecture
- **[config.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/training/config.py)**: Added the `policy_kwargs` configuration block to configure a 2x512 MLP architecture (for actor `pi` and critic `vf`) instead of the default 2x64 layout. Passed it through `to_ppo_kwargs()`.
- **[train.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/training/train.py)**: Unpacks the extended `ppo_kwargs` containing `policy_kwargs` to dynamically configure the PPO policy model.

### 2. Strategic Pivot to Phase 1
- **[action.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/env/action.py)**: Reduced the action space to size 6 (containing only play, discard, select_blind, skip_blind, cash_out, next_round). When in the `SHOP` state, it unconditionally returns `next_round`. When in `BOOSTER_STATES`, it unconditionally returns `pack_skip`.
- **[balatro_env.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/env/balatro_env.py)**: Commented out money delta, interest threshold bonus, and joker acquisition rewards from `_calculate_reward()`.

### 3. Spatial Stability & Hand Sorting
- **[observation.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/env/observation.py)**: Implemented `get_card_sort_key` to sort hand cards by rank descending, and then by suit. Hand cards are now sorted before they are encoded in the observation.
- **[action.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/env/action.py)**: Updated `decode_action` to sort hand cards using the same logic and map the agent's action index back to the card's original index in `GameState`.

### 4. Hand Evaluation Feature Engineering
- **[observation.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/src/env/observation.py)**: Implemented `get_hand_flags` using helpers from `hand_evaluator.py` to check for `is_pair`, `is_two_pair`, `is_three_of_a_kind`, `is_straight`, `is_flush`, `is_full_house`, `is_four_of_a_kind`, and `is_straight_flush`. Extended `game_info` array size from 15 to 23 and appended these flags.

### 5. Running on Headless Linux Environment
- **[run_training.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/run_training.py)**: Reverted the execution command from `wine64` back to the standard `wine` wrapper to fix `FileNotFoundError` on environments where `wine64` is not directly exposed on PATH.

## Testing & Validation Results

We executed the smoke tests in `tests/test_phase2.py` with Python 3.12:

```bash
$env:PYTHONUTF8=1; $env:PYTHONPATH="."; py -3.12 tests/test_phase2.py
```

### Output
```text
✓ Action space correct
✓ Observation space keys correct
✓ Shop buy_card (force next_round) correct
✓ Shop buy_card fallback (force next_round) correct
✓ Shop reroll (force next_round) correct
✓ Shop sell_joker (force next_round) correct
✓ Shop next_round decode correct
✓ Booster pack_select (force pack_skip) correct
✓ Booster pack_skip decode correct
✓ Phase 1 actions unchanged
✓ Observation encoding with shop data correct
✓ Hand sorting and flags correct

🎉 All Phase 2 smoke tests passed!
```
All assertions verified:
- Correct action space size of 6.
- Correct observation vector dimensions (23 for `game_info`).
- Correct automatic skip transitions in shops and packs.
- Stable, deterministic spatial sorting of cards by rank and suit.
- Accurate feature extraction for hand types (e.g. detecting a pair of 2s).

## Diagnostic & Investigation System

We have implemented an automated diagnostic check suite and detailed error logging to locate the exact cause of any timeouts, sluggishness, or potential graphics/physics crashes.

### 1. Changes Implemented
- **[setup_mods.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/scripts/setup_mods.py)**: Injected `[DIAGNOSTIC]` log print statements inside the LUA mod patches for `Moveable.move_xy` (easing physics bypass) and `EventManager.update` (10x delta speed multiplier). These prints execute once and confirm that the speed hacks are active in the running game.
- **[run_training.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/run_training.py)**: Refactored the log-dump function into a helper `dump_instance_logs()`. Modified the main training loop wrapper so that if training is interrupted (`KeyboardInterrupt`) or crashes (`Exception`), the last 40 lines of standard output, standard error, and the newest `lovely` logs for all active ports are instantly printed to the terminal.
- **[diagnose.py](file:///c:/Users/yrfr137478/Downloads/balatroBot-linux/balatroBot-linux-MAIN/scripts/diagnose.py)**: Added a new dedicated diagnostics command-line utility to run system health checks, test path integrity, launch a debug instance on port 12350, run end-to-end API test transactions (health, start, select, play) measuring response latency, and output a detailed analysis of the Lovely and system log files.
- **[WINEDLLOVERRIDES Reversion]**: Reverted `WINEDLLOVERRIDES` back to `"version=n,b"` across `run_training.py`, `scripts/diagnose.py`, and `scripts/launch_balatro_multiple.py`. Previously, overriding audio-related DLLs (`mmdevapi` and `dsound`) in the headless Wine container caused the Love2D/OpenAL dependency resolution to trigger a hard loader crash (Exit Code 9 / SIGKILL).


### 2. Instructions to Run Diagnosis on the VM
To execute the diagnosis on the remote VM, run:
```bash
git pull origin main
rm -rf /tmp/wine_master /tmp/wine_diag
python scripts/setup_mods.py
python scripts/diagnose.py
```
This will output a detailed diagnostic report in the terminal.
