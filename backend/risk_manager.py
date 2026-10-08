from config import config

class RiskManager:
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

        # Sizing basato sul rischio: la quantita' e' derivata da "quanto sono
        # disposto a perdere se lo stop viene colpito", non da una frazione
        # fissa del capitale. risk_amount_usdt e' l'importo che si perde
        # (prima della leva, che incide solo sul margine) se il prezzo arriva
        # esattamente sullo stop loss.
        #
        # Nota: in precedenza qui c'era `min(capital*0.20, capital*0.10)`,
        # un bug per cui il ramo al 20% non veniva mai raggiunto e la size
        # era sempre il 10% fisso del capitale, indipendentemente dal
        # rischio reale del trade (stop stretto o largo che fosse).
        risk_amount_usdt = capital * (config.RISK_PER_TRADE_PERCENT / 100.0)
        quantity_by_risk = risk_amount_usdt / sl_distance if sl_distance > 0 else 0.0

        # Tetto di sicurezza: anche con uno stop molto stretto (che implica
        # una size enorme a parita' di rischio in dollari), il nozionale non
        # supera mai MAX_POSITION_PERCENT del capitale.
        max_position_usdt = capital * (config.MAX_POSITION_PERCENT / 100.0)
        notional_by_risk = quantity_by_risk * price
        position_usdt = min(notional_by_risk, max_position_usdt)
        quantity = round(position_usdt / price, 6) if price > 0 else 0.0

        return {
            'quantity': quantity,
            'leverage': leverage,
            'stop_loss': round(stop_loss, 4),
            'take_profit': round(take_profit, 4),
            'risk_amount_usdt': round(min(risk_amount_usdt, position_usdt), 2),
        }

    def check_daily_loss_limit(self, daily_pnl, capital) -> bool:
        return daily_pnl > -(capital * (config.MAX_DAILY_LOSS_PERCENT / 100))

    def can_open_position(self, open_count) -> bool:
        return open_count < config.MAX_OPEN_POSITIONS

risk_manager = RiskManager()
