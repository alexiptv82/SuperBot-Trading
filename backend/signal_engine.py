from indicators import TechnicalIndicators

class SignalEngine:
    MIN_STRENGTH = 60

    def analyze(self, ohlcv_1m, ohlcv_15m, ohlcv_1h) -> dict:
        try:
            i1m = TechnicalIndicators(ohlcv_1m).compute_all()
            i15m = TechnicalIndicators(ohlcv_15m).compute_all()
            i1h = TechnicalIndicators(ohlcv_1h).compute_all()
        except ValueError as e:
            return {'error': str(e), 'signal': 'hold', 'strength': 0}

        scalp = self._scalp(i1m, i15m)
        medium = self._medium(i15m, i1h)
        best = scalp if scalp['strength'] >= medium['strength'] else medium

        return {
            'signal': best['direction'],
            'strength': best['strength'],
            'trade_type': best['type'],
            'main_trend': i1h['trend'],
            'indicators_1m': i1m,
            'indicators_15m': i15m,
            'indicators_1h': i1h,
            'reasons': best['reasons'],
        }

    def _scalp(self, i1m, i15m) -> dict:
        score, reasons = 0, []
        rsi = i1m['rsi']
        if rsi < 35: score += 25; reasons.append(f'RSI ipervenduto ({rsi:.1f})')
        elif rsi > 65: score -= 25; reasons.append(f'RSI ipercomprato ({rsi:.1f})')
        if i1m['macd']['bullish_cross']: score += 30; reasons.append('MACD cross rialzista')
        elif i1m['macd']['bearish_cross']: score -= 30; reasons.append('MACD cross ribassista')
        if i15m['trend'] == 'bullish': score += 15; reasons.append('Trend 15m bullish')
        elif i15m['trend'] == 'bearish': score -= 15; reasons.append('Trend 15m bearish')
        if i1m['volume']['high_volume']: score += 20; reasons.append('Volume alto')
        bb = i1m['bollinger']
        if bb['price_position'] < 0.1: score += 15; reasons.append('Sotto banda BB')
        elif bb['price_position'] > 0.9: score -= 15; reasons.append('Sopra banda BB')
        strength = abs(score)
        direction = 'long' if score > 0 else ('short' if score < 0 else 'hold')
        if strength < self.MIN_STRENGTH: direction = 'hold'
        return {'direction': direction, 'strength': strength, 'type': 'scalp', 'reasons': reasons}

    def _medium(self, i15m, i1h) -> dict:
        score, reasons = 0, []
        if i1h['trend'] == 'bullish': score += 35; reasons.append('Trend 1h bullish')
        elif i1h['trend'] == 'bearish': score -= 35; reasons.append('Trend 1h bearish')
        rsi = i15m['rsi']
        if rsi < 30: score += 30; reasons.append(f'RSI 15m ipervenduto ({rsi:.1f})')
        elif rsi > 70: score -= 30; reasons.append(f'RSI 15m ipercomprato ({rsi:.1f})')
        if i1h['macd']['bullish_cross']: score += 25; reasons.append('MACD 1h rialzista')
        elif i1h['macd']['bearish_cross']: score -= 25; reasons.append('MACD 1h ribassista')
        if i15m['ema_9'] > i15m['ema_21'] > i15m['ema_50']: score += 20; reasons.append('EMA bullish 15m')
        elif i15m['ema_9'] < i15m['ema_21'] < i15m['ema_50']: score -= 20; reasons.append('EMA bearish 15m')
        strength = abs(score)
        direction = 'long' if score > 0 else ('short' if score < 0 else 'hold')
        if strength < self.MIN_STRENGTH: direction = 'hold'
        return {'direction': direction, 'strength': strength, 'type': 'medium', 'reasons': reasons}

signal_engine = SignalEngine()
