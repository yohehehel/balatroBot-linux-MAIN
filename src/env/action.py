import numpy as np
from gymnasium import spaces
from typing import Dict, Any, Tuple, List
from src.game_state import GameState
from src.env.observation import get_card_sort_key

# Action Types:
# 0: PLAY_HAND
# 1: DISCARD
# 2: SELECT_BLIND
# 3: SKIP_BLIND
# 4: CASH_OUT
# 5: NEXT_ROUND
# --- Phase 2: Shop & Booster actions ---
# 6: BUY_CARD       (buy shop card at index from card_mask)
# 7: BUY_VOUCHER    (buy voucher at index from card_mask)
# 8: BUY_PACK       (buy pack at index from card_mask)
# 9: REROLL_SHOP    (reroll shop items)
# 10: SELL_JOKER    (sell joker at index from card_mask)
# 11: PACK_SELECT   (select card from opened booster pack)
# 12: PACK_SKIP     (skip opened booster pack)

BOOSTER_STATES = {
    "SMODS_BOOSTER_OPENED",
    "TAROT_PACK",
    "PLANET_PACK",
    "SPECTRAL_PACK",
    "STANDARD_PACK",
    "BUFFOON_PACK",
}

def get_action_space() -> spaces.MultiDiscrete:
    # 9 discrete dimensions:
    # Dim 0: action type (0-5 Phase 1 + 6-12 Phase 2 shop/booster)
    # Dim 1 to 8: binary selection of cards (0: off, 1: on)
    return spaces.MultiDiscrete([13, 2, 2, 2, 2, 2, 2, 2, 2])


def _first_set_bit(card_mask: np.ndarray, max_idx: int = 7) -> int:
    """Return the index of the first set bit in card_mask, clamped to max_idx.
    Returns 0 if no bit is set.
    """
    for i in range(min(len(card_mask), max_idx + 1)):
        if card_mask[i] == 1:
            return i
    return 0


def decode_action(action: np.ndarray, game_state: GameState) -> Tuple[dict, bool]:
    """
    Decodes a Gymnasium action into a dictionary describing the API call.
    Automatically projects/corrects invalid actions into valid ones to prevent agent penalties.
    Always returns True for is_valid.
    """
    action_type = action[0]
    card_mask = action[1:]
    
    state_name = game_state.state
    
    # 1. BLIND_SELECT State
    if state_name == "BLIND_SELECT":
        # Force either select_blind (2) or skip_blind (3). Default to select_blind.
        if action_type in [2, 3]:
            chosen_action = "select_blind" if action_type == 2 else "skip_blind"
        else:
            chosen_action = "select_blind"
            
        # Bugfix: Boss blind cannot be skipped. If the Boss blind is selectable, force select_blind.
        is_boss_selectable = False
        if game_state.blinds:
            for blind in game_state.blinds.values():
                if blind.type == "BOSS" and blind.status in ["SELECT", "CURRENT"]:
                    is_boss_selectable = True
                    break
        if is_boss_selectable and chosen_action == "skip_blind":
            chosen_action = "select_blind"
            
        return {"action": chosen_action}, True
            
    # 2. SELECTING_HAND State
    elif state_name == "SELECTING_HAND":
        if not game_state.hand or not game_state.hand.cards:
            return {"action": "wait"}, True
            
        # Sort cards with their original indices to ensure spatial consistency
        sorted_cards_with_indices = sorted(
            enumerate(game_state.hand.cards),
            key=lambda x: get_card_sort_key(x[1])
        )
        
        hand_size = len(game_state.hand.cards)
        # Select cards based on mask, limited to the actual hand size
        # Note: card_mask[i] refers to the i-th card in sorted order.
        selected_original_indices = [
            orig_idx for i, (orig_idx, card) in enumerate(sorted_cards_with_indices[:8])
            if card_mask[i] == 1
        ]
        
        # Auto-correct selected cards to be between 1 and 5 cards
        if len(selected_original_indices) == 0:
            selected_original_indices = [sorted_cards_with_indices[0][0]]  # Default to the first card in the sorted hand
        elif len(selected_original_indices) > 5:
            selected_original_indices = selected_original_indices[:5]  # Truncate to first 5 cards
            
        # Determine the action type: play (0) or discard (1).
        # Map any other value to 0 or 1.
        if action_type not in [0, 1]:
            action_type = action_type % 2
            
        # If discard is chosen but no discards are left, force play (0)
        if action_type == 1 and game_state.round.discards_left <= 0:
            action_type = 0
            
        if action_type == 0:
            return {"action": "play", "cards": selected_original_indices}, True
        else:
            return {"action": "discard", "cards": selected_original_indices}, True
            
    # 3. ROUND_EVAL State
    elif state_name == "ROUND_EVAL":
        return {"action": "cash_out"}, True
    
    # 4. SHOP State — Agent-driven (Phase 2)
    elif state_name == "SHOP":
        return _decode_shop_action(action_type, card_mask, game_state)
    
    # 5. BOOSTER PACK States — Agent-driven (Phase 2)
    elif state_name in BOOSTER_STATES:
        return _decode_booster_action(action_type, card_mask, game_state)
            
    # 6. Other / Menu / Game Over
    elif state_name == "MENU" or state_name == "GAME_OVER":
        if state_name == "MENU":
            return {"action": "start_game", "deck": "RED", "stake": "WHITE"}, True
        elif state_name == "GAME_OVER":
            return {"action": "menu"}, True
            
    return {"action": "wait"}, True


def _decode_shop_action(action_type: int, card_mask: np.ndarray, game_state: GameState) -> Tuple[dict, bool]:
    """Decode actions when in SHOP state.
    
    Valid action types: 6 (buy card), 7 (buy voucher), 8 (buy pack),
    9 (reroll), 10 (sell joker), 5 (next_round).
    All other types default to next_round.
    """
    money = float(game_state.money)
    
    if action_type == 6:  # BUY_CARD
        idx = _first_set_bit(card_mask, max_idx=1)  # shop has max ~2 cards
        if game_state.shop and game_state.shop.cards and idx < len(game_state.shop.cards):
            card = game_state.shop.cards[idx]
            buy_cost = card.cost.buy
            if money >= buy_cost:
                # Check slot limits for Jokers and Consumables
                if card.set == "JOKER":
                    current_jokers = len(game_state.jokers.cards) if game_state.jokers else 0
                    joker_limit = game_state.jokers.limit if game_state.jokers else 5
                    if current_jokers >= joker_limit:
                        return {"action": "next_round"}, True
                elif card.set in ("TAROT", "PLANET", "SPECTRAL"):
                    current_consumables = len(game_state.consumables.cards) if game_state.consumables else 0
                    consumable_limit = game_state.consumables.limit if game_state.consumables else 2
                    if current_consumables >= consumable_limit:
                        return {"action": "next_round"}, True
                return {"action": "buy_card", "index": idx}, True
        return {"action": "next_round"}, True
    
    elif action_type == 7:  # BUY_VOUCHER
        idx = _first_set_bit(card_mask, max_idx=1)
        if game_state.vouchers and game_state.vouchers.cards and idx < len(game_state.vouchers.cards):
            buy_cost = game_state.vouchers.cards[idx].cost.buy
            if money >= buy_cost:
                return {"action": "buy_voucher", "index": idx}, True
        return {"action": "next_round"}, True
    
    elif action_type == 8:  # BUY_PACK
        idx = _first_set_bit(card_mask, max_idx=1)
        if game_state.packs and game_state.packs.cards and idx < len(game_state.packs.cards):
            buy_cost = game_state.packs.cards[idx].cost.buy
            if money >= buy_cost:
                return {"action": "buy_pack", "index": idx}, True
        return {"action": "next_round"}, True
    
    elif action_type == 9:  # REROLL
        reroll_cost = game_state.round.reroll_cost
        if money >= reroll_cost:
            return {"action": "reroll"}, True
        return {"action": "next_round"}, True
    
    elif action_type == 10:  # SELL_JOKER
        idx = _first_set_bit(card_mask, max_idx=4)  # max 5 joker slots
        if game_state.jokers and game_state.jokers.cards and idx < len(game_state.jokers.cards):
            # Don't sell eternal jokers
            joker = game_state.jokers.cards[idx]
            if not joker.modifier.eternal:
                return {"action": "sell_joker", "index": idx}, True
        return {"action": "next_round"}, True
    
    else:
        # action_type 5 (NEXT_ROUND) or any other → leave shop
        return {"action": "next_round"}, True


def _decode_booster_action(action_type: int, card_mask: np.ndarray, game_state: GameState) -> Tuple[dict, bool]:
    """Decode actions when a booster pack is opened.
    
    Valid action types: 11 (pack_select), 12 (pack_skip).
    All other types default to pack_skip for safety.
    """
    if not game_state.pack or not game_state.pack.cards:
        # No pack cards available — skip
        return {"action": "pack_skip"}, True
    
    if action_type == 11:  # PACK_SELECT
        idx = _first_set_bit(card_mask, max_idx=4)  # up to 5 cards in pack
        if idx < len(game_state.pack.cards):
            card = game_state.pack.cards[idx]
            if card.set == "JOKER":
                current_jokers = len(game_state.jokers.cards) if game_state.jokers else 0
                joker_limit = game_state.jokers.limit if game_state.jokers else 5
                if current_jokers >= joker_limit:
                    return {"action": "pack_skip"}, True
            elif card.set in ("TAROT", "PLANET", "SPECTRAL"):
                current_consumables = len(game_state.consumables.cards) if game_state.consumables else 0
                consumable_limit = game_state.consumables.limit if game_state.consumables else 2
                if current_consumables >= consumable_limit:
                    return {"action": "pack_skip"}, True
            return {"action": "pack_select", "index": idx}, True
        else:
            # Index out of range, skip booster pack
            return {"action": "pack_skip"}, True
    
    else:
        # action_type 12 (PACK_SKIP) or any other → skip
        return {"action": "pack_skip"}, True
