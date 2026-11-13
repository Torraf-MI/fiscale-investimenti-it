from datetime import date

import pytest

from fiscale_investimenti import dati
from fiscale_investimenti.motore import Movimento, Posizione, RegimeAmministrato
from fiscale_investimenti.pianificazione import (
    Costi,
    confronto_veicoli,
    imposta_per_ordine,
    latenti,
    piano_recupero,
    valore_realizzo_perdita,
)
from fiscale_investimenti.regole import QUOTA_IMPONIBILE_STATO, Tipo
from fiscale_investimenti.strumenti import Strumento
from fiscale_investimenti.zainetto import Zainetto

S = {s.nome: s for s in [Strumento("Oro", Tipo.ETC), Strumento("Azione", Tipo.AZIONE_IT),
                         Strumento("ETF", Tipo.ETF), Strumento("BTP", Tipo.TITOLO_STATO)]}
POS = {"Oro": Posizione(10, 100), "Azione": Posizione(1000, 9), "ETF": Posizione(100, 50), "BTP": Posizione(100, 90)}
PREZZI = {"Oro": 200, "Azione": 10, "ETF": 80, "BTP": 100}


def test_latenti_e_categorie():
    lat = latenti(POS, PREZZI, S)
    assert lat.loc["Oro", "latente"] == 1000 and lat.loc["Oro", "compensabile"]
    assert not lat.loc["ETF", "compensabile"] and lat.loc["ETF", "categoria"] == "Redditi di capitale"
    assert lat.loc["BTP", "imponibile"] == pytest.approx(1000 * QUOTA_IMPONIBILE_STATO)


def test_piano_sceglie_prima_lo_strumento_piu_efficiente():
    z = Zainetto({2022: 600.0})
    p = piano_recupero(POS, PREZZI, S, z, 2026)
    assert p.obiettivo == 600 and p.recuperato == pytest.approx(600)
    assert [a.strumento for a in p.azioni] == ["Oro"]          # 50% di plusvalenza per euro venduto
    assert p.azioni[0].quantita == 6 and p.azioni[0].costo_medio_dopo > 100
    assert p.perso == 0 and p.risparmio == pytest.approx(0.26 * 600)
    assert p.valore_attuale(5, 0.03) < p.risparmio


def test_piano_usa_i_titoli_di_stato_al_48_per_cento_e_segnala_le_perdite():
    z = Zainetto({2022: 3000.0})
    p = piano_recupero(POS, PREZZI, S, z, 2026)
    assert [a.strumento for a in p.azioni] == ["Oro", "Azione", "BTP"]
    btp = p.azioni[-1]
    assert btp.imponibile == pytest.approx(btp.plusvalenza * QUOTA_IMPONIBILE_STATO)
    assert p.capacita == pytest.approx(1000 + 1000 + 1000 * QUOTA_IMPONIBILE_STATO)
    assert p.recuperato == pytest.approx(p.capacita) and p.perso == pytest.approx(3000 - p.capacita)


def test_eseguire_il_piano_non_costa_imposte_e_svuota_le_scadenze():
    m = RegimeAmministrato(S, Zainetto({2022: 1500.0, 2024: 400.0}))
    for n, p in POS.items():
        m.esegui(Movimento(date(2025, 1, 2), "acquisto", n, p.quantita, p.costo_medio))
    piano = piano_recupero(m.posizioni, PREZZI, S, m.zainetto, 2026, Costi())
    for a in piano.azioni:
        r = m.esegui(Movimento(date(2026, 12, 15), "vendita", a.strumento, a.quantita, a.prezzo))
        m.esegui(Movimento(date(2026, 12, 15), "acquisto", a.strumento, a.quantita, a.prezzo))
        assert r["imposta"] == pytest.approx(0, abs=0.05 * 0.26)   # al più qualche centesimo di arrotondamento
    assert m.zainetto.in_scadenza(2026) == pytest.approx(0, abs=1e-6)
    assert m.zainetto.saldo(2026) == pytest.approx(400, abs=60)   # le ultime unità arrotondate usano il 2024


def test_nessuna_scadenza_nessuna_azione():
    p = piano_recupero(POS, PREZZI, S, Zainetto({2025: 500.0}), 2026)
    assert p.azioni == [] and p.obiettivo == 0


def test_costi_e_tobin_tax():
    c = Costi(riacquisto_stesso_giorno=False)
    az = S["Azione"]
    assert c.operazione(10_000, az) == pytest.approx(19 + 19 + 0.001 * 10_000 + 10)
    assert Costi().operazione(10_000, az) == pytest.approx(19 + 19 + 10)


def test_ordine_e_valore_della_minusvalenza():
    assert imposta_per_ordine(1000, 1500) == {"Prima la plusvalenza": 390.0, "Prima la minusvalenza": 130.0}
    etf = S["ETF"]
    # se la minusvalenza non verrà mai usata, realizzare la perdita di un ETF fa solo pagare più imposte dopo
    assert valore_realizzo_perdita(1000, etf, 0.0, 1, 5) < 0
    assert valore_realizzo_perdita(1000, etf, 1.0, 1, 5) > 0
    assert valore_realizzo_perdita(1000, etf, 1.0, 5, 5) == pytest.approx(0)


def test_confronto_veicoli():
    v = confronto_veicoli(10_000, 4_000)
    assert v.loc["ETF azionario", "imposta"] == pytest.approx(2_600)
    assert v.loc["Azioni, ETC, certificates", "imposta"] == pytest.approx(0.26 * 6_000)
    assert v.loc["ETF di titoli di Stato", "imposta"] == pytest.approx(1_250)
    assert v.loc["Titoli di Stato diretti", "zainetto usato"] == pytest.approx(4_000)
    atteso = 0.26 * (10_000 * QUOTA_IMPONIBILE_STATO - 4_000)
    assert v.loc["Titoli di Stato diretti", "imposta"] == pytest.approx(atteso)
    assert (confronto_veicoli(-1_000, 4_000)["imposta"] == 0).all()


def test_piano_sul_caso_dimostrativo(motore_demo):
    p = piano_recupero(motore_demo.posizioni, dati.PREZZI_OGGI, dati.strumenti_dimostrativi(),
                       motore_demo.zainetto, 2026)
    assert p.perso == pytest.approx(0) and p.azioni[0].strumento == dati.ORO
