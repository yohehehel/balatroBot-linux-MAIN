from typing import List, Tuple, Dict, Optional, Set
import itertools
from src.game_state import Card, GameState

RANK_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'T': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11
}

RANK_ORDERS = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
}

HAND_TYPES_BY_PRIORITY = [
    "Flush Five",
    "Flush House",
    "Five of a Kind",
    "Straight Flush",
    "Four of a Kind",
    "Full House",
    "Flush",
    "Straight",
    "Three of a Kind",
    "Two Pair",
    "Pair",
    "High Card"
]

def is_wild(card: Card) -> bool:
    return card.modifier.enhancement == "WILD" and not card.state.debuff

def is_stone(card: Card) -> bool:
    return card.modifier.enhancement == "STONE" and not card.state.debuff

def get_card_suit(card: Card) -> Optional[str]:
    if card.state.debuff:
        return card.value.suit
    return card.value.suit

def get_card_rank(card: Card) -> Optional[str]:
    if is_stone(card):
        return None
    return card.value.rank

def check_flush(cards: List[Card]) -> bool:
    if len(cards) < 5:
        return False
    # Check if there exists a suit that matches all cards (either matches card's suit or card is wild)
    for suit in ["H", "D", "C", "S"]:
        match = True
        for c in cards:
            c_suit = get_card_suit(c)
            if c_suit != suit and not is_wild(c):
                match = False
                break
        if match:
            return True
    return False

def check_straight(cards: List[Card]) -> bool:
    if len(cards) < 5:
        return False
    
    ranks = [get_card_rank(c) for c in cards]
    if any(r is None for r in ranks):
        return False
        
    # Get rank order values
    values = [RANK_ORDERS[r] for r in ranks if r in RANK_ORDERS]
    if len(values) < 5:
        return False
        
    # Standard Ace high
    v_sorted = sorted(values)
    if len(set(v_sorted)) == 5 and (v_sorted[-1] - v_sorted[0] == 4):
        return True
        
    # Ace low (Ace is 14, can be treated as 1)
    if 14 in values:
        v_low = [1 if x == 14 else x for x in values]
        v_low_sorted = sorted(v_low)
        if len(set(v_low_sorted)) == 5 and (v_low_sorted[-1] - v_low_sorted[0] == 4):
            return True
            
    return False

def evaluate_exact_subset(cards: List[Card]) -> str:
    """Evaluate the exact hand type formed by the list of cards (must use all of them)."""
    n = len(cards)
    if n == 0:
        return "High Card"
        
    # Get ranks
    ranks = [get_card_rank(c) for c in cards]
    # Filter out None ranks (stone cards)
    valid_ranks = [r for r in ranks if r is not None]
    
    rank_counts = {}
    for r in valid_ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
        
    # Count how many of each rank
    counts = sorted(list(rank_counts.values()), reverse=True)
    
    # 5 cards
    if n == 5:
        has_flush = check_flush(cards)
        has_straight = check_straight(cards)
        
        # Flush Five: 5 same rank, same suit
        if len(counts) == 1 and counts[0] == 5 and has_flush:
            return "Flush Five"
            
        # Flush House: Full House, same suit
        if len(counts) == 2 and counts[0] == 3 and counts[1] == 2 and has_flush:
            return "Flush House"
            
        # Five of a Kind: 5 same rank
        if len(counts) == 1 and counts[0] == 5:
            return "Five of a Kind"
            
        # Straight Flush: Straight, same suit
        if has_straight and has_flush:
            return "Straight Flush"
            
        # Full House
        if len(counts) == 2 and counts[0] == 3 and counts[1] == 2:
            return "Full House"
            
        # Flush
        if has_flush:
            return "Flush"
            
        # Straight
        if has_straight:
            return "Straight"
            
    # 4 cards or more (could be 5 cards as well if it failed above checks)
    if len(counts) >= 1 and counts[0] >= 4:
        return "Four of a Kind"
        
    if len(counts) >= 1 and counts[0] >= 3:
        # If 5 cards played, we already checked Full House, so it's Three of a Kind
        return "Three of a Kind"
        
    if len(counts) >= 2 and counts[0] >= 2 and counts[1] >= 2:
        return "Two Pair"
        
    if len(counts) >= 1 and counts[0] >= 2:
        return "Pair"
        
    return "High Card"


def get_scoring_cards(cards: List[Card], hand_type: str) -> List[Card]:
    if hand_type in ["Flush Five", "Flush House", "Five of a Kind", "Straight Flush", "Full House", "Flush", "Straight"]:
        return cards
        
    ranks = [get_card_rank(c) for c in cards]
    valid_ranks = [r for r in ranks if r is not None]
    
    rank_counts = {}
    for r in valid_ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
        
    if hand_type == "Four of a Kind":
        # Keep the 4 cards of the dominant rank
        if rank_counts:
            target_rank = max(rank_counts, key=rank_counts.get)
            return [c for c in cards if get_card_rank(c) == target_rank][:4]
        return cards[:4]
        
    elif hand_type == "Three of a Kind":
        # Keep the 3 cards of the dominant rank
        if rank_counts:
            target_rank = max(rank_counts, key=rank_counts.get)
            return [c for c in cards if get_card_rank(c) == target_rank][:3]
        return cards[:3]
        
    elif hand_type == "Two Pair":
        # Keep the two ranks with count >= 2
        target_ranks = [r for r, count in rank_counts.items() if count >= 2]
        target_ranks.sort(key=lambda r: RANK_ORDERS.get(r, 0), reverse=True)
        target_ranks = target_ranks[:2]
        return [c for c in cards if get_card_rank(c) in target_ranks]
        
    elif hand_type == "Pair":
        # Keep the rank with count >= 2
        target_ranks = [r for r, count in rank_counts.items() if count >= 2]
        if target_ranks:
            target_rank = max(target_ranks, key=lambda r: RANK_ORDERS.get(r, 0))
            return [c for c in cards if get_card_rank(c) == target_rank][:2]
        return cards[:2]
        
    elif hand_type == "High Card":
        # Keep only the card with the highest rank order
        if not cards:
            return []
        sorted_cards = sorted(cards, key=lambda c: RANK_ORDERS.get(get_card_rank(c), 0), reverse=True)
        return [sorted_cards[0]]
        
    return cards


def find_best_hand(played_cards: List[Card]) -> Tuple[str, List[Card]]:
    """
    Finds the highest hand type that can be formed by a subset of up to 5 played cards,
    and returns that hand type along with the scoring subset.
    """
    if not played_cards:
        return "High Card", []
        
    best_hand_type = "High Card"
    best_subset = [played_cards[0]] if played_cards else []
    
    max_size = min(len(played_cards), 5)
    
    for size in range(1, max_size + 1):
        for subset in itertools.combinations(played_cards, size):
            subset_list = list(subset)
            htype = evaluate_exact_subset(subset_list)
            
            # Check if this hand type is higher priority
            curr_idx = HAND_TYPES_BY_PRIORITY.index(htype)
            best_idx = HAND_TYPES_BY_PRIORITY.index(best_hand_type)
            
            if curr_idx < best_idx:
                best_hand_type = htype
                best_subset = subset_list
            elif curr_idx == best_idx:
                # Tie breaker: sum of rank orders of all cards in the subset
                curr_sum = sum(RANK_ORDERS.get(get_card_rank(c), 0) for c in subset_list)
                best_sum = sum(RANK_ORDERS.get(get_card_rank(c), 0) for c in best_subset)
                if curr_sum > best_sum:
                    best_subset = subset_list
                    
    # Only return the actual scoring cards for the detected hand type
    scoring_subset = get_scoring_cards(best_subset, best_hand_type)
    return best_hand_type, scoring_subset


def estimate_score(played_subset: List[Card], hand_type: str, game_state: GameState) -> int:
    """
    Estimates the score (chips * mult) of the played subset.
    Uses base values from game_state.hands for the given hand_type.
    """
    # 1. Get base chips and mult from game state for this hand type
    hand_info = game_state.hands.get(hand_type)
    if hand_info:
        base_chips = hand_info.chips
        base_mult = hand_info.mult
    else:
        # Fallback to level 1 defaults if hand type is unknown/not in state
        defaults = {
            "Flush Five": (160, 16),
            "Flush House": (140, 14),
            "Five of a Kind": (120, 12),
            "Straight Flush": (100, 8),
            "Four of a Kind": (60, 7),
            "Full House": (40, 4),
            "Flush": (35, 4),
            "Straight": (30, 4),
            "Three of a Kind": (30, 3),
            "Two Pair": (20, 2),
            "Pair": (10, 2),
            "High Card": (5, 1)
        }
        base_chips, base_mult = defaults.get(hand_type, (5, 1))

    # 2. Add chips from the cards that score
    # Note: Only cards in the scoring subset actually add their chips
    added_chips = 0
    added_mult = 0
    mult_multipliers = []  # List of multipliers, e.g. x1.5, x2
    
    for card in played_subset:
        if card.state.debuff:
            continue
            
        # Rank chips
        rank = get_card_rank(card)
        card_chips = RANK_VALUES.get(rank, 0) if rank else 0
        if is_stone(card):
            card_chips = 50
            
        # Enhancements
        if card.modifier.enhancement == "CHIPS":
            card_chips += 30
        elif card.modifier.enhancement == "MULT":
            added_mult += 4
        elif card.modifier.enhancement == "GLASS":
            mult_multipliers.append(2.0)
        elif card.modifier.enhancement == "LUCKY":
            # 1/5 chance of +20 mult, 1/15 chance of +20 chips. Average:
            added_mult += 4.0
            card_chips += 1.3
            
        # Editions
        if card.modifier.edition == "FOIL":
            card_chips += 50
        elif card.modifier.edition == "HOLOGRAPHIC":
            added_mult += 10
        elif card.modifier.edition == "POLYCHROME":
            mult_multipliers.append(1.5)
            
        # Red seal triggers card twice
        triggers = 2 if card.modifier.seal == "RED" else 1
        
        added_chips += card_chips * triggers
        added_mult += added_mult * (triggers - 1)  # simple double trigger mult
        
        # Apply multipliers for each trigger
        for _ in range(triggers):
            if card.modifier.enhancement == "GLASS":
                mult_multipliers.append(2.0)
            if card.modifier.edition == "POLYCHROME":
                mult_multipliers.append(1.5)
                
    total_chips = base_chips + added_chips
    total_mult = base_mult + added_mult
    
    # Apply multipliers
    for m in mult_multipliers:
        total_mult *= m
        
    return int(total_chips * total_mult)


def get_best_play_decision(hand_cards: List[Card], game_state: GameState) -> Tuple[List[int], str, int]:
    """
    Finds the absolute best combination of up to 5 cards from hand_cards that maximizes the estimated score.
    Returns: (list of 0-based indices of cards to play, hand_type, estimated_score)
    """
    if not hand_cards:
        return [], "High Card", 0
        
    best_indices = []
    best_score = -1
    best_hand_type = "High Card"
    
    # Generate all combinations of size 1 to 5 of card indices
    n = len(hand_cards)
    max_play_size = min(n, 5)
    
    for size in range(1, max_play_size + 1):
        for combo in itertools.combinations(range(n), size):
            combo_indices = list(combo)
            combo_cards = [hand_cards[i] for i in combo_indices]
            
            # Find the scoring hand type and subset
            htype, scoring_subset = find_best_hand(combo_cards)
            score = estimate_score(scoring_subset, htype, game_state)
            
            if score > best_score:
                best_score = score
                best_indices = combo_indices
                best_hand_type = htype
                
    return best_indices, best_hand_type, best_score
