"""Caso dimostrativo: il dossier titoli di una famiglia dal 2021 al novembre 2026.

La storia è costruita per mostrare le trappole tipiche del sistema italiano: nel 2022 un ETF obbligazionario e
un'azione tecnologica chiudono in perdita e riempiono lo zainetto; i premi di un certificate ne recuperano una parte;
nel 2026 la vendita di un ETF azionario in guadagno paga il 26% pieno mentre lo zainetto è pieno, e alla fine
dell'anno scadono le minusvalenze del 2022 rimaste. Nomi e prezzi sono di fantasia."""

from __future__ import annotations

from datetime import date

import pandas as pd

from .motore import Movimento
from .regole import Tipo, commissione
from .strumenti import Strumento

DATA_ANALISI = date(2026, 11, 12)

ETF_OBBL = "ETF Obbligazionario Euro"
BANCA = "Azioni Banca Italiana"
TECH = "Azioni Tecnologia USA"
CERT = "Certificate Cash Collect Banche"
ETF_MONDO = "ETF Azionario Mondo"
BTP = "BTP 2033 3,50%"
ORO = "ETC Oro fisico"
ENERGIA = "Azioni Energia Italia"
OBBL = "Obbligazione Industriale 2029 4%"
EMERGENTI = "ETF Azionario Emergenti"


def strumenti_dimostrativi() -> dict[str, Strumento]:
    lista = [
        Strumento(ETF_OBBL, Tipo.ETF, quota_stato=0.65, rendimento=0.025, volatilita=0.06, gruppo="obbligazioni"),
        Strumento(BANCA, Tipo.AZIONE_IT, rendimento=0.06, volatilita=0.26, flusso=0.06, spread=0.001),
        Strumento(TECH, Tipo.AZIONE_ESTERA, ritenuta_estera=0.15, rendimento=0.08, volatilita=0.28, flusso=0.007),
        Strumento(CERT, Tipo.CERTIFICATE, scadenza=date(2028, 3, 1), volatilita=0.10, flusso=0.078, spread=0.004),
        Strumento(ETF_MONDO, Tipo.ETF, rendimento=0.07, volatilita=0.16, spread=0.0005),
        Strumento(BTP, Tipo.TITOLO_STATO, cedola=0.035, scadenza=date(2033, 3, 1), volatilita=0.05,
                  gruppo="obbligazioni", spread=0.0015),
        Strumento(ORO, Tipo.ETC, rendimento=0.04, volatilita=0.15, gruppo="oro", spread=0.0008),
        Strumento(ENERGIA, Tipo.AZIONE_IT, rendimento=0.05, volatilita=0.24, flusso=0.05),
        Strumento(OBBL, Tipo.OBBLIGAZIONE, cedola=0.04, scadenza=date(2029, 6, 15), volatilita=0.025,
                  gruppo="obbligazioni", spread=0.003),
        Strumento(EMERGENTI, Tipo.ETF, rendimento=0.07, volatilita=0.20),
    ]
    return {s.nome: s for s in lista}


def _ordine(data: str, op: str, nome: str, q: float, prezzo: float) -> Movimento:
    return Movimento(date.fromisoformat(data), op, nome, q, prezzo, commissioni=round(commissione(q * prezzo), 2))


def _flusso(data: str, op: str, nome: str, importo: float) -> Movimento:
    return Movimento(date.fromisoformat(data), op, nome, importo=round(importo, 2))


def movimenti_dimostrativi() -> list[Movimento]:
    m = [
        _ordine("2021-03-15", "acquisto", ETF_OBBL, 1000, 100.00),
        _ordine("2021-06-10", "acquisto", BANCA, 2000, 10.00),
        _ordine("2022-02-07", "acquisto", TECH, 100, 150.00),
        _flusso("2022-05-23", "dividendo", BANCA, 2000 * 0.60),
        _flusso("2022-08-12", "dividendo", TECH, 100 * 0.92),
        _ordine("2022-10-14", "vendita", ETF_OBBL, 1000, 82.50),
        _ordine("2022-12-16", "vendita", TECH, 100, 105.00),
        _ordine("2023-03-01", "acquisto", CERT, 250, 100.00),
        _ordine("2023-05-08", "acquisto", ETF_MONDO, 600, 80.00),
        _flusso("2023-05-22", "dividendo", BANCA, 2000 * 0.70),
        _ordine("2023-07-12", "acquisto", BTP, 400, 92.00),
        _ordine("2024-01-15", "acquisto", ORO, 80, 190.00),
        _ordine("2024-03-04", "acquisto", ENERGIA, 1000, 12.00),
        _flusso("2024-05-20", "dividendo", BANCA, 2000 * 0.85),
        _ordine("2024-05-20", "acquisto", OBBL, 200, 97.00),
        _ordine("2024-09-20", "vendita", ENERGIA, 1000, 9.20),
        _ordine("2025-01-20", "acquisto", EMERGENTI, 300, 50.00),
        _ordine("2025-04-08", "vendita", EMERGENTI, 300, 41.00),
        _flusso("2025-05-19", "dividendo", BANCA, 2000 * 0.95),
        _ordine("2025-09-15", "vendita", BANCA, 500, 15.00),
        _flusso("2026-05-18", "dividendo", BANCA, 1500 * 1.00),
        _ordine("2026-06-15", "vendita", ETF_MONDO, 200, 112.00),
    ]
    # premi mensili del certificate (0,65% del nominale) da aprile 2023
    for d in pd.date_range("2023-04-01", "2026-11-01", freq="MS"):
        m.append(_flusso(d.date().isoformat(), "premio", CERT, 250 * 100 * 0.0065))
    # cedole semestrali del BTP (1 marzo, 1 settembre) e annuali dell'obbligazione (15 giugno)
    for a in range(2023, 2027):
        for g in ("03-01", "09-01"):
            d = f"{a}-{g}"
            if "2023-07-12" < d <= DATA_ANALISI.isoformat():
                m.append(_flusso(d, "cedola", BTP, 400 * 100 * 0.0175))
        d = f"{a}-06-15"
        if "2024-05-20" < d <= DATA_ANALISI.isoformat():
            m.append(_flusso(d, "cedola", OBBL, 200 * 100 * 0.04))
    return sorted(m, key=lambda x: x.data)


PREZZI_OGGI = {BANCA: 17.40, CERT: 98.50, ETF_MONDO: 118.00, BTP: 99.20, ORO: 345.00, OBBL: 101.30}


def movimenti_dataframe(movimenti: list[Movimento]) -> pd.DataFrame:
    return pd.DataFrame([m.__dict__ for m in movimenti])
