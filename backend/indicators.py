import pandas as pd
import numpy as np

class TechnicalIndicators:
    def __init__(self, ohlcv: list):
        if len(ohlcv) < 50:
            raise ValueError(f"Servono almeno 50 candele, ricevute: {len(ohlcv)}")
        self.df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], unit='ms')
        self.df = self.df.sort_values('timestamp').reset_index(drop=True)

    def rsi(self, period=14) -> float:
        delta = self.df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return float((100 - (100 / (1 + rs))).iloc[-1])

    def macd(self) -> dict:
        ema12 = self.df['close'].ewm(span=12).mean()
        ema26 = self.df['close'].ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        return {
            'macd': float(macd_line.iloc[-1]),
            'signal': float(signal_line.iloc[-1]),
            'histogram': float((macd_line - signal_line).iloc[-1]),
            'bullish_cross': bool(macd_line.iloc[-1] > signal_line.iloc[-1] and
                                  macd_line.iloc[-2] <= signal_line.iloc[-2]),
            'bearish_cross': bool(macd_line.iloc[-1] < signal_line.iloc[-1] and
                                  macd_line.iloc[-2] >= signal_line.iloc[-2]),
        }

    def ema(self, period: int) -> float:
        return float(self.df['close'].ewm(span=period).mean().iloc[-1])

    def bollinger_bands(self) -> dict:
        sma = self.df['close'].rolling(20).mean()
        std = self.df['close'].rolling(20).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        price = self.df['close'].iloc[-1]
        denom = upper.iloc[-1] - lower.iloc[-1]
        return {
            'upper': float(upper.iloc[-1]),
            'middle': float(sma.iloc[-1]),
            'lower': float(lower.iloc[-1]),
            'price_position': float((price - lower.iloc[-1]) / denom) if denom != 0 else 0.5,
            'squeeze': bool(denom / sma.iloc[-1] < 0.02),
        }

    def atr(self, period=14) -> float:
        hl = self.df['high'] - self.df['low']
        hc = (self.df['high'] - self.df['close'].shift()).abs()
        lc = (self.df['low'] - self.df['close'].shift()).abs()
        return float(pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(period).mean().iloc[-1])

    def adx(self, period=14) -> float:
        """Average Directional Index (Wilder). Misura la FORZA del trend
        (non la direzione): usato dal regime detector per distinguere un
        mercato in trend da uno laterale. La smoothing di Wilder è
        approssimata con una EMA ad alpha=1/period (adjust=False), la forma
        standard usata quando non si ha accesso alla formula ricorsiva
        esatta di Wilder su tutta la serie.
        """
        high, low, close = self.df['high'], self.df['low'], self.df['close']
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        hl = high - low
        hc = (high - close.shift()).abs()
        lc = (low - close.shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)

        alpha = 1.0 / period
        tr_s = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_dm_s = plus_dm.ewm(alpha=alpha, adjust=False).mean()
        minus_dm_s = minus_dm.ewm(alpha=alpha, adjust=False).mean()

        plus_di = 100 * (plus_dm_s / tr_s.replace(0, float('nan')))
        minus_di = 100 * (minus_dm_s / tr_s.replace(0, float('nan')))
        di_sum = (plus_di + minus_di).replace(0, float('nan'))
        dx = 100 * (plus_di - minus_di).abs() / di_sum
        adx_series = dx.ewm(alpha=alpha, adjust=False).mean()

        value = adx_series.iloc[-1]
        return float(value) if pd.notna(value) else 0.0

    def bbw(self) -> float:
        """Bollinger Band Width normalizzata: (upper-lower)/middle. Usata dal
        regime detector insieme all'ADX -- una BBW bassa indica un mercato
        compresso/laterale, coerente con un ADX basso."""
        bb = self.bollinger_bands()
        middle = bb['middle']
        return (bb['upper'] - bb['lower']) / middle if middle else 0.0

    def volume_analysis(self) -> dict:
        avg = self.df['volume'].rolling(20).mean().iloc[-1]
        cur = self.df['volume'].iloc[-1]
        return {'current': float(cur), 'average_20': float(avg),
                'ratio': float(cur / avg) if avg > 0 else 1.0,
                'high_volume': bool(cur > avg * 1.5)}

    def trend_direction(self) -> str:
        e9, e21, e50 = self.ema(9), self.ema(21), self.ema(50)
        price = float(self.df['close'].iloc[-1])
        if price > e9 > e21 > e50: return 'bullish'
        if price < e9 < e21 < e50: return 'bearish'
        return 'sideways'

    def vwap(self, period: int = 20) -> dict:
        """VWAP mobile (rolling, non ancorato a sessione) sul prezzo tipico
        (H+L+C)/3, con banda di deviazione in unita' di sigma (z-score).

        Usato da MeanReversionStrategy come ancora di prezzo alternativa
        alle sole Bollinger Band: la deviazione standard qui e' calcolata
        sulla serie (prezzo_tipico - vwap), quindi lo z-score risponde alla
        domanda "quanto e' lontano il prezzo dal suo VWAP recente, in unita'
        di dispersione recente" -- coerente con lo spirito mean-reversion
        (vedi trovato Qwen: 'VWAP +-k*sigma in MeanReversion').
        """
        typical = (self.df['high'] + self.df['low'] + self.df['close']) / 3.0
        vol = self.df['volume']
        rolling_pv = (typical * vol).rolling(period).sum()
        rolling_vol = vol.rolling(period).sum()
        vwap_series = rolling_pv / rolling_vol.replace(0, np.nan)

        dev = typical - vwap_series
        dev_std = dev.rolling(period).std()

        price = float(self.df['close'].iloc[-1])
        vwap_last = vwap_series.iloc[-1]
        std_last = dev_std.iloc[-1]

        vwap_value = float(vwap_last) if pd.notna(vwap_last) else price
        std_value = float(std_last) if pd.notna(std_last) and std_last > 0 else 0.0
        zscore = (price - vwap_value) / std_value if std_value > 0 else 0.0
        return {'value': vwap_value, 'std': std_value, 'zscore': float(zscore)}

    def realized_vol_ratio(self, short_period: int = 20, long_period: int = 50) -> float:
        """Rapporto tra volatilita' realizzata di breve periodo e di lungo
        periodo (deviazione standard dei log-return). Un valore > 1 indica
        un'espansione recente di volatilita' rispetto alla norma del
        periodo lungo; < 1 indica una compressione. Puramente informativo
        per ora (vedi trovato Qwen: 'realized volatility ratio multi-timeframe'),
        non ancora usato come filtro attivo su nessuna strategia.
        """
        log_ret = np.log(self.df['close'] / self.df['close'].shift(1))
        short_vol = log_ret.rolling(short_period).std().iloc[-1]
        long_vol = log_ret.rolling(long_period).std().iloc[-1]
        if pd.isna(short_vol) or pd.isna(long_vol) or long_vol <= 0:
            return 1.0
        return float(short_vol / long_vol)

    def compute_all(self) -> dict:
        rsi_val = self.rsi()
        return {
            'price': float(self.df['close'].iloc[-1]),
            'trend': self.trend_direction(),
            'rsi': rsi_val,
            'rsi_signal': 'oversold' if rsi_val < 30 else ('overbought' if rsi_val > 70 else 'neutral'),
            'macd': self.macd(),
            'ema_9': self.ema(9), 'ema_21': self.ema(21), 'ema_50': self.ema(50),
            'bollinger': self.bollinger_bands(),
            'atr': self.atr(),
            'adx': self.adx(),
            'bbw': self.bbw(),
            'vwap': self.vwap(),
            'realized_vol_ratio': self.realized_vol_ratio(),
            'volume': self.volume_analysis(),
        }
