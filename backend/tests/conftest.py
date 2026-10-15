"""Impostazioni comuni dei test.

DESK_MACRO_FETCH=0: i test non devono MAI scaricare il calendario macro vero (la rete e' lenta o assente, e se la
CI girasse durante un CPI vero il risultato dei test cambierebbe). I test del calendario passano dati finti."""
import os

os.environ["DESK_MACRO_FETCH"] = "0"
