import pytest

from fiscale_investimenti import configurazione, dati
from fiscale_investimenti.analisi import analizza
from fiscale_investimenti.motore import RegimeAmministrato


@pytest.fixture(scope="session")
def motore_demo():
    return RegimeAmministrato(dati.strumenti_dimostrativi()).processa(dati.movimenti_dimostrativi())


@pytest.fixture(scope="session")
def analisi_demo():
    cfg = configurazione.esempio()
    cfg.simulazione.scenari = 60
    return analizza(cfg)
