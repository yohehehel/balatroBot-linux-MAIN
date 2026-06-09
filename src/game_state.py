from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

@dataclass
class CardValue:
    suit: Optional[str] = None       # "H", "D", "C", "S"
    rank: Optional[str] = None       # "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"
    effect: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "CardValue":
        if not isinstance(d, dict):
            d = {}
        return cls(
            suit=d.get("suit"),
            rank=d.get("rank"),
            effect=d.get("effect", "")
        )

@dataclass
class CardModifier:
    seal: Optional[str] = None         # "GOLD", "RED", "BLUE", "PURPLE"
    edition: Optional[str] = None      # "FOIL", "HOLOGRAPHIC", "POLYCHROME", "NEGATIVE"
    enhancement: Optional[str] = None  # "GOLD", "STEEL", "STONE", "GLASS", "WILD", "LUCKY", "MULT", "CHIPS"
    eternal: bool = False
    perishable: Optional[int] = None
    rental: bool = False

    @classmethod
    def from_dict(cls, d: Any) -> "CardModifier":
        if not isinstance(d, dict):
            d = {}
        return cls(
            seal=d.get("seal"),
            edition=d.get("edition"),
            enhancement=d.get("enhancement"),
            eternal=d.get("eternal", False),
            perishable=d.get("perishable"),
            rental=d.get("rental", False)
        )

@dataclass
class CardState:
    debuff: bool = False
    hidden: bool = False
    highlight: bool = False

    @classmethod
    def from_dict(cls, d: Any) -> "CardState":
        if not isinstance(d, dict):
            d = {}
        return cls(
            debuff=d.get("debuff", False),
            hidden=d.get("hidden", False),
            highlight=d.get("highlight", False)
        )

@dataclass
class CardCost:
    sell: int = 0
    buy: int = 0

    @classmethod
    def from_dict(cls, d: Any) -> "CardCost":
        if not isinstance(d, dict):
            d = {}
        return cls(
            sell=d.get("sell", 0),
            buy=d.get("buy", 0)
        )

@dataclass
class Card:
    id: int
    key: str
    set: str             # "JOKER", "TAROT", "PLANET", "SPECTRAL", "VOUCHER", "BOOSTER", "EDITION", "ENHANCED", "DEFAULT"
    label: str
    value: CardValue
    modifier: CardModifier
    state: CardState
    cost: CardCost

    @classmethod
    def from_dict(cls, d: Any) -> "Card":
        if not isinstance(d, dict):
            d = {}
        return cls(
            id=d.get("id", 0),
            key=d.get("key", ""),
            set=d.get("set", "DEFAULT"),
            label=d.get("label", ""),
            value=CardValue.from_dict(d.get("value", {})),
            modifier=CardModifier.from_dict(d.get("modifier", {})),
            state=CardState.from_dict(d.get("state", {})),
            cost=CardCost.from_dict(d.get("cost", {}))
        )

@dataclass
class Area:
    count: int = 0
    limit: int = 0
    highlighted_limit: Optional[int] = None
    cards: List[Card] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any) -> "Area":
        if not isinstance(d, dict):
            d = {}
        cards_raw = d.get("cards", [])
        cards_list = []
        if isinstance(cards_raw, dict):
            # Parse dict keys as digits, Lua list with holes
            sorted_keys = sorted(cards_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 99999)
            cards_list = [Card.from_dict(cards_raw[k]) for k in sorted_keys]
        elif isinstance(cards_raw, list):
            cards_list = [Card.from_dict(c) for c in cards_raw]

        return cls(
            count=d.get("count", 0),
            limit=d.get("limit", 0),
            highlighted_limit=d.get("highlighted_limit"),
            cards=cards_list
        )

@dataclass
class HandInfo:
    order: int
    level: int
    chips: int
    mult: int
    played: int
    played_this_round: int
    example: List[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any) -> "HandInfo":
        if not isinstance(d, dict):
            d = {}
        return cls(
            order=d.get("order", 0),
            level=d.get("level", 1),
            chips=d.get("chips", 0),
            mult=d.get("mult", 0),
            played=d.get("played", 0),
            played_this_round=d.get("played_this_round", 0),
            example=d.get("example", [])
        )

@dataclass
class RoundInfo:
    hands_left: int = 0
    hands_played: int = 0
    discards_left: int = 0
    discards_used: int = 0
    reroll_cost: int = 0
    chips: int = 0

    @classmethod
    def from_dict(cls, d: Any) -> "RoundInfo":
        if not isinstance(d, dict):
            d = {}
        return cls(
            hands_left=d.get("hands_left", 0),
            hands_played=d.get("hands_played", 0),
            discards_left=d.get("discards_left", 0),
            discards_used=d.get("discards_used", 0),
            reroll_cost=d.get("reroll_cost", 0),
            chips=d.get("chips", 0)
        )

@dataclass
class BlindInfo:
    type: str                # "SMALL", "BIG", "BOSS"
    status: str              # "DEFEATED", "SKIPPED", "CURRENT", "SELECT", "UPCOMING"
    name: str = ""
    effect: str = ""
    score: int = 0
    tag_name: str = ""
    tag_effect: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "BlindInfo":
        if not isinstance(d, dict):
            d = {}
        return cls(
            type=d.get("type", ""),
            status=d.get("status", "UPCOMING"),
            name=d.get("name", ""),
            effect=d.get("effect", ""),
            score=d.get("score", 0),
            tag_name=d.get("tag_name", ""),
            tag_effect=d.get("tag_effect", "")
        )

@dataclass
class GameState:
    state: str = "UNKNOWN"
    round_num: int = 0
    ante_num: int = 0
    money: int = 0
    won: Optional[bool] = None
    deck: Optional[str] = None
    stake: Optional[str] = None
    seed: Optional[str] = None
    used_vouchers: Dict[str, str] = field(default_factory=dict)
    hands: Dict[str, HandInfo] = field(default_factory=dict)
    round: RoundInfo = field(default_factory=RoundInfo)
    blinds: Dict[str, BlindInfo] = field(default_factory=dict)
    jokers: Optional[Area] = None
    consumables: Optional[Area] = None
    cards: Optional[Area] = None
    hand: Optional[Area] = None
    shop: Optional[Area] = None
    vouchers: Optional[Area] = None
    packs: Optional[Area] = None
    pack: Optional[Area] = None

    @classmethod
    def from_dict(cls, d: Any) -> "GameState":
        if not isinstance(d, dict):
            d = {}
        hands_raw = d.get("hands", {})
        hands_parsed = {k: HandInfo.from_dict(v) for k, v in hands_raw.items()}

        blinds_raw = d.get("blinds", {})
        blinds_parsed = {k: BlindInfo.from_dict(v) for k, v in blinds_raw.items()}

        return cls(
            state=d.get("state", "UNKNOWN"),
            round_num=d.get("round_num", 0),
            ante_num=d.get("ante_num", 0),
            money=d.get("money", 0),
            won=d.get("won"),
            deck=d.get("deck"),
            stake=d.get("stake"),
            seed=d.get("seed"),
            used_vouchers=d.get("used_vouchers", {}),
            hands=hands_parsed,
            round=RoundInfo.from_dict(d.get("round", {})),
            blinds=blinds_parsed,
            jokers=Area.from_dict(d.get("jokers", {})) if "jokers" in d and d["jokers"] else None,
            consumables=Area.from_dict(d.get("consumables", {})) if "consumables" in d and d["consumables"] else None,
            cards=Area.from_dict(d.get("cards", {})) if "cards" in d and d["cards"] else None,
            hand=Area.from_dict(d.get("hand", {})) if "hand" in d and d["hand"] else None,
            shop=Area.from_dict(d.get("shop", {})) if "shop" in d and d["shop"] else None,
            vouchers=Area.from_dict(d.get("vouchers", {})) if "vouchers" in d and d["vouchers"] else None,
            packs=Area.from_dict(d.get("packs", {})) if "packs" in d and d["packs"] else None,
            pack=Area.from_dict(d.get("pack", {})) if "pack" in d and d["pack"] else None
        )
