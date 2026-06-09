import httpx
import logging
from typing import List, Optional, Any, Dict
from src.game_state import GameState

logger = logging.getLogger("BalatroClient")

class BalatroAPIError(Exception):
    """Exception raised for errors in the Balatro JSON-RPC API."""
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"API Error {code}: {message} (data: {data})")
        self.code = code
        self.message = message
        self.data = data


class BalatroClient:
    def __init__(self, base_url: str = "http://127.0.0.1:12346", timeout: float = 10.0):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        self._request_id = 1

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._request_id
        }
        self._request_id += 1
        
        try:
            logger.debug(f"Calling JSON-RPC method {method} with params {params}")
            response = self.client.post("/", json=payload)
            response.raise_for_status()
            res_json = response.json()
        except httpx.RequestError as e:
            logger.error(f"HTTP request failed: {e}")
            raise e
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {response.text}")
            raise e

        if "error" in res_json:
            err = res_json["error"]
            logger.error(f"JSON-RPC Error: {err}")
            raise BalatroAPIError(err.get("code", -1), err.get("message", "Unknown error"), err.get("data"))

        return res_json.get("result")

    def health(self) -> Dict[str, Any]:
        """Perform health check on the API."""
        return self._call("health")

    def gamestate(self) -> GameState:
        """Fetch the current game state."""
        res = self._call("gamestate")
        return GameState.from_dict(res)

    def start(self, deck: str = "RED", stake: str = "WHITE", seed: Optional[str] = None) -> GameState:
        """Start a new game run."""
        params = {"deck": deck, "stake": stake}
        if seed:
            params["seed"] = seed
        res = self._call("start", params)
        return GameState.from_dict(res)

    def menu(self) -> GameState:
        """Return to main menu."""
        res = self._call("menu")
        return GameState.from_dict(res)

    def select(self) -> GameState:
        """Select the current blind."""
        res = self._call("select")
        return GameState.from_dict(res)

    def skip(self) -> GameState:
        """Skip the current blind."""
        res = self._call("skip")
        return GameState.from_dict(res)

    def play(self, cards: List[int]) -> GameState:
        """Play cards from the hand. Indices are 0-based."""
        res = self._call("play", {"cards": cards})
        return GameState.from_dict(res)

    def discard(self, cards: List[int]) -> GameState:
        """Discard cards from the hand. Indices are 0-based."""
        res = self._call("discard", {"cards": cards})
        return GameState.from_dict(res)

    def buy(self, card: Optional[int] = None, voucher: Optional[int] = None, pack: Optional[int] = None) -> GameState:
        """Buy an item from the shop (exactly one parameter must be provided)."""
        params = {}
        if card is not None:
            params["card"] = card
        elif voucher is not None:
            params["voucher"] = voucher
        elif pack is not None:
            params["pack"] = pack
        else:
            raise ValueError("Must specify either card, voucher, or pack to buy.")
            
        res = self._call("buy", params)
        return GameState.from_dict(res)

    def sell(self, joker: Optional[int] = None, consumable: Optional[int] = None) -> GameState:
        """Sell a joker or consumable (exactly one parameter must be provided)."""
        params = {}
        if joker is not None:
            params["joker"] = joker
        elif consumable is not None:
            params["consumable"] = consumable
        else:
            raise ValueError("Must specify either joker or consumable to sell.")
            
        res = self._call("sell", params)
        return GameState.from_dict(res)

    def use(self, consumable: int, cards: Optional[List[int]] = None) -> GameState:
        """Use a consumable card. Indices are 0-based."""
        params = {"consumable": consumable}
        if cards is not None:
            params["cards"] = cards
        res = self._call("use", params)
        return GameState.from_dict(res)

    def reroll(self) -> GameState:
        """Reroll shop items."""
        res = self._call("reroll")
        return GameState.from_dict(res)

    def cash_out(self) -> GameState:
        """Cash out after a round."""
        res = self._call("cash_out")
        return GameState.from_dict(res)

    def next_round(self) -> GameState:
        """Advance from shop to blind selection."""
        res = self._call("next_round")
        return GameState.from_dict(res)

    def pack(self, card: Optional[int] = None, targets: Optional[List[int]] = None, skip: Optional[bool] = None) -> GameState:
        """Select or skip a card from an opened booster pack."""
        params = {}
        if card is not None:
            params["card"] = card
        if targets is not None:
            params["targets"] = targets
        if skip is not None:
            params["skip"] = skip
        res = self._call("pack", params)
        return GameState.from_dict(res)
