"""Suite del ritorno al codice del 13/10 (9fa667f). Gira SOLO su questo codice: i test delle versioni successive
(capitale V1, Salvadanaio, DeepSeek, opportunita' additive...) non si applicano e restano fuori da questa cartella."""
import os
import sys

os.environ.setdefault("DESK_MACRO_FETCH", "0")
os.environ.setdefault("DESK_DAILY_FETCH", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
