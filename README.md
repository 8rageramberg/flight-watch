# flight-watch

Overvåker flere flysøk samtidig (Lisboa i høst, Japan om et halvt år, hva som
helst), rangerer treffene etter en vektet "hva koster dette deg egentlig"-logikk,
og sender de beste til Telegram 2x daglig. Gratis fra ende til ende: ingen
betalt API, ingen server.

## Filstruktur

| Fil | Hva den gjør |
| --- | --- |
| `config.py` | **Alt du normalt vil endre.** Søkene, datovinduene, reglene. |
| `scoring.py` | Harde filtre + vektet rangering. Vektene er dokumentert i koden. |
| `models.py` | Regner ut reisetid, mellomlandinger osv. fra Google-dataen. |
| `notify.py` | Formatering + Telegram-utsending. |
| `flight_watch.py` | Limet: kjører søkene, sorterer, sender. |
| `test_scoring.py` | Tester logikken mot oppdiktede reiser. Ingen nett-tilgang nødvendig. |

## Kom i gang

1. **Telegram-bot:** send `/newbot` til [@BotFather](https://t.me/BotFather) →
   du får en token.
2. **Chat-ID:** send en melding til boten din, åpne så
   `https://api.telegram.org/bot<TOKEN>/getUpdates` og finn `"chat":{"id":...}`.
3. **Push til et (gjerne privat) GitHub-repo.**
4. **Secrets:** Settings → Secrets and variables → Actions → legg inn
   `TELEGRAM_BOT_TOKEN` og `TELEGRAM_CHAT_ID`.
5. **Test:** Actions → "Flight watch" → Run workflow.

Lokalt, uten å spamme deg selv:

```bash
pip install -r requirements.txt
python test_scoring.py           # se hvordan logikken oppfører seg
python flight_watch.py --dry-run # ekte søk, men skriver til terminalen
python flight_watch.py --only lisboa
```

## Legge til et nytt søk

Kopier et `Search(...)` i `config.py`. Alt er navngitte felter:

```python
Search(
    name="Tokyo – vinterferie",
    origins=["OSL"],
    destinations=["HND", "NRT"],       # begge sjekkes
    window=DateWindow(
        start=date(2027, 2, 5),
        end=date(2027, 2, 26),         # siste mulige AVREISE
        trip_lengths=[12, 14],         # netter borte
        step_days=4,                   # sjekk hver 4. dag i vinduet
        weekdays=[3, 4, 5],            # valgfritt: kun tor/fre/lør
        latest_return=None,            # valgfritt: må være hjemme innen
    ),
    limits=LONGHAUL_LIMITS,
    weights=LONGHAUL_WEIGHTS,
    enabled=False,
    notify_when_empty=False,           # ikke mas hver dag i et halvt år
)
```

`DateWindow.search_count` forteller deg hvor mange søk kombinasjonen gir før du
setter den i gang – hold deg gjerne under ~40 per søk (se rate limiting under).

## Hvordan rangeringen fungerer

**Trinn 1 – harde filtre.** Kaster reiser som bare er tull, uansett pris:
mer enn 2 mellomlandinger, overganger så korte at du ikke rekker dem, og
regler av typen "er reisen over 10 timer, må den koste under 1000 kr".
Disse ligger i `EUROPE_LIMITS` / `LONGHAUL_LIMITS` i `config.py`.

**Trinn 2 – vektet kostnad.** Alt som overlever måles i kroner: prisen pluss
et påslag for hver ting som gjør reisen kjipere.

| Ulempe | Påslag |
| --- | --- |
| Hver time lengre enn den raskeste reisen funnet | 110 kr |
| 1 / 2 / 3 mellomlandinger | 300 / 1100 / 2600 kr |
| Overgang under 1,25 t | 450 kr |
| Hver time mellomlanding utover 3 t | 130 kr |
| Mellomlanding over 7 t (må sove på flyplassen) | +700 kr |
| Avgang før 07 eller ankomst etter 23 | 350 kr |

Direkte og billig vinner dermed automatisk, mens en 2-stopps maratonreise må
være markant billigere for å slå den.

**Kupp-unntaket:** du tåler åpenbart mer styr for 680 kr enn for 2400 kr.
Derfor halveres hele påslaget når prisen nærmer seg bunnivået på ruten
(under ~55 % av typisk pris), med jevn overgang imellom. Det er dette som gjør
at en 680-kroners 2-stopper faktisk kan gå til topps, mens en 2900-kroners
2-stopper ikke gjør det.

**Referansepunktene regnes ut fra dagens faktiske søkeresultater**, ikke
hardkodet. "Raskeste reise" og "typisk pris" betyr noe helt annet for Tokyo
enn for Lisboa, og logikken tilpasser seg selv.

Meldingen viser regnestykket, så du kan se hvorfor noe havnet der det havnet:

```
1. 680 kr · 2 stopp · 10.5t · 7 netter
   fre 25.09 → fre 02.10 · OSL-BER-MAD-LIS · Ryanair, Iberia
   vektet: 1560 kr — +6.0t vs raskeste (+330), 2 mellomlanding(er) (+550)
   [kuppabatt: påslag teller 50%]
   📉 -340 kr siden forrige kjøring
```

## Justere vektene

Kjør `python test_scoring.py` etter hver endring. Den kjører logikken mot et
sett oppdiktede reiser – inkludert bevisst absurde, som en 3-stopper til
520 kr og en med 9 timers nattopphold – og viser hva som filtreres bort og
hvordan resten rangeres. Du ser effekten umiddelbart, uten å vente på et ekte
Google-søk. Nederst ligger noen `assert`-er som fanger opp om du har justert
deg inn i noe ulogisk (f.eks. at direkte taper mot 2 stopp til samme pris).

## Kjente begrensninger – les disse

- **Rundtur-metrikkene gjelder utreisen.** Google Flights viser utreisealternativer
  med totalprisen for hele rundturen, og det er den strukturen biblioteket
  leser. Reisetid, mellomlandinger og klokkeslett i meldingen beskriver altså
  utreisen, mens prisen er for tur/retur. Hjemreisen kan i prinsippet være
  verre enn utreisen. Vil du ha eksakt kontroll på begge retninger, må du
  søke hver vei som `trip="one-way"` – si fra til Claude Code, det er en
  overkommelig endring i `flight_watch.py`.
- **`fast-flights` er en uoffisiell scraper**, ikke et offisielt API. Det er
  derfor det er gratis. Google kan endre siden sin og knekke biblioteket, og
  forespørsler fra GitHub Actions' delte datasenter-IP-er blir lettere
  rate-limitet enn fra hjemme-IP-en din. Scriptet legger inn 1,5–4 sekunders
  tilfeldig pause mellom hvert søk for å dempe dette. Følg med i
  Actions-loggen om jobben begynner å feile jevnlig. Plan B: proxy
  (`get_flights(query, proxy=...)` støttes direkte) eller bytte datakilde til
  en billig betalt wrapper (SerpApi / SearchApi.io har Google
  Flights-endepunkter). Bare `query_one()` må skrives om.
- **Norske lavprisselskaper** (Norwegian, Widerøe m.fl.) er ikke alltid
  fullstendig representert i Google Flights-data på grunn av
  distribusjonsavtaler. Dette fanger det aller meste, men ikke garantert
  hver eneste kampanje.
- **Prishistorikken** (`state.json`) lagrer bare beste pris per søk fra forrige
  kjøring, og committes tilbake til repoet av workflowen. Slett filen for å
  nullstille.

## Kostnad

0 kr. Hver kjøring tar typisk 2–5 minutter avhengig av antall
datokombinasjoner, godt innenfor GitHub Actions' gratisnivå.
