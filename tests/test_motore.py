from datetime import date

import pytest

from fiscale_investimenti.motore import Movimento, RegimeAmministrato, da_dataframe
from fiscale_investimenti.regole import QUOTA_IMPONIBILE_STATO, Tipo
from fiscale_investimenti.strumenti import Strumento
from fiscale_investimenti.zainetto import Zainetto

S = {s.nome: s for s in [
    Strumento("Azione", Tipo.AZIONE_IT),
    Strumento("Azione USA", Tipo.AZIONE_ESTERA, ritenuta_estera=0.15),
    Strumento("ETF", Tipo.ETF),
    Strumento("ETF Gov", Tipo.ETF, quota_stato=0.5),
    Strumento("BTP", Tipo.TITOLO_STATO),
    Strumento("Cert", Tipo.CERTIFICATE),
]}


def mov(d, op, nome, q=0.0, p=0.0, importo=0.0, c=0.0):
    return Movimento(date.fromisoformat(d), op, nome, q, p, importo, c)


def test_costo_medio_ponderato_con_commissioni():
    m = RegimeAmministrato(S).processa([mov("2025-01-10", "acquisto", "Azione", 100, 10, c=5),
                                        mov("2025-03-10", "acquisto", "Azione", 300, 14, c=7)])
    p = m.posizioni["Azione"]
    assert p.quantita == 400 and p.costo_medio == pytest.approx((1005 + 4207) / 400)
    r = m.esegui(mov("2025-06-10", "vendita", "Azione", 100, 15, c=4))
    assert r["reddito"] == pytest.approx(1500 - 4 - 100 * (5212 / 400))
    assert m.posizioni["Azione"].costo_medio == pytest.approx(5212 / 400)   # la vendita non cambia il costo medio


def test_plusvalenza_compensata_con_lo_zainetto():
    m = RegimeAmministrato(S, Zainetto({2024: 300.0}))
    m.processa([mov("2025-01-10", "acquisto", "Azione", 100, 10), mov("2025-06-10", "vendita", "Azione", 100, 15)])
    r = m.righe[-1]
    assert r["compensato"] == 300 and r["imposta"] == pytest.approx(0.26 * 200)
    assert m.zainetto.saldo(2025) == 0


def test_plusvalenza_etf_non_compensabile_minusvalenza_si():
    m = RegimeAmministrato(S, Zainetto({2024: 10_000.0}))
    m.processa([mov("2025-01-10", "acquisto", "ETF", 100, 100), mov("2025-06-10", "vendita", "ETF", 50, 120)])
    r = m.righe[-1]
    assert r["categoria"] == "Redditi di capitale" and r["compensato"] == 0
    assert r["imposta"] == pytest.approx(0.26 * 1000) and m.zainetto.saldo(2025) == 10_000
    m.esegui(mov("2025-09-10", "vendita", "ETF", 50, 90))
    assert m.righe[-1]["categoria"] == "Redditi diversi"
    assert m.zainetto.residui[2025] == pytest.approx(500)


def test_titoli_di_stato_al_48_per_cento():
    m = RegimeAmministrato(S, Zainetto({2024: 1000.0}))
    m.processa([mov("2025-01-10", "acquisto", "BTP", 100, 90), mov("2025-03-01", "cedola", "BTP", importo=400),
                mov("2025-06-10", "vendita", "BTP", 100, 100)])
    cedola, vendita = m.righe[1], m.righe[2]
    assert cedola["imposta"] == pytest.approx(0.125 * 400)
    assert vendita["imponibile"] == pytest.approx(1000 * QUOTA_IMPONIBILE_STATO)
    assert vendita["compensato"] == pytest.approx(480.77, abs=0.01) and vendita["imposta"] == 0
    assert m.zainetto.saldo(2025) == pytest.approx(1000 - 480.77, abs=0.01)
    # minusvalenza di un ETF con metà titoli di Stato: entra nello zainetto ridotta
    m.processa([mov("2025-07-01", "acquisto", "ETF Gov", 10, 100), mov("2025-08-01", "vendita", "ETF Gov", 10, 80)])
    assert m.righe[-1]["minus_generate"] == pytest.approx(200 * (0.5 + 0.5 * QUOTA_IMPONIBILE_STATO))


def test_dividendo_estero_e_premio_certificate():
    m = RegimeAmministrato(S, Zainetto({2024: 50.0}))
    m.processa([mov("2025-01-10", "acquisto", "Azione USA", 10, 100), mov("2025-02-10", "acquisto", "Cert", 1, 100),
                mov("2025-05-10", "dividendo", "Azione USA", importo=100),
                mov("2025-06-10", "premio", "Cert", importo=80)])
    div, premio = m.righe[2], m.righe[3]
    assert div["ritenuta_estera"] == pytest.approx(15) and div["imposta"] == pytest.approx(0.26 * 85)
    assert premio["compensato"] == 50 and premio["imposta"] == pytest.approx(0.26 * 30)


def test_l_ordine_conta_minusvalenza_solo_sulle_plusvalenze_successive():
    base = [mov("2025-01-10", "acquisto", "Azione", 100, 10), mov("2025-01-10", "acquisto", "Cert", 100, 10)]
    prima_plus = RegimeAmministrato(S).processa(base + [mov("2025-03-10", "vendita", "Azione", 100, 12),
                                                        mov("2025-10-10", "vendita", "Cert", 100, 8)])
    prima_minus = RegimeAmministrato(S).processa(base + [mov("2025-03-10", "vendita", "Cert", 100, 8),
                                                         mov("2025-10-10", "vendita", "Azione", 100, 12)])
    assert prima_plus.registro["imposta"].sum() == pytest.approx(52)
    assert prima_minus.registro["imposta"].sum() == pytest.approx(0)
    assert prima_plus.zainetto.saldo(2025) == pytest.approx(200)


def test_scadenza_al_cambio_d_anno():
    m = RegimeAmministrato(S, Zainetto({2021: 700.0, 2022: 100.0}))
    m.esegui(mov("2025-12-01", "acquisto", "Azione", 1, 10))
    assert m.zainetto.saldo(2025) == 800
    m.esegui(mov("2026-01-05", "acquisto", "Azione", 1, 10))
    assert [(s.anno_realizzo, s.importo) for s in m.scadute] == [(2021, 700.0)]
    assert m.riepilogo_annuo().loc[2025, "Minusvalenze scadute"] == 700


def test_errori():
    m = RegimeAmministrato(S)
    with pytest.raises(ValueError):
        m.esegui(mov("2025-01-10", "vendita", "Azione", 1, 10))
    with pytest.raises(KeyError):
        m.esegui(mov("2025-01-10", "acquisto", "Sconosciuto", 1, 10))
    with pytest.raises(ValueError):
        Movimento(date(2025, 1, 1), "regalo", "Azione")
    m.esegui(mov("2025-01-10", "acquisto", "Azione", 1, 10))
    with pytest.raises(ValueError):
        m.esegui(mov("2024-01-10", "acquisto", "Azione", 1, 10))


def test_caso_dimostrativo(motore_demo):
    m = motore_demo
    r = m.registro
    etf = r[(r["strumento"] == "ETF Obbligazionario Euro") & (r["operazione"] == "vendita")].iloc[0]
    assert etf["minus_generate"] == pytest.approx(-etf["reddito"] * (1 - 0.65 * (1 - QUOTA_IMPONIBILE_STATO)))
    # ogni euro di minusvalenza è stato usato, è ancora nello zainetto o è scaduto
    generate = r["minus_generate"].sum()
    usate = r["compensato"].sum()
    assert generate == pytest.approx(usate + m.zainetto.saldo(2026) + sum(s.importo for s in m.scadute))
    assert m.zainetto.in_scadenza(2026) > 6_000
    # la vendita dell'ETF azionario ha pagato il 26% pieno con lo zainetto pieno
    nc = m.imposte_non_compensate()
    assert (nc["operazione"] == "vendita").sum() == 1
    rie = m.riepilogo_annuo()
    assert rie["Imposte totali"].sum() == pytest.approx(r["imposta"].sum())


def test_da_dataframe(motore_demo):
    import pandas as pd

    df = pd.DataFrame({"data": ["2025-01-10"], "operazione": ["acquisto"], "strumento": ["Azione"],
                       "quantita": [3], "prezzo": [10]})
    (x,) = da_dataframe(df)
    assert x.quantita == 3 and x.commissioni == 0 and x.data == date(2025, 1, 10)
