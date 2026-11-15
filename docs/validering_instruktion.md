# Validering af screeningen (protokollens punkt 10) – runde 2

**Fil:** `data/validate/2026-10-31/validation_sheet.csv` (30 nye repos, 10 pr. platform, ingen fra runde 1). Åbn den i Numbers eller Excel. **Eksportér den som CSV** (Arkiv → Eksportér til → CSV) til samme navn, så scoringen kan læse den.

## Sådan gør du
1. Åbn linket i kolonnen `url`. Det viser repoet ved præcis den commit, koden analyserede.
2. Besvar de tre spørgsmål med `ja`, `nej` eller `uklar`. Vurdér selv ud fra repoet, og gæt ikke på, hvad koden har sagt.
3. Skriv en kort begrundelse i `note`, især ved `nej` og `uklar`. Ved `backend_ok = ja` skriver du stien til mappen eller filen med server-koden. Skriv ingen kodeuddrag.

| Kolonne | Spørgsmål | Hvad du kigger efter |
|---|---|---|
| `platform_ok` | Er repoet lavet med den platform, der står i `platform`? | Lovable: commits fra Lovables bot (`gpt-engineer-app[bot]` / `lovable-dev[bot]`). Replit: commits fra Replit Agent. Bolt.new: en `.bolt/`-mappe i roden. |
| `web_not_mobile` | Er det en webapp og ikke en mobilapp? | `nej`, hvis der findes en `app.json` med `"expo"` eller en `eas.json` (Expo-mobilapp). |
| `backend_ok` | Har repoet **server-side-kode** på mindst ca. 50 linjer, uanset hvor den ligger? | Se definitionen herunder. Kan du ikke afgøre det inden for ca. 5 minutter, svarer du `uklar`. |

## Hvad er server-side-kode?
Det er kode, der kører på en server eller i en cloud-funktion og aldrig sendes til brugerens browser.

**Tæller med (eksempler):**
- Supabase Edge Functions: `supabase/functions/<navn>/index.ts`, typisk med `Deno.serve(...)` eller `serve(...)`.
- En Node-server: Express, Fastify, Hono eller Koa, typisk med `app.get(...)`, `app.post(...)` eller `app.listen(...)`, fx i `server/`, `backend/`, `api/` eller `artifacts/api-server/`.
- Serverless-funktioner: `netlify/functions/`, `api/` (Vercel) eller `functions/` (Firebase og Cloudflare).
- TanStack Start: filer, der hedder `*.server.ts` eller `*.functions.ts`, eller kald til `createServerFn(...)`.
- En Python-backend: Flask, FastAPI eller Django, fx `app.py` eller `main.py` med `@app.route` / `@app.get`.

**Tæller ikke med:**
- React-komponenter, sider og hooks (`.tsx`/`.jsx` i `src/components`, `src/pages`, `src/hooks`). De kører i browseren.
- Frontend-kode, der *kalder* en backend: `supabase.from(...)`, `fetch("/api/...")` og `src/integrations/supabase/client.ts`. Kaldet sker fra browseren. Det er ikke selve serveren.
- Databaseskemaer og migrationer (`supabase/migrations/*.sql`), konfiguration (`vite.config.ts`, `package.json`) og typedefinitioner (`types.ts`).
- Mockups og sandkasser (fx `artifacts/mockup-sandbox`).

## Bagefter
Kør `docker compose run --rm pipeline validate --freeze-date 2026-10-31 --score`. Det giver overensstemmelsen pr. platform og spørgsmål i `validation_agreement.csv` og listen over uenigheder i `validation_disagreements.csv`.
