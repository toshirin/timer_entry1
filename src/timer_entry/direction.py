from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Side = Literal["buy", "sell"]
PriceSide = Literal["bid", "ask"]


@dataclass(frozen=True)
class DirectionSpec:
    # DirectionSpec は、売買方向ごとの価格系列規約を固定する。
    # scan / qualify / runtime が同じ定義を参照することで、
    # Buy/Sell の取り違えや Bid/Ask 混入を防ぐ。
    side: Side
    entry_col: str
    tp_hit_col: str
    tp_time_col: str | None
    sl_hit_col: str
    sl_time_col: str | None
    forced_exit_col: str
    entry_price_side: PriceSide
    exit_price_side: PriceSide
    tp_sign: int
    sl_sign: int

    @property
    def entry_series_name(self) -> str:
        return self.entry_col

    @property
    def tp_series_name(self) -> str:
        # TP は hit 判定に使う series と、実際の exit side を併記して監査しやすくする。
        return f"{self.tp_hit_col}/{self.exit_price_side}"

    @property
    def sl_series_name(self) -> str:
        # SL も trigger 側と実約定側を併記し、Buy/Sell 逆転バグを見つけやすくする。
        return f"{self.sl_hit_col}/{self.exit_price_side}"

    @property
    def forced_exit_series_name(self) -> str:
        return self.forced_exit_col

    @property
    def price_series_used(self) -> dict[str, str]:
        # 研究憲法に従い、使用系列はそのまま監査出力へ流せる形で持つ。
        return {
            "entry": self.entry_col,
            "tp_hit": self.tp_hit_col,
            "sl_hit": self.sl_hit_col,
            "forced_exit": self.forced_exit_col,
            "tp_order_time": self.tp_time_col or "",
            "sl_order_time": self.sl_time_col or "",
            "entry_price_side": self.entry_price_side,
            "exit_price_side": self.exit_price_side,
            "tp_series_name": self.tp_series_name,
            "sl_series_name": self.sl_series_name,
            "forced_exit_series_name": self.forced_exit_series_name,
        }


# Buy は実運用の long と同じ向きで固定する。
# entry は Ask、利確と forced exit は Bid、SL trigger は Ask を使う。
BUY_SPEC = DirectionSpec(
    side="buy",
    entry_col="Ask_Open",
    tp_hit_col="Bid_High",
    tp_time_col="Bid_High_Time",
    sl_hit_col="Ask_Low",
    sl_time_col="Ask_Low_Time",
    forced_exit_col="Bid_Close",
    entry_price_side="ask",
    exit_price_side="bid",
    tp_sign=+1,
    sl_sign=-1,
)


# Sell は Buy の完全な鏡像として固定する。
# entry は Bid、利確と forced exit は Ask、SL trigger は Bid を使う。
SELL_SPEC = DirectionSpec(
    side="sell",
    entry_col="Bid_Open",
    tp_hit_col="Ask_Low",
    tp_time_col="Ask_Low_Time",
    sl_hit_col="Bid_High",
    sl_time_col="Bid_High_Time",
    forced_exit_col="Ask_Close",
    entry_price_side="bid",
    exit_price_side="ask",
    tp_sign=-1,
    sl_sign=+1,
)


DIRECTION_SPECS: dict[Side, DirectionSpec] = {
    "buy": BUY_SPEC,
    "sell": SELL_SPEC,
}


def get_direction_spec(side: str) -> DirectionSpec:
    # runtime 側は設定値から文字列で side が来るので、
    # ここで正規化して unknown side を早めに落とす。
    normalized = side.strip().lower()
    if normalized not in DIRECTION_SPECS:
        raise ValueError(f"Unsupported side: {side}")
    return DIRECTION_SPECS[normalized]  # type: ignore[index]


__all__ = [
    "BUY_SPEC",
    "SELL_SPEC",
    "DIRECTION_SPECS",
    "DirectionSpec",
    "PriceSide",
    "Side",
    "get_direction_spec",
]
