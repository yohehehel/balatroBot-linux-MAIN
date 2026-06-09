import os
import sys
import argparse
import logging
import numpy as np
import torch

# Limit PyTorch CPU threads to avoid CPU thrashing on high-core VMs
torch.set_num_threads(4)
torch.set_num_interop_threads(4)

from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor

from src.env.balatro_env import BalatroEnv
from src.bots.heuristic_bot import HeuristicBot

def api_to_gym_action(api_decision, game_state) -> np.ndarray:
    """
    Maps a heuristic bot's dictionary-based API decision back into the Gymnasium
    MultiDiscrete action format [action_type, c0, c1, c2, c3, c4, c5, c6, c7].
    """
    action_type_map = {
        "play": 0,
        "discard": 1,
        "select_blind": 2,
        "skip_blind": 3,
        "cash_out": 4,
        "next_round": 5,
        "buy_card": 6,
        "buy_voucher": 7,
        "buy_pack": 8,
        "reroll": 9,
        "sell_joker": 10,
        "pack_select": 11,
        "pack_skip": 12,
        "menu": 4,         # GAME_OVER -> returns to menu (action 4)
        "start_game": 5,   # MENU -> starts game (action 5)
    }
    
    action = np.zeros(9, dtype=np.int64)
    action[0] = action_type_map.get(api_decision.get("action"), 0)
    
    if api_decision.get("action") in ["play", "discard"] and "cards" in api_decision:
        for idx in api_decision["cards"]:
            if idx < 8:
                action[idx + 1] = 1
                
    return action

def main():
    parser = argparse.ArgumentParser(description="Evaluate a Balatro Bot (PPO or Heuristic).")
    parser.add_argument("--model-path", type=str, default=None, help="Path to the PPO model checkpoint (.zip). If omitted, evaluates Heuristic Bot.")
    parser.add_argument("--api-url", type=str, default="http://127.0.0.1:12346", help="Balatro JSON-RPC API URL.")
    parser.add_argument("--episodes", type=int, default=10, help="Number of episodes to evaluate.")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("EvaluateBot")

    logger.info("Initializing Balatro Environment for evaluation...")
    try:
        env = BalatroEnv(base_url=args.api_url)
        # Verify connectivity
        health = env.client.health()
        logger.info(f"API Health check: {health}")
    except Exception as e:
        logger.error("Could not connect to Balatro JSON-RPC API. Ensure Balatro is running with the mod loaded!")
        logger.error(str(e))
        sys.exit(1)

    model = None
    heuristic_bot = None

    if args.model_path:
        logger.info(f"Loading trained PPO model from {args.model_path}...")
        try:
            model = PPO.load(args.model_path)
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load PPO model: {e}")
            sys.exit(1)
    else:
        logger.info("No model path provided. Evaluating the HEURISTIC BOT baseline...")
        heuristic_bot = HeuristicBot(env.client)

    # Track metrics
    wons = []
    max_antes = []
    final_moneys = []
    total_rounds = []
    episode_rewards = []

    for ep in range(args.episodes):
        logger.info(f"Starting Episode {ep + 1}/{args.episodes}...")
        obs, info = env.reset()
        done = False
        ep_reward = 0.0
        
        while not done:
            if model is not None:
                # Use trained agent to select action
                action, _ = model.predict(obs, deterministic=True)
            else:
                # Use heuristic bot to select action
                decision = heuristic_bot.decide(env.current_state)
                action = api_to_gym_action(decision, env.current_state)

            obs, reward, terminated, truncated, info = env.step(action)
            ep_reward += reward
            done = terminated or truncated

        # Extract episode metrics from end-of-episode info
        metrics = info.get("episode_metrics", {})
        won = metrics.get("won", False)
        ante = metrics.get("ante", 1)
        round_num = metrics.get("round", 0)
        money = metrics.get("money", 0.0)

        wons.append(won)
        max_antes.append(ante)
        final_moneys.append(money)
        total_rounds.append(round_num)
        episode_rewards.append(ep_reward)

        logger.info(
            f"Episode {ep + 1} finished | Won: {won} | Max Ante: {ante} | "
            f"Rounds: {round_num} | Final Money: {money} | Reward: {ep_reward:.2f}"
        )

    # Print final summary statistics
    logger.info("=== EVALUATION REPORT ===")
    logger.info(f"Bot Type: {'PPO Model' if args.model_path else 'Heuristic Bot'}")
    logger.info(f"Episodes Played: {args.episodes}")
    logger.info(f"Win Rate: {np.mean(wons) * 100:.1f}% ({sum(wons)}/{args.episodes})")
    logger.info(f"Average Max Ante: {np.mean(max_antes):.2f} (Max: {np.max(max_antes)}, Min: {np.min(max_antes)})")
    logger.info(f"Average Final Money: ${np.mean(final_moneys):.2f}")
    logger.info(f"Average Rounds Played: {np.mean(total_rounds):.2f}")
    logger.info(f"Average Cumulative Reward: {np.mean(episode_rewards):.2f}")
    logger.info("=========================")

if __name__ == "__main__":
    main()
