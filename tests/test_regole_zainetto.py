import pytest

from fiscale_investimenti.regole import (
    ALIQUOTA,
    QUOTA_IMPONIBILE_STATO,
    Tipo,
    aliquota_effettiva,
    commissione,
    fattore_imponibile,
    ultimo_anno_utile,
)
from fiscale_investimenti.strumenti import Strumento
from fiscale_investimenti.zainetto import Zainetto


def test_aliquote_e_quota_titoli_di_stato():
    assert QUOTA_IMPONIBILE_STATO == pytest.approx(0.4808, abs=1e-4)
    assert aliquota_effettiva(0.0) == pytest.approx(0.26)
    assert aliquota_effettiva(1.0) == pytest.approx(0.125)
    # ETF con il 65% di titoli di Stato: media pesata delle due aliquote
    assert aliquota_effettiva(0.65) == pytest.approx(0.35 * 0.26 + 0.65 * 0.125)
    with pytest.raises(ValueError):
        fattore_imponibile(1.2)


def test_classificazione_degli_strumenti():
    etf = Strumento("ETF", Tipo.ETF)
    assert not etf.plus_compensabili and etf.regola.minusvalenze == "Redditi diversi"
    assert Strumento("ETC", "etc").plus_compensabili
    cert = Strumento("Cert", Tipo.CERTIFICATE)
    assert cert.regola.flussi == "Redditi diversi"           # i premi assorbono lo zainetto
    btp = Strumento("BTP", Tipo.TITOLO_STATO, quota_stato=0.3)
    assert btp.quota == 1.0 and btp.aliquota == pytest.approx(0.125)
    assert Strumento("Az", Tipo.AZIONE_IT).regola.tobin and not Strumento("Az", Tipo.AZIONE_ESTERA).regola.tobin


def test_commissioni_con_minimo_e_massimo():
    assert commissione(500) == 2.95
    assert commissione(5_000) == pytest.approx(9.5)
    assert commissione(50_000) == 19.0
    assert commissione(0) == 0.0


def test_scadenza_al_quarto_anno_successivo():
    z = Zainetto()
    z.aggiungi(2022, 1000)
    assert ultimo_anno_utile(2022) == 2026
    assert z.saldo(2026) == 1000 and z.in_scadenza(2026) == 1000
    assert z.saldo(2027) == 0
    assert z.per_scadenza(2025) == {2026: 1000}
    assert z.elimina_scadute(2026) == {}
    assert z.elimina_scadute(2027) == {2022: 1000} and z.residui == {}


def test_compensazione_dalla_minusvalenza_piu_vecchia():
    z = Zainetto()
    z.aggiungi(2024, 300)
    z.aggiungi(2022, 500)
    z.aggiungi(2025, 200)
    usato, da = z.compensa(650, 2026)
    assert usato == 650 and da == {2022: 500, 2024: 150}
    assert z.validi(2026) == {2024: 150, 2025: 200}
    usato, _ = z.compensa(1_000, 2026)
    assert usato == pytest.approx(350) and z.saldo(2026) == pytest.approx(0)


def test_minusvalenze_scadute_non_compensano():
    z = Zainetto({2020: 1000, 2023: 100})
    usato, da = z.compensa(500, 2026)
    assert usato == 100 and da == {2023: 100}
    assert z.residui[2020] == 1000                           # non toccata: era già scaduta
    with pytest.raises(ValueError):
        z.aggiungi(2026, -1)


def test_aliquota_costante():
    assert ALIQUOTA == 0.26
