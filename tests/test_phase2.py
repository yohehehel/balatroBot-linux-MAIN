"""Smoke test for Phase 2: action decoding and observation encoding."""
import numpy as np
from src.env.observation import get_observation_space, encode_observation
from src.env.action import get_action_space, decode_action
from src.game_state import GameState

def test_action_space():
    space = get_action_space()
    assert list(space.nvec) == [13, 2, 2, 2, 2, 2, 2, 2, 2], f"Unexpected: {space.nvec}"
    print("✓ Action space correct")

def test_observation_space():
    space = get_observation_space()
    expected_keys = {"game_info", "hand_cards", "joker_cards", "shop_cards", 
                     "shop_vouchers", "shop_packs", "pack_cards"}
    assert set(space.spaces.keys()) == expected_keys, f"Missing keys: {expected_keys - set(space.spaces.keys())}"
    print("✓ Observation space keys correct")

def test_decode_shop_buy_card():
    state = GameState.from_dict({
        "state": "SHOP", "money": 10,
        "shop": {"count": 2, "limit": 2, "cards": [
            {"id": 1, "key": "j_joker", "set": "JOKER", "label": "Joker",
             "value": {}, "modifier": {}, "state": {}, "cost": {"buy": 4, "sell": 2}}
        ]}
    })
    # action_type=6 (BUY_CARD), card_mask bit 0 set -> buy index 0
    action = np.array([6, 1, 0, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "buy_card"
    assert result["index"] == 0
    print("✓ Shop buy_card decode correct")

def test_decode_shop_buy_card_no_money():
    state = GameState.from_dict({
        "state": "SHOP", "money": 2,
        "shop": {"count": 1, "limit": 2, "cards": [
            {"id": 1, "key": "j_joker", "set": "JOKER", "label": "Joker",
             "value": {}, "modifier": {}, "state": {}, "cost": {"buy": 4, "sell": 2}}
        ]}
    })
    # action_type=6 (BUY_CARD) but money (2) < cost (4) -> fallback next_round
    action = np.array([6, 1, 0, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "next_round"
    print("✓ Shop buy_card fallback to next_round when no money correct")

def test_decode_shop_reroll():
    state = GameState.from_dict({
        "state": "SHOP", "money": 10,
        "round": {"reroll_cost": 5}
    })
    # action_type=9 (REROLL), money(10) >= reroll_cost(5) -> reroll
    action = np.array([9, 0, 0, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "reroll"
    print("✓ Shop reroll decode correct")

def test_decode_shop_sell_joker():
    state = GameState.from_dict({
        "state": "SHOP", "money": 5,
        "jokers": {"count": 2, "limit": 5, "cards": [
            {"id": 1, "key": "j_joker", "set": "JOKER", "label": "Joker",
             "value": {}, "modifier": {}, "state": {}, "cost": {"sell": 3}},
            {"id": 2, "key": "j_banner", "set": "JOKER", "label": "Banner",
             "value": {}, "modifier": {}, "state": {}, "cost": {"sell": 2}},
        ]}
    })
    # action_type=10 (SELL_JOKER), card_mask bit 1 set -> sell joker at index 1
    action = np.array([10, 0, 1, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "sell_joker"
    assert result["index"] == 1
    print("✓ Shop sell_joker decode correct")

def test_decode_shop_next_round():
    state = GameState.from_dict({"state": "SHOP", "money": 0})
    action = np.array([5, 0, 0, 0, 0, 0, 0, 0, 0])  # NEXT_ROUND
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "next_round"
    print("✓ Shop next_round decode correct")

def test_decode_booster_select():
    state = GameState.from_dict({
        "state": "BUFFOON_PACK",
        "pack": {"count": 2, "limit": 2, "cards": [
            {"id": 1, "key": "j_joker", "set": "JOKER", "label": "Joker",
             "value": {}, "modifier": {}, "state": {}, "cost": {}},
            {"id": 2, "key": "j_banner", "set": "JOKER", "label": "Banner",
             "value": {}, "modifier": {}, "state": {}, "cost": {}},
        ]}
    })
    # action_type=11 (PACK_SELECT), card_mask bit 1 set -> select index 1
    action = np.array([11, 0, 1, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "pack_select"
    assert result["index"] == 1
    print("✓ Booster pack_select decode correct")

def test_decode_booster_skip():
    state = GameState.from_dict({
        "state": "TAROT_PACK",
        "pack": {"count": 3, "limit": 3, "cards": [
            {"id": 1, "key": "c_magician", "set": "TAROT", "label": "The Magician",
             "value": {}, "modifier": {}, "state": {}, "cost": {}},
        ]}
    })
    # action_type=12 (PACK_SKIP) -> pack_skip
    action = np.array([12, 0, 0, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "pack_skip"
    print("✓ Booster pack_skip decode correct")

def test_decode_booster_select_spectral_target():
    state = GameState.from_dict({
        "state": "SPECTRAL_PACK",
        "pack": {"count": 1, "limit": 1, "cards": [
            {"id": 1, "key": "c_deja_vu", "set": "SPECTRAL", "label": "Deja Vu",
             "value": {}, "modifier": {}, "state": {}, "cost": {}},
        ]},
        "hand": {"count": 5, "limit": 8, "cards": [
            {"id": i, "key": f"card{i}", "set": "DEFAULT", "label": f"Card{i}",
             "value": {"suit": "H", "rank": "2"}, "modifier": {}, "state": {}, "cost": {}}
            for i in range(5)
        ]}
    })
    # action_type=11 (PACK_SELECT), card_mask bit 0 set (pack card index 0)
    # card_mask bit 1 set (select first card in hand as target)
    action = np.array([11, 1, 1, 0, 0, 0, 0, 0, 0])
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "pack_select"
    assert result["index"] == 0
    assert result["targets"] == [0]
    print("✓ Booster pack_select with c_deja_vu target selection correct")

def test_phase1_actions_unchanged():
    """Verify Phase 1 actions still work identically."""
    # SELECTING_HAND: play
    state = GameState.from_dict({
        "state": "SELECTING_HAND",
        "hand": {"count": 8, "limit": 8, "cards": [
            {"id": i, "key": f"c{i}", "set": "DEFAULT", "label": f"Card{i}",
             "value": {"suit": "H", "rank": "A"}, "modifier": {}, "state": {}, "cost": {}}
            for i in range(8)
        ]},
        "round": {"hands_left": 4, "discards_left": 3}
    })
    action = np.array([0, 1, 1, 1, 0, 0, 0, 0, 0])  # PLAY cards 0,1,2
    result, valid = decode_action(action, state)
    assert valid
    assert result["action"] == "play"
    assert result["cards"] == [0, 1, 2]
    
    # BLIND_SELECT: select
    state2 = GameState.from_dict({
        "state": "BLIND_SELECT",
        "blinds": {"small": {"type": "SMALL", "status": "SELECT"}}
    })
    action2 = np.array([2, 0, 0, 0, 0, 0, 0, 0, 0])
    result2, valid2 = decode_action(action2, state2)
    assert valid2
    assert result2["action"] == "select_blind"
    
    print("✓ Phase 1 actions unchanged")

def test_observation_with_shop_data():
    state = GameState.from_dict({
        "state": "SHOP", "round_num": 3, "ante_num": 1, "money": 17,
        "round": {"hands_left": 0, "reroll_cost": 5},
        "jokers": {"count": 1, "limit": 5, "cards": [
            {"id": 1, "key": "j_joker", "set": "JOKER", "label": "Joker",
             "value": {}, "modifier": {}, "state": {}, "cost": {"sell": 3}}
        ]},
        "shop": {"count": 2, "limit": 2, "cards": [
            {"id": 10, "key": "j_greedy_joker", "set": "JOKER", "label": "Greedy Joker",
             "value": {}, "modifier": {"edition": "FOIL"}, "state": {}, "cost": {"buy": 5, "sell": 3}}
        ]},
    })
    obs = encode_observation(state)
    
    # Check game_info extended fields
    gi = obs["game_info"]
    assert len(gi) == 23
    assert gi[10] == 5.0  # reroll_cost
    assert gi[11] == 1.0  # jokers_count
    assert gi[12] == 5.0  # jokers_limit
    assert gi[13] == 3.0  # interest_bonus = floor(17/5) = 3
    assert gi[14] == 1.0  # shop_active
    
    # Check joker encoding
    joker = obs["joker_cards"][0]
    assert joker[21] == 1.0  # presence flag
    assert joker[0] == 1/8   # JOKER set index = 1, /8
    assert joker[1] == 1.0   # j_joker is in group 0 -> feature[1] = 1.0
    
    # Check shop card
    shop_card = obs["shop_cards"][0]
    assert shop_card[21] == 1.0  # presence
    assert shop_card[18] == 0.33  # FOIL edition
    assert shop_card[8] == 5/20  # buy cost = 5, /20
    
    print("✓ Observation encoding with shop data correct")

def test_observation_hand_sorting_and_flags():
    # Hand: Ace of Hearts, King of Diamonds, Queen of Spades, 2 of Hearts, 2 of Clubs
    # This forms a Pair (of 2s).
    state = GameState.from_dict({
        "state": "SELECTING_HAND",
        "hand": {"count": 5, "limit": 8, "cards": [
            {"id": 1, "key": "c1", "set": "DEFAULT", "label": "2h", "value": {"suit": "H", "rank": "2"}, "modifier": {}, "state": {}, "cost": {}},
            {"id": 2, "key": "c2", "set": "DEFAULT", "label": "Ah", "value": {"suit": "H", "rank": "A"}, "modifier": {}, "state": {}, "cost": {}},
            {"id": 3, "key": "c3", "set": "DEFAULT", "label": "Q_S", "value": {"suit": "S", "rank": "Q"}, "modifier": {}, "state": {}, "cost": {}},
            {"id": 4, "key": "c4", "set": "DEFAULT", "label": "Kd", "value": {"suit": "D", "rank": "K"}, "modifier": {}, "state": {}, "cost": {}},
            {"id": 5, "key": "c5", "set": "DEFAULT", "label": "2c", "value": {"suit": "C", "rank": "2"}, "modifier": {}, "state": {}, "cost": {}},
        ]}
    })
    obs = encode_observation(state)
    
    # 1. Verify game_info length is 23
    gi = obs["game_info"]
    assert len(gi) == 23, f"Expected game_info size 23, got {len(gi)}"
    
    # Flags order: is_pair, is_two_pair, is_three_of_a_kind, is_straight, is_flush, is_full_house, is_four_of_a_kind, is_straight_flush
    # Expected: is_pair = 1.0, others = 0.0
    assert gi[15] == 1.0  # is_pair
    assert gi[16] == 0.0  # is_two_pair
    assert gi[17] == 0.0  # is_three_of_a_kind
    assert gi[18] == 0.0  # is_straight
    assert gi[19] == 0.0  # is_flush
    assert gi[20] == 0.0  # is_full_house
    assert gi[21] == 0.0  # is_four_of_a_kind
    assert gi[22] == 0.0  # is_straight_flush
    
    # 2. Verify sorting of hand_cards
    # Hand cards should be sorted by rank descending: A, K, Q, 2, 2.
    cards = obs["hand_cards"]
    
    # Card 0 (A)
    assert cards[0][4 + 12] == 1.0  # Rank A
    assert cards[0][0] == 1.0       # Suit H
    
    # Card 1 (K)
    assert cards[1][4 + 11] == 1.0  # Rank K
    assert cards[1][1] == 1.0       # Suit D
    
    # Card 2 (Q)
    assert cards[2][4 + 10] == 1.0  # Rank Q
    assert cards[2][3] == 1.0       # Suit S
    
    # Card 3 (2h)
    assert cards[3][4 + 0] == 1.0   # Rank 2
    assert cards[3][0] == 1.0       # Suit H
    
    # Card 4 (2c)
    assert cards[4][4 + 0] == 1.0   # Rank 2
    assert cards[4][2] == 1.0       # Suit C
    
    print("✓ Hand sorting and flags correct")

if __name__ == "__main__":
    test_action_space()
    test_observation_space()
    test_decode_shop_buy_card()
    test_decode_shop_buy_card_no_money()
    test_decode_shop_reroll()
    test_decode_shop_sell_joker()
    test_decode_shop_next_round()
    test_decode_booster_select()
    test_decode_booster_select_spectral_target()
    test_decode_booster_skip()
    test_phase1_actions_unchanged()
    test_observation_with_shop_data()
    test_observation_hand_sorting_and_flags()
    print("\n🎉 All Phase 2 smoke tests passed!")


