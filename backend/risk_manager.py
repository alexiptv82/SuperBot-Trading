from config import config

class RiskManager:
    RISK_PER_TRADE = 0.02
    SCALP_TP_RATIO = 1.5
    MEDIUM_TP_RATIO = 3.0

    def calculate_trade_params(self, capital, price, atr, direction, trade_type, signal_strength) -> dict:
        leverage = max(min(int(signal_strength / 10), config.MAX_LEVERAGE), 2)
        sl_mult = 1.0 if trade_type == 'scalp' else 2.0
        sl_distance = atr * sl_mult
        tp_ratio = self.SCALP_TP_RATIO if trade_type == 'scalp' else self.MEDIUM_TP_RATIO
        if direction == 'long':
            stop_loss = price - sl_distance
            take_profit = price + (sl_distance * tp_ratio)
        else:
            stop_loss = price + sl_distance
            take_profit = price - (sl_distance * tp_ratio)
        risk_amount = capital * self.RISK_PER_TRADE
        sl_pct = sl_distance / price
        position_value = risk_amount / sl_pct if sl_pct > 0 else 0
        quantity = (position_value * leverage) / price if price > 0 else 0
        return {
            'quantity': round(quantity, 6), 'leverage': leverage,
            'stop_loss': round(stop_loss, 4), 'take_profit': round(take_profit, 4),
            'risk_amount_usdt': round(risk_amount, 2),
        }

    def check_daily_loss_limit(self, daily_pnl, capital) -> bool:
        return daily_pnl > -(capital * (config.MAX_DAILY_LOSS_PERCENT / 100))

    def can_open_position(self, open_count) -> bool:
        return open_count < config.MAX_OPEN_POSITIONS

risk_manager = RiskManager()
