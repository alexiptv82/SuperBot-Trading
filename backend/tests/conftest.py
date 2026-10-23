"""Impostazioni comuni dei test.

DESK_MACRO_FETCH=0: i test non devono MAI scaricare il calendario macro vero (la rete e' lenta o assente, e se la
CI girasse durante un CPI vero il risultato dei test cambierebbe). I test del calendario passano dati finti.

DESK_DAILY_FETCH=0: `cli.daily_bars` non scarica MAI le barre giornaliere vere (4 chiamate per simbolo); i test che
provano lo scarico lo riattivano e passano un `opener` finto."""
import os

os.environ["DESK_MACRO_FETCH"] = "0"
os.environ["DESK_DAILY_FETCH"] = "0"

# Unit tests use synthetic responses: fail closed before any real socket connection.
import sys


def _block_test_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise OSError("TEST_NETWORK_DISABLED")


sys.addaudithook(_block_test_network)
