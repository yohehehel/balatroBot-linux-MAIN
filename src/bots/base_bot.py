import time
import logging
from src.client import BalatroClient
from src.game_state import GameState

logger = logging.getLogger("BaseBot")

class BaseBot:
    def __init__(self, client: BalatroClient):
        self.client = client
        self.running = False

    def decide(self, game_state: GameState) -> dict:
        """
        Evaluate the game state and return a dictionary representing the action to take.
        Returns:
            dict: {"action": "play", "cards": [...]}
                  {"action": "discard", "cards": [...]}
                  {"action": "select_blind"}
                  {"action": "skip_blind"}
                  {"action": "cash_out"}
                  {"action": "next_round"}
                  {"action": "start_game", "deck": "RED", "stake": "WHITE"}
                  {"action": "menu"}
                  {"action": "wait"}
        """
        raise NotImplementedError()

    def step(self) -> GameState:
        # Get current state
        state = self.client.gamestate()
        # Decide action
        action_dict = self.decide(state)
        action = action_dict.get("action", "wait")
        
        logger.info(f"State: {state.state} | Money: ${state.money} | Ante: {state.ante_num} | Action: {action_dict}")
        
        if action == "play":
            return self.client.play(action_dict["cards"])
        elif action == "discard":
            return self.client.discard(action_dict["cards"])
        elif action == "select_blind":
            return self.client.select()
        elif action == "skip_blind":
            return self.client.skip()
        elif action == "cash_out":
            return self.client.cash_out()
        elif action == "next_round":
            return self.client.next_round()
        elif action == "start_game":
            return self.client.start(
                deck=action_dict.get("deck", "RED"),
                stake=action_dict.get("stake", "WHITE")
            )
        elif action == "pack":
            return self.client.pack(
                card=action_dict.get("card"),
                targets=action_dict.get("targets"),
                skip=action_dict.get("skip")
            )
        elif action == "menu":
            return self.client.menu()
        elif action == "wait":
            time.sleep(0.5)
            return state
        else:
            raise ValueError(f"Unknown action: {action}")

    def run(self, delay: float = 0.5):
        self.running = True
        logger.info("Starting bot execution loop...")
        while self.running:
            try:
                self.step()
                if delay > 0:
                    time.sleep(delay)
            except KeyboardInterrupt:
                logger.info("Stopping bot execution loop...")
                self.running = False
            except Exception as e:
                logger.error(f"Error in bot execution loop: {e}", exc_info=True)
                time.sleep(2.0)
