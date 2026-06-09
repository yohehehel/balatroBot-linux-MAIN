import numpy as np
from typing import Dict, Any
from gymnasium import spaces
from src.game_state import GameState, Card

STATES = [
    "UNKNOWN", "MENU", "BLIND_SELECT", "SELECTING_HAND",
    "ROUND_EVAL", "SHOP", "GAME_OVER", "SMODS_BOOSTER_OPENED"
]

SUITS = ["H", "D", "C", "S"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]

# Card set name -> numeric index for encoding
CARD_SET_IDX = {
    "DEFAULT": 0,
    "JOKER": 1,
    "TAROT": 2,
    "PLANET": 3,
    "SPECTRAL": 4,
    "VOUCHER": 5,
    "BOOSTER": 6,
    "EDITION": 7,
    "ENHANCED": 8,
}

# Top ~80 most common jokers in Balatro, mapped to group indices (0..6)
# Each group has ~12 jokers. Jokers not in this list get group 7 (OTHER).
JOKER_KEY_GROUPS = {
    # Group 0: Mult jokers
    "j_joker": 0, "j_greedy_joker": 0, "j_lusty_joker": 0,
    "j_wrathful_joker": 0, "j_gluttenous_joker": 0, "j_jolly": 0,
    "j_zany": 0, "j_mad": 0, "j_crazy": 0, "j_droll": 0,
    "j_half": 0, "j_stencil": 0,
    # Group 1: Chip jokers
    "j_sly": 1, "j_wily": 1, "j_clever": 1, "j_devious": 1,
    "j_crafty": 1, "j_banner": 1, "j_mystic_summit": 1,
    "j_marble": 1, "j_loyalty_card": 1, "j_misprint": 1,
    "j_steel_joker": 1, "j_rough_gem": 1,
    # Group 2: xMult / scaling jokers
    "j_blackboard": 2, "j_runner": 2, "j_ice_cream": 2,
    "j_DNA": 2, "j_ride_the_bus": 2, "j_green_joker": 2,
    "j_red_card": 2, "j_madness": 2, "j_square": 2,
    "j_vampire": 2, "j_obelisk": 2, "j_lucky_cat": 2,
    # Group 3: Economy jokers
    "j_to_the_moon": 3, "j_golden": 3, "j_rocket": 3,
    "j_delayed_grat": 3, "j_business": 3, "j_faceless": 3,
    "j_todo_list": 3, "j_egg": 3, "j_gift": 3,
    "j_trading": 3, "j_cloud_9": 3, "j_mail": 3,
    # Group 4: Retrigger / special mechanic jokers
    "j_mime": 4, "j_dusk": 4, "j_hack": 4,
    "j_sock_and_buskin": 4, "j_hanging_chad": 4,
    "j_seltzer": 4, "j_blueprint": 4, "j_brainstorm": 4,
    "j_baron": 4, "j_photograph": 4, "j_ancient": 4,
    "j_triboulet": 4,
    # Group 5: Hand-type boosters
    "j_raised_fist": 5, "j_fibonacci": 5, "j_even_steven": 5,
    "j_odd_todd": 5, "j_scholar": 5, "j_walkie_talkie": 5,
    "j_smeared": 5, "j_shortcut": 5, "j_four_fingers": 5,
    "j_splash": 5, "j_flower_pot": 5, "j_acrobat": 5,
    # Group 6: Miscellaneous strong jokers
    "j_abstract": 6, "j_constellation": 6, "j_cartomancer": 6,
    "j_astronomer": 6, "j_burnt": 6, "j_juggler": 6,
    "j_drunkard": 6, "j_stone": 6, "j_bull": 6,
    "j_diet_cola": 6, "j_popcorn": 6, "j_campfire": 6,
}
NUM_JOKER_GROUPS = 8  # 0..6 = known groups, 7 = OTHER

# Edition encodings
EDITION_VALUES = {
    "FOIL": 0.33,
    "HOLOGRAPHIC": 0.66,
    "POLYCHROME": 1.0,
}

# Number of features per shop/joker card
CARD_FEATURES = 22

# Observation key shapes
GAME_INFO_SIZE = 23
HAND_CARD_FEATURES = 20
MAX_HAND_CARDS = 8
MAX_JOKERS = 5
MAX_SHOP_CARDS = 2
MAX_SHOP_VOUCHERS = 2
MAX_SHOP_PACKS = 2
MAX_PACK_CARDS = 5


def get_state_idx(state_name: str) -> int:
    if state_name in {"TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK", "BUFFOON_PACK"}:
        state_name = "SMODS_BOOSTER_OPENED"
    try:
        return STATES.index(state_name)
    except ValueError:
        return 0

def get_card_sort_key(card: Card) -> tuple:
    rank = card.value.rank
    suit = card.value.suit
    
    try:
        rank_idx = RANKS.index(rank) if (rank and rank in RANKS) else -1
    except ValueError:
        rank_idx = -1
        
    try:
        suit_idx = SUITS.index(suit) if (suit and suit in SUITS) else -1
    except ValueError:
        suit_idx = -1
        
    return (-rank_idx, suit_idx)

def get_hand_flags(cards: list) -> dict:
    flags = {
        "is_pair": 0.0,
        "is_two_pair": 0.0,
        "is_three_of_a_kind": 0.0,
        "is_straight": 0.0,
        "is_flush": 0.0,
        "is_full_house": 0.0,
        "is_four_of_a_kind": 0.0,
        "is_straight_flush": 0.0
    }
    if not cards:
        return flags
        
    from src.hand_evaluator import get_card_rank, get_card_suit, is_wild, check_straight, check_flush
    import itertools

    ranks = [get_card_rank(c) for c in cards]
    valid_ranks = [r for r in ranks if r is not None]
    
    rank_counts = {}
    for r in valid_ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
        
    counts = sorted(list(rank_counts.values()), reverse=True)
    
    # Pairs, Three of a Kind, Four of a Kind
    if len(counts) >= 1:
        if counts[0] >= 2:
            flags["is_pair"] = 1.0
        if counts[0] >= 3:
            flags["is_three_of_a_kind"] = 1.0
        if counts[0] >= 4:
            flags["is_four_of_a_kind"] = 1.0
            
    # Two Pair
    if len(counts) >= 2 and counts[0] >= 2 and counts[1] >= 2:
        flags["is_two_pair"] = 1.0
        
    # Full House
    if len(counts) >= 2 and counts[0] >= 3 and counts[1] >= 2:
        flags["is_full_house"] = 1.0
        
    # Flush
    for suit in ["H", "D", "C", "S"]:
        suit_count = 0
        for c in cards:
            c_suit = get_card_suit(c)
            if c_suit == suit or is_wild(c):
                suit_count += 1
        if suit_count >= 5:
            flags["is_flush"] = 1.0
            break
            
    # Straight & Straight Flush
    if len(cards) >= 5:
        for subset in itertools.combinations(cards, 5):
            subset_list = list(subset)
            if check_straight(subset_list):
                flags["is_straight"] = 1.0
                if check_flush(subset_list):
                    flags["is_straight_flush"] = 1.0
                    
    # Ensure logical implication
    if flags["is_straight_flush"] == 1.0:
        flags["is_straight"] = 1.0
        flags["is_flush"] = 1.0
        
    return flags

def get_observation_space() -> spaces.Dict:
    return spaces.Dict({
        "game_info": spaces.Box(low=0.0, high=1e9, shape=(GAME_INFO_SIZE,), dtype=np.float32),
        "hand_cards": spaces.Box(low=0.0, high=1.0, shape=(MAX_HAND_CARDS, HAND_CARD_FEATURES), dtype=np.float32),
        "joker_cards": spaces.Box(low=0.0, high=1.0, shape=(MAX_JOKERS, CARD_FEATURES), dtype=np.float32),
        "shop_cards": spaces.Box(low=0.0, high=1.0, shape=(MAX_SHOP_CARDS, CARD_FEATURES), dtype=np.float32),
        "shop_vouchers": spaces.Box(low=0.0, high=1.0, shape=(MAX_SHOP_VOUCHERS, CARD_FEATURES), dtype=np.float32),
        "shop_packs": spaces.Box(low=0.0, high=1.0, shape=(MAX_SHOP_PACKS, CARD_FEATURES), dtype=np.float32),
        "pack_cards": spaces.Box(low=0.0, high=1.0, shape=(MAX_PACK_CARDS, CARD_FEATURES), dtype=np.float32),
    })

def encode_card(card: Card) -> np.ndarray:
    """Encode a hand card into 20 features (Phase 1 format, unchanged)."""
    # 20 features per card:
    # 4 for suit one-hot
    # 13 for rank one-hot
    # 3 for state flags (debuffed, hidden, highlight)
    features = np.zeros(HAND_CARD_FEATURES, dtype=np.float32)
    
    # Suit one-hot
    suit = card.value.suit
    if suit in SUITS:
        features[SUITS.index(suit)] = 1.0
        
    # Rank one-hot
    rank = card.value.rank
    if rank in RANKS:
        features[4 + RANKS.index(rank)] = 1.0
        
    # Flags
    if card.state.debuff:
        features[17] = 1.0
    if card.state.hidden:
        features[18] = 1.0
    if card.state.highlight:
        features[19] = 1.0
        
    return features


def encode_shop_card(card: Card) -> np.ndarray:
    """Encode a shop/joker/voucher/pack card into 22 features.
    
    Feature layout:
    [0]      card set index (normalized by /8)
    [1..7]   joker group one-hot (7 features, group 7 = OTHER fills none)
    [8]      buy cost (normalized by /20)
    [9]      sell cost (normalized by /10)
    [10..13] suit one-hot (for playing cards in packs)
    [14..17] rank bucket one-hot (Low 2-5, Mid 6-9, Face T-K, Ace)
    [18]     edition value (foil=0.33, holo=0.66, poly=1.0)
    [19]     eternal flag
    [20]     rental flag
    [21]     presence flag (always 1.0 for real cards)
    """
    features = np.zeros(CARD_FEATURES, dtype=np.float32)
    
    # [0] Card set
    set_idx = CARD_SET_IDX.get(card.set, 0)
    features[0] = set_idx / 8.0
    
    # [1..7] Joker group one-hot
    if card.set == "JOKER" and card.key:
        group = JOKER_KEY_GROUPS.get(card.key, 7)
        if group < 7:  # Known groups get one-hot, OTHER (7) leaves all zeros
            features[1 + group] = 1.0
    
    # [8] Buy cost
    features[8] = min(card.cost.buy / 20.0, 1.0)
    
    # [9] Sell cost
    features[9] = min(card.cost.sell / 10.0, 1.0)
    
    # [10..13] Suit one-hot
    if card.value.suit and card.value.suit in SUITS:
        features[10 + SUITS.index(card.value.suit)] = 1.0
    
    # [14..17] Rank bucket
    rank = card.value.rank
    if rank in RANKS:
        rank_idx = RANKS.index(rank)
        if rank_idx <= 3:       # 2-5
            features[14] = 1.0
        elif rank_idx <= 7:     # 6-9
            features[15] = 1.0
        elif rank_idx <= 11:    # T-K
            features[16] = 1.0
        else:                   # A
            features[17] = 1.0
    
    # [18] Edition
    if card.modifier.edition:
        features[18] = EDITION_VALUES.get(card.modifier.edition, 0.0)
    
    # [19] Eternal
    if card.modifier.eternal:
        features[19] = 1.0
    
    # [20] Rental
    if card.modifier.rental:
        features[20] = 1.0
    
    # [21] Presence flag
    features[21] = 1.0
    
    return features


def encode_observation(state: GameState) -> Dict[str, np.ndarray]:
    # 1. Encode game_info (23 elements)
    target_score = 0
    for blind in state.blinds.values():
        if blind.status == "CURRENT":
            target_score = blind.score
            break
    
    jokers_count = len(state.jokers.cards) if state.jokers else 0
    jokers_limit = state.jokers.limit if state.jokers else 5
    interest_bonus = min(int(state.money) // 5, 5)
    shop_active = 1.0 if state.state == "SHOP" else 0.0
    reroll_cost = state.round.reroll_cost
    
    hand_flags = get_hand_flags(state.hand.cards if (state.hand and state.hand.cards) else [])
            
    game_info = np.array([
        float(state.round_num),
        float(state.ante_num),
        float(state.money),
        float(state.round.hands_left),
        float(state.round.hands_played),
        float(state.round.discards_left),
        float(state.round.discards_used),
        float(state.round.chips),
        float(target_score),
        float(get_state_idx(state.state)),
        # Phase 2 additions:
        float(reroll_cost),
        float(jokers_count),
        float(jokers_limit),
        float(interest_bonus),
        shop_active,
        # Hand type flags (Feature Engineering):
        hand_flags["is_pair"],
        hand_flags["is_two_pair"],
        hand_flags["is_three_of_a_kind"],
        hand_flags["is_straight"],
        hand_flags["is_flush"],
        hand_flags["is_full_house"],
        hand_flags["is_four_of_a_kind"],
        hand_flags["is_straight_flush"],
    ], dtype=np.float32)
    
    # 2. Encode hand_cards (8 slots, 20 features each) - sorted by rank descending then suit
    hand_cards = np.zeros((MAX_HAND_CARDS, HAND_CARD_FEATURES), dtype=np.float32)
    if state.hand and state.hand.cards:
        sorted_cards = sorted(state.hand.cards, key=get_card_sort_key)
        for i, card in enumerate(sorted_cards[:MAX_HAND_CARDS]):
            hand_cards[i] = encode_card(card)
    
    # 3. Encode owned jokers (5 slots, 22 features each)
    joker_cards = np.zeros((MAX_JOKERS, CARD_FEATURES), dtype=np.float32)
    if state.jokers and state.jokers.cards:
        for i, card in enumerate(state.jokers.cards[:MAX_JOKERS]):
            joker_cards[i] = encode_shop_card(card)
    
    # 4. Encode shop cards (2 slots)
    shop_cards = np.zeros((MAX_SHOP_CARDS, CARD_FEATURES), dtype=np.float32)
    if state.shop and state.shop.cards:
        for i, card in enumerate(state.shop.cards[:MAX_SHOP_CARDS]):
            shop_cards[i] = encode_shop_card(card)
    
    # 5. Encode shop vouchers (2 slots)
    shop_vouchers = np.zeros((MAX_SHOP_VOUCHERS, CARD_FEATURES), dtype=np.float32)
    if state.vouchers and state.vouchers.cards:
        for i, card in enumerate(state.vouchers.cards[:MAX_SHOP_VOUCHERS]):
            shop_vouchers[i] = encode_shop_card(card)
    
    # 6. Encode shop packs (2 slots)
    shop_packs = np.zeros((MAX_SHOP_PACKS, CARD_FEATURES), dtype=np.float32)
    if state.packs and state.packs.cards:
        for i, card in enumerate(state.packs.cards[:MAX_SHOP_PACKS]):
            shop_packs[i] = encode_shop_card(card)
    
    # 7. Encode opened booster pack cards (5 slots)
    pack_cards = np.zeros((MAX_PACK_CARDS, CARD_FEATURES), dtype=np.float32)
    if state.pack and state.pack.cards:
        for i, card in enumerate(state.pack.cards[:MAX_PACK_CARDS]):
            pack_cards[i] = encode_shop_card(card)
            
    return {
        "game_info": game_info,
        "hand_cards": hand_cards,
        "joker_cards": joker_cards,
        "shop_cards": shop_cards,
        "shop_vouchers": shop_vouchers,
        "shop_packs": shop_packs,
        "pack_cards": pack_cards,
    }
