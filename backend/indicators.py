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
            'volume': self.volume_analysis(),
        }
