"""Fiscalità degli investimenti per le persone fisiche in Italia: redditi di capitale e redditi diversi, aliquote
26% e 12,5%, zainetto fiscale con le scadenze, piano di fine anno e tax-loss harvesting all'italiana."""

from .analisi import Analisi, analizza
from .motore import Movimento, Posizione, RegimeAmministrato, leggi_movimenti
from .pianificazione import Costi, confronto_veicoli, latenti, piano_recupero, valore_realizzo_perdita
from .regole import ALIQUOTA, ALIQUOTA_STATO, QUOTA_IMPONIBILE_STATO, Tipo, aliquota_effettiva, fattore_imponibile
from .simulazione import ParametriSimulazione, Simulatore
from .strumenti import Strumento
from .zainetto import Zainetto

__version__ = "0.1.0"
__all__ = ["ALIQUOTA", "ALIQUOTA_STATO", "QUOTA_IMPONIBILE_STATO", "Analisi", "Costi", "Movimento",
           "ParametriSimulazione", "Posizione", "RegimeAmministrato", "Simulatore", "Strumento", "Tipo", "Zainetto",
           "aliquota_effettiva", "analizza", "confronto_veicoli", "fattore_imponibile", "latenti", "leggi_movimenti",
           "piano_recupero", "valore_realizzo_perdita"]
