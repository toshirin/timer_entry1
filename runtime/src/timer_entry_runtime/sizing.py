from __future__ import annotations

from .constants import OANDA_MARGIN_RATE
from .models import AccountSnapshot, PriceSnapshot, SettingConfig, TradeComputation


def compute_units(
    *,
    setting: SettingConfig,
    account: AccountSnapshot,
    price: PriceSnapshot,
) -> TradeComputation:
    margin_price = price.ask
    margin_price_side = "ask"

    if setting.fixed_units is not None:
        required_margin = setting.fixed_units * margin_price * OANDA_MARGIN_RATE
        estimated = account.balance / required_margin * 100.0 if required_margin > 0 else None
        return TradeComputation(
            requested_units=int(setting.fixed_units),
            sizing_basis="fixed_units",
            effective_margin_ratio=None,
            estimated_margin_ratio_after_entry=estimated,
            margin_price=margin_price,
            margin_price_side=margin_price_side,
        )

    if setting.margin_ratio_target is None:
        raise ValueError("margin_ratio_target is required when fixed_units is not set")

    if setting.size_scale_pct is None:
        effective_margin_ratio = float(setting.margin_ratio_target)
        sizing_basis = "margin_ratio_target"
    else:
        if setting.size_scale_pct <= 0:
            raise ValueError("size_scale_pct must be greater than zero")
        effective_margin_ratio = float(setting.margin_ratio_target) * (100.0 / float(setting.size_scale_pct))
        sizing_basis = "margin_ratio_target_with_size_scale_pct"

    units = int(account.balance / (effective_margin_ratio / 100.0) / (margin_price * OANDA_MARGIN_RATE))
    if units <= 0:
        raise ValueError("computed units must be greater than zero")

    required_margin = units * margin_price * OANDA_MARGIN_RATE
    estimated = account.balance / required_margin * 100.0 if required_margin > 0 else None
    return TradeComputation(
        requested_units=units,
        sizing_basis=sizing_basis,
        effective_margin_ratio=effective_margin_ratio,
        estimated_margin_ratio_after_entry=estimated,
        margin_price=margin_price,
        margin_price_side=margin_price_side,
    )
