#!/usr/bin/env python
import logging
import sys
import time
from src.client import BalatroClient
from src.bots.heuristic_bot import HeuristicBot

def main():
    # Setup logging to stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger("run_demo")
    logger.info("Initializing Balatro Heuristic Bot Demo...")
    
    client = BalatroClient()
    
    # 1. Health check
    try:
        health = client.health()
        logger.info(f"API Health Check: {health}")
    except Exception as e:
        logger.error("Could not connect to BalatroBot API. Is the game running and the mod loaded?")
        sys.exit(1)
        
    bot = HeuristicBot(client)
    
    logger.info("Running Heuristic Bot. Press Ctrl+C to stop.")
    try:
        bot.run(delay=0.5)
    except KeyboardInterrupt:
        logger.info("Demo stopped by user.")

if __name__ == "__main__":
    main()
