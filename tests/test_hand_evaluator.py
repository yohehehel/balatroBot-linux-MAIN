import pytest
from src.game_state import Card, CardValue, CardModifier, CardState, CardCost, GameState, HandInfo
from src.hand_evaluator import (
    evaluate_exact_subset, find_best_hand, estimate_score, get_best_play_decision
)

def make_card(rank: str, suit: str, enhancement: str = "Base", edition: str = "Base", debuffed: bool = False) -> Card:
    return Card(
        id=0,
        key=f"{suit}_{rank}",
        set="DEFAULT",
        label=f"{rank} of {suit}",
        value=CardValue(suit=suit, rank=rank, effect=""),
        modifier=CardModifier(
            enhancement=enhancement if enhancement != "Base" else None,
            edition=edition if edition != "Base" else None
        ),
        state=CardState(debuff=debuffed),
        cost=CardCost(sell=0, buy=0)
    )

def test_high_card():
    cards = [make_card("2", "H")]
    assert evaluate_exact_subset(cards) == "High Card"

def test_pair():
    cards = [make_card("A", "H"), make_card("A", "D")]
    assert evaluate_exact_subset(cards) == "Pair"

def test_two_pair():
    cards = [
        make_card("A", "H"), make_card("A", "D"),
        make_card("K", "C"), make_card("K", "S")
    ]
    assert evaluate_exact_subset(cards) == "Two Pair"

def test_three_of_a_kind():
    cards = [make_card("T", "H"), make_card("T", "D"), make_card("T", "C")]
    assert evaluate_exact_subset(cards) == "Three of a Kind"

def test_straight():
    cards = [
        make_card("2", "H"), make_card("3", "D"),
        make_card("4", "C"), make_card("5", "S"), make_card("6", "H")
    ]
    assert evaluate_exact_subset(cards) == "Straight"
    
    # Test Ace low straight
    cards_low = [
        make_card("A", "H"), make_card("2", "D"),
        make_card("3", "C"), make_card("4", "S"), make_card("5", "H")
    ]
    assert evaluate_exact_subset(cards_low) == "Straight"

def test_flush():
    cards = [
        make_card("2", "H"), make_card("5", "H"),
        make_card("9", "H"), make_card("J", "H"), make_card("A", "H")
    ]
    assert evaluate_exact_subset(cards) == "Flush"

def test_full_house():
    cards = [
        make_card("A", "H"), make_card("A", "D"), make_card("A", "C"),
        make_card("K", "S"), make_card("K", "H")
    ]
    assert evaluate_exact_subset(cards) == "Full House"

def test_four_of_a_kind():
    cards = [
        make_card("9", "H"), make_card("9", "D"),
        make_card("9", "C"), make_card("9", "S")
    ]
    assert evaluate_exact_subset(cards) == "Four of a Kind"

def test_five_of_a_kind():
    cards = [
        make_card("Q", "H"), make_card("Q", "D"),
        make_card("Q", "C"), make_card("Q", "S"), make_card("Q", "H")
    ]
    assert evaluate_exact_subset(cards) == "Five of a Kind"

def test_straight_flush():
    cards = [
        make_card("T", "S"), make_card("J", "S"),
        make_card("Q", "S"), make_card("K", "S"), make_card("A", "S")
    ]
    assert evaluate_exact_subset(cards) == "Straight Flush"

def test_flush_house():
    # Full house with all same suit (e.g. wild cards or modified deck)
    cards = [
        make_card("8", "C"), make_card("8", "C"), make_card("8", "C"),
        make_card("7", "C"), make_card("7", "C")
    ]
    assert evaluate_exact_subset(cards) == "Flush House"

def test_flush_five():
    cards = [
        make_card("A", "D"), make_card("A", "D"), make_card("A", "D"),
        make_card("A", "D"), make_card("A", "D")
    ]
    assert evaluate_exact_subset(cards) == "Flush Five"

def test_find_best_hand():
    # Hand of 8 cards: A-H, A-D, K-C, Q-S, T-H, 8-D, 5-C, 2-S
    hand = [
        make_card("A", "H"), make_card("A", "D"),
        make_card("K", "C"), make_card("Q", "S"),
        make_card("T", "H"), make_card("8", "D"),
        make_card("5", "C"), make_card("2", "S")
    ]
    htype, subset = find_best_hand(hand)
    assert htype == "Pair"
    assert len(subset) == 2
    assert subset[0].value.rank == "A"
    assert subset[1].value.rank == "A"

def test_estimate_score():
    state = GameState()
    state.hands["Pair"] = HandInfo(order=1, level=1, chips=10, mult=2, played=0, played_this_round=0)
    
    scoring_subset = [make_card("A", "H"), make_card("A", "D")]
    # Ace value is 11 chips each. Total chips = 10 (base) + 11 + 11 = 32. Mult = 2 (base). Score = 32 * 2 = 64
    score = estimate_score(scoring_subset, "Pair", state)
    assert score == 64
