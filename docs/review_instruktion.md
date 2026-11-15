# Manuel vurdering af fund (TP/FP)

**Filer** (i `data/review/2026-10-31/`):
- `review_sheet.csv`: 120 fund til forfatter.
- `review_sheet_coder2.csv`: 30 af de samme fund til andenkoderen, i en anden rækkefølge.

Åbn arket i Numbers eller Excel, og **eksportér det som CSV** 

## Sådan gør forfatter
1. Åbn linket i `url`. Det viser filen ved præcis den commit, der blev scannet, med linjen markeret.
2. Læs `title` (hvad reglen leder efter), `message` (værktøjets forklaring) og `cwe`.
3. Kig på koden omkring linjen. Følg om nødvendigt, hvor værdierne kommer fra, men brug højst ca. 5 minutter.
4. Skriv én etiket i `label`: `TP`, `FP` eller `uklar`. Skriv en kort begrundelse i `note`, især ved `FP` og `uklar`. **Kopiér ingen kode** ind i arket.

| Etiket | Betydning |
|---|---|
| `TP` | Svagheden, som `title`/`cwe` beskriver, findes faktisk på dette sted. |
| `FP` | Den gør ikke. Værktøjet har matchet et mønster, men svagheden er der ikke. |
| `uklar` | Det kan ikke afgøres inden for ca. 5 minutter. |

Du vurderer **kun, om svagheden er til stede**. Du vurderer ikke, om en angriber reelt kan udnytte den, og heller ikke hvor alvorlig den er.

## Hjælp til de hyppigste regler (vejledning, ikke facit)
- **Usikker tilfældighed (CWE-338, `Math.random`):** `TP`, hvis værdien bruges til noget, der skal være hemmeligt eller ikke må kunne gættes: tokens, passwords, nøgler, session- eller invitations-ID'er, OTP-koder. `FP`, hvis den bruges til UI, animationer, demodata, farver eller ID'er uden sikkerhedsbetydning.
- **SSRF (CWE-918):** `TP`, hvis en URL, som brugeren kan påvirke (request-parametre, body, headers), hentes server-side uden en tilladelsesliste. `FP`, hvis URL'en er konstant eller kommer fra konfiguration/miljøvariabler, eller hvis koden kører i browseren.
- **XSS (CWE-79), fx `dangerouslySetInnerHTML`:** `TP`, hvis indholdet kan komme fra brugere eller eksterne data uden sanering. `FP`, hvis indholdet er statisk eller saneret (fx DOMPurify).
- **Filsti fra variabel (CWE-22):** `TP`, hvis stien kan påvirkes af brugerinput uden kontrol. `FP`, hvis den kun bygges af konstanter eller konfiguration.
- **Manglende rate limiting (CWE-770/307):** `TP`, hvis route-handleren gør noget dyrt (database, fil, ekstern API, login) og der ikke findes rate limiting på appen eller routen. `FP`, hvis der findes rate limiting et andet sted, som dækker routen.
- **Log injection (CWE-117):** `TP`, hvis brugerkontrollerede data skrives til loggen uden at linjeskift fjernes. `FP`, hvis værdien ikke kan kontrolleres af brugeren.
- **Stack trace eller fejlbesked til brugeren (CWE-209/497):** `TP`, hvis fejlbeskeden eller stacken sendes tilbage i HTTP-svaret. `FP`, hvis den kun logges server-side.

Ved andre regler: Læs `title`/`message`, og afgør, om det, reglen beskriver, faktisk sker i koden.

## Bagefter
Kør `docker compose run --rm pipeline review --freeze-date 2026-10-31 --score`. Kommandoen giver:
- `review_precision.csv`: præcisionen TP/(TP+FP) pr. platform og værktøj, med et 95 %-interval (Wilson).
- `review_by_rule.csv`: etiketterne pr. regel.
- `review_agreement.json`: enigheden og Cohen's kappa mellem forfatter og andenkoderen.
