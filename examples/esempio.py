"""Uso come libreria: registro fiscale, zainetto, piano di fine anno e confronto tra veicoli."""

from datetime import date

from fiscale_investimenti import (
    Movimento,
    RegimeAmministrato,
    Strumento,
    Tipo,
    Zainetto,
    confronto_veicoli,
    piano_recupero,
)

strumenti = {s.nome: s for s in [
    Strumento("ETF Mondo", Tipo.ETF),
    Strumento("ETC Oro", Tipo.ETC),
    Strumento("BTP 2033", Tipo.TITOLO_STATO),
]}

# minusvalenze portate da un'altra banca: 4.000 € realizzate nel 2022 (scadono il 31/12/2026)
motore = RegimeAmministrato(strumenti, Zainetto({2022: 4_000.0}))
motore.processa([
    Movimento(date(2024, 1, 10), "acquisto", "ETF Mondo", 100, 80.0, commissioni=9.5),
    Movimento(date(2024, 1, 10), "acquisto", "ETC Oro", 50, 190.0, commissioni=9.5),
    Movimento(date(2024, 1, 10), "acquisto", "BTP 2033", 100, 92.0, commissioni=9.5),
    Movimento(date(2025, 3, 1), "cedola", "BTP 2033", importo=350.0),            # 12,5%
    Movimento(date(2026, 6, 15), "vendita", "ETF Mondo", 50, 115.0, commissioni=9.5),  # 26% pieno
])
print(motore.registro[["data", "strumento", "operazione", "categoria", "reddito", "imposta", "zainetto"]])
print("Zainetto per scadenza:", motore.zainetto.per_scadenza(2026))

# entro il 31 dicembre: quali plusvalenze realizzare per non perdere le minusvalenze del 2022?
prezzi = {"ETF Mondo": 118.0, "ETC Oro": 345.0, "BTP 2033": 99.2}
piano = piano_recupero(motore.posizioni, prezzi, strumenti, motore.zainetto, 2026)
print(piano.tabella()[["strumento", "quantita", "controvalore", "recuperato", "costo"]])
print(f"Recuperate {piano.recuperato:,.0f} €, imposta futura evitata {piano.risparmio:,.0f} €")

# lo stesso guadagno di 10.000 € con 4.000 € di zainetto, su veicoli diversi
print(confronto_veicoli(10_000, 4_000)[["categoria", "imposta", "aliquota effettiva"]])
