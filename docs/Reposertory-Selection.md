| Platform | Endpoint | Query |
|---|---|---|
| Lovable | `GET /search/commits` | `author:lovable-dev[bot] author-date:<date>` |
| Replit | `GET /search/commits` | `committer:replit-agent author-date:<date>` |
| Bolt.new | `GET /search/repositories` | `"built with Bolt.new"`, `"bolt.new"`, `"built with bolt"`, `"made with bolt"`, `"created with bolt"`, `topic:bolt-new`, `topic:boltnew` |
| Bolt.new | `GET /search/code` | `path:.bolt filename:config.json`; `filename:package.json "vite-react-typescript-starter"`; `"Built with Bolt.new" filename:README.md` |
## Mobil-kriterium (låst 2026-10-31)

**Regel:** Et repo ekskluderes som mobil-app, hvis der et sted i filtræet findes
1. en `app.json` med en topniveau-nøgle `"expo"`, eller
2. en `eas.json`.

Ingen andre filer tæller (fravalgt: `build.gradle`, `pubspec.yaml`, `android/`, `ios/`, `capacitor.config.*`, `AndroidManifest.xml`, `app.config.js/ts`). Begrundelse: Reglen skal kun ramme platformenes egen mobil-output-type. En web-app, der er pakket ind med fx Capacitor, er stadig en web-kodebase og bliver i stikprøven.

**Dokumentation (hentet 2026-10-31):**
- Bolt.new bygger mobil-apps via Expo: "Bolt can build mobile apps using the Expo integration." Expo er den eneste mobil-vej, FAQ'en nævner. https://support.bolt.new/concepts/faq.md
- Replit Agent bygger mobil-apps med Expo: "Expo is what Agent uses to build your mobile app on Replit." https://docs.replit.com/learn/mobile/expo (sidetitel "Native Mobile Apps")
- Expo: `app.json` er Expo's app-konfiguration, og indholdet ligger under topniveau-nøglen `expo`. https://docs.expo.dev/workflow/configuration/ ("Configure with app config")
- Expo: `eas.json` er konfigurationen til EAS Build, med `android`- og `ios`-felter pr. build-profil. https://docs.expo.dev/build/eas-json/ ("Configure EAS Build with eas.json")

**Kendte begrænsninger (Threats):**
- Expo kan også bygge til web ("universal Android, iOS, and web app", docs.expo.dev). Reglen udelukker altså platformenes Expo-projekter som helhed, også hvis et af dem også kører som web.
- Et Expo-projekt, der kun har `app.config.js/ts` og ingen `app.json` eller `eas.json`, opdages ikke. Det fanges eventuelt af valideringsstikprøven (B5).

## Repo i flere platforme (låst 2026-10-31)

**Regel:** Et repo (`full_name`), der står i rammen for mere end én platform, ekskluderes fra alle platforme. Tjekket laves i kode, efter at rammerne er hentet og før blandingen.

## Spor af andre AI-værktøjer og vibe-platforme: kun variabler (låst 2026-10-31)

Ingen af disse ekskluderer et repo. Koden noterer pr. repo, hvilke filer der findes (hele filtræet), og andelen rapporteres pr. platform.

**`other_ai_tool` (værktøjsspecifikke filer, som ingen af de tre platforme dokumenterer, at de bruger):**
`.claude/` (Claude Code), `.cursor/` og `.cursorrules` (Cursor), `.windsurf/` og `.windsurfrules` (Windsurf), `.clinerules` (Cline), `.github/copilot-instructions.md` (GitHub Copilot), `GEMINI.md` (Gemini CLI), `.aider*` (Aider).

**`ambiguous_instructions` (instruktionsfiler, som platformene selv bruger, registreres for sig):**
`AGENTS.md` og `CLAUDE.md` (alle varianter af store og små bogstaver). Begrundelse: Lovable læser begge som instruktioner til sin egen agent (https://docs.lovable.dev/features/knowledge.md), og Bolt.new bruger `agents.md` automatisk (https://support.bolt.new/prompting/manage-context.md). Målt 2026-10-31: 9 af 11 `AGENTS.md` i forstudiets Lovable-kandidater begynder med `<!-- LOVABLE:BEGIN -->`.

**`other_platform` (filspor fra en af de to andre platforme):**
Lovable er `lovable-tagger` i `package.json`, Replit er `.replit` eller `replit.md`, og Bolt.new er `.bolt/`.

Platformens egne filer tæller ikke som spor for den platform selv. For Replit gælder det `.replit`, `replit.md` og `.agents/`, og for Bolt.new gælder det `.bolt/`.

## Seed (låst 2026-10-31)

**Regel:** Seedet er frysedatoen skrevet som heltal `YYYYMMDD`. Frysedatoen er den dag, rammen hentes og fryses. Fryses rammen fx 2026-11-03, er seedet `20261103`. Seedet logges i `docs/beslutningslog.md`, før blandingen køres. Det samme seed bruges til valideringsstikprøven.

---

## Samlet udvælgelsesprotokol (komplet 2026-10-31, fryses ved første kørsel)

1. **Periode:** 12 måneder bagud fra frysedatoen.
2. **Identifikation:**
   - Lovable og Replit (ændret 2026-10-31): commit-søgningerne i tabellen øverst i **tilfældige minutvinduer**. For hver dag i perioden trækkes ét tilfældigt minut i hver 2-timers blok (UTC), i alt 12 pr. dag, med seedet: `author-date:<start>..<start+59s>`. Vinduerne er de samme for begge platforme, og hvert vindue hentes helt. Vinduer, der rammer loftet på 1.000, logges. Begrundelse: Dagsvinduer gav kun ca. 3 % af Lovables commits (1.000 af 30.000–38.000 pr. dag), i GitHubs udokumenterede rækkefølge (målt 2026-10-31).
   - Bolt.new: repository- og kodesøgningerne i tabellen øverst, uden tidsvinduer.
   - Dubletter fjernes på `full_name`. De rå API-svar gemmes med tidsstempel, og rammen fryses.
3. **Repo i flere platforme:** Står et `full_name` i mere end én platforms ramme, ekskluderes det fra alle.
4. **Forfilter (metadata):** ikke en fork, ikke arkiveret, og `pushed_at` inden for perioden.
5. **Rækkefølge:** Rammen sorteres alfabetisk på `full_name` og blandes med `random.Random(seed).shuffle()`.
6. **Screening i den rækkefølge**, med kloning via `git clone --filter=blob:none`. Fejler en kloning, springes repoet over, og det logges.
   - Platformsspor findes: commits af `lovable-dev[bot]`, commits med committer `replit-agent`, eller `.bolt/` i roden.
   - Ikke en mobil-app (Expo-reglen ovenfor).
   - Backend-NLOC ≥ 50 (Lizard 1.24.3). Backend-mapperne `supabase/functions`, `server`, `api`, `backend`, `functions`, `netlify/functions` og `artifacts/api-server` (tilføjet 2026-11-01 efter piloten, Replit Agents monorepo-skabelon) skal ligge i roden. Derudover tæller filer, der hedder `*.server.<ext>` eller `*.functions.<ext>`, hvor som helst i træet (tilføjet 2026-11-01 efter valideringen: TanStack Starts dokumenterede konvention for server-kode, brugt i Lovables nyere skabelon). Filendelserne er `.ts/.js/.mjs/.cjs/.py`, og `node_modules`, `dist`, `build` og `.git` springes over. **Reglen er frosset 2026-11-01 efter validering v2.** Kendte huller er backend-filer i roden (`server.js`, `app.py`) og andre mapper (fx `cloudflare/`). De rapporteres som trusler og rettes ikke.
   - Ét repo pr. ejer: Det første i rækkefølgen tæller, og senere repos fra samme ejer springes over.
7. **Stop:** når der er 100 berettigede pr. platform, eller når rammen er brugt op.
8. **Stikprøver:** Hovedanalysen er de første 50 berettigede. De første 25 bruges til følsomhedsanalyse (100-laget droppet 2026-11-01). Har en platform færre end 50, sættes hoved-N for alle ned til det laveste antal.
9. **Variabler pr. repo (ekskluderer ikke):** backend-NLOC, platformens commit-andel (Lovable og Replit), `other_ai_tool`, `ambiguous_instructions` og `other_platform`.
10. **Validering:** Den studerende tjekker selv 10 repos pr. platform (5 inkluderede og 5 ekskluderede), trukket med samme seed. Overensstemmelsen rapporteres. To runder (2026-11-01): v1 førte til udvidelsen af backend-reglen. v2 er trukket uden v1's repos (`--exclude`), har en præciseret instruktion og rapporteres som det uafhængige skøn over fejlraten for den frosne regel.
11. **Log:** Hver beslutning skrives med begrundelse pr. repo. Repo-navne forbliver i `data/` (git-ignoreret), og pseudonymer bruges i analysen.
