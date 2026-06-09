from typing import List
import logging
from src.bots.base_bot import BaseBot
from src.game_state import GameState, Card
from src.hand_evaluator import get_best_play_decision

logger = logging.getLogger("HeuristicBot")

class HeuristicBot(BaseBot):
    def decide(self, game_state: GameState) -> dict:
        state_name = game_state.state

        if state_name == "MENU":
            return {"action": "start_game", "deck": "RED", "stake": "WHITE"}
            
        elif state_name == "BLIND_SELECT":
            # For the heuristic bot, we always select the current blind (no skip)
            return {"action": "select_blind"}
            
        elif state_name == "ROUND_EVAL":
            return {"action": "cash_out"}
            
        elif state_name == "SHOP":
            # Baseline just skips the shop and goes to the next round
            return {"action": "next_round"}
            
        elif state_name == "GAME_OVER":
            return {"action": "menu"}
            
        elif state_name in {"SMODS_BOOSTER_OPENED", "TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK", "BUFFOON_PACK"}:
            # Skip any opened booster packs
            return {"action": "pack", "skip": True}
            
        elif state_name == "SELECTING_HAND":
            if not game_state.hand or not game_state.hand.cards:
                return {"action": "wait"}
                
            hand_cards = game_state.hand.cards
            
            # Find best hand to play
            play_indices, hand_type, estimated_score = get_best_play_decision(hand_cards, game_state)
            
            # Determine blind target score
            target_score = 0
            for blind in game_state.blinds.values():
                if blind.status == "CURRENT":
                    target_score = blind.score
                    break
            
            remaining_score = max(0, target_score - game_state.round.chips)
            
            logger.info(f"Best hand: {hand_type} | Est. Score: {estimated_score} | Target: {target_score} (Remaining: {remaining_score}) | Hands left: {game_state.round.hands_left} | Discards left: {game_state.round.discards_left}")
            
            # If the best hand score is enough to beat the blind, play it immediately!
            if estimated_score >= remaining_score:
                logger.info(f"Estimated score {estimated_score} beats remaining target {remaining_score}. Playing hand.")
                return {"action": "play", "cards": play_indices}
                
            # If we have discards left, let's try to improve our hand
            if game_state.round.discards_left > 0:
                discard_indices = self.get_discard_decision(hand_cards)
                if discard_indices:
                    logger.info(f"Hand score {estimated_score} doesn't beat {remaining_score}. Discarding indices: {discard_indices}")
                    return {"action": "discard", "cards": discard_indices}
                    
            # If we have no discards left or decide not to discard, play our best hand
            if play_indices:
                logger.info("No discards left. Playing best available hand.")
                return {"action": "play", "cards": play_indices}
            else:
                # Fallback: play the first card
                logger.info("No play indices found. Playing first card as fallback.")
                return {"action": "play", "cards": [0]}
                
        return {"action": "wait"}

    def get_discard_decision(self, hand_cards: List[Card]) -> List[int]:
        """
        Heuristic to choose cards to discard (up to 5 cards).
        """
        # 1. Flush Hunt: Check if we have 3 or 4 cards of the same suit
        suit_counts = {}
        for c in hand_cards:
            if c.state.debuff:
                continue
            suit = c.value.suit
            if suit:
                suit_counts[suit] = suit_counts.get(suit, 0) + 1
                
        dominant_suit = None
        for suit, count in suit_counts.items():
            if count >= 3:
                dominant_suit = suit
                break
                
        if dominant_suit:
            # Keep all cards of dominant suit (and wild cards). Discard other suits.
            discard_indices = []
            for i, c in enumerate(hand_cards):
                # Don't discard wild cards or dominant suit cards
                is_wild = c.modifier.enhancement == "WILD" and not c.state.debuff
                if c.value.suit != dominant_suit and not is_wild:
                    discard_indices.append(i)
            if discard_indices:
                return discard_indices[:5]
                
        # 2. Pairs/Trips Hunt: Keep duplicates, discard singles of lowest ranks
        rank_counts = {}
        for c in hand_cards:
            rank = c.value.rank
            if rank:
                rank_counts[rank] = rank_counts.get(rank, 0) + 1
                
        # Determine which ranks are singles (count == 1)
        single_ranks = {r for r, count in rank_counts.items() if count == 1}
        
        # If we have singles, discard them starting from lowest rank
        # Rank ordering values
        rank_values = {
            '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
            'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
        }
        
        discard_candidates = []
        for i, c in enumerate(hand_cards):
            rank = c.value.rank
            if rank in single_ranks:
                val = rank_values.get(rank, 0)
                discard_candidates.append((i, val))
                
        if discard_candidates:
            # Sort by rank value ascending (lowest first)
            discard_candidates.sort(key=lambda x: x[1])
            return [x[0] for x in discard_candidates[:5]]
            
        # 3. Fallback: discard the 5 lowest cards
        rank_values = {
            '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
            'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
        }
        candidates = []
        for i, c in enumerate(hand_cards):
            rank = c.value.rank
            val = rank_values.get(rank, 0) if rank else 0
            candidates.append((i, val))
            
        candidates.sort(key=lambda x: x[1])
        return [x[0] for x in candidates[:5]]
