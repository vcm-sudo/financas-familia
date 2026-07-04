# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Transações Família

Family financial management web app for tracking and importing transactions.

**Live**: https://vcm-sudo.github.io/financas-familia/  
**Repo**: https://github.com/vcm-sudo/financas-familia/

### Tech Stack

- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript — single file `index.html` (~1350 lines)
- **Backend**: Firebase Authentication + Firestore
- **Charts**: Chart.js 4.4 (CDN)
- **Hosting**: GitHub Pages — push to `main` deploys automatically
- **AI (PDF extraction)**: Claude Code CLI (`claude`, `claude-opus-4-8`) on the **subscription**, via a local bridge server (`servidor.py`, `POST /extrair-pdf`). The old direct `api.anthropic.com` browser call and the in-app API-key field were removed. PDF import only works when the app is opened locally on the Mac (`localhost`, run `iniciar-financas.command` → serves on :8742); on GitHub Pages / phone it degrades to a message pointing at OFX/CSV. OFX and CSV import are pure client-side and keep working everywhere.

### Deploy

```bash
git add index.html
git commit -m "description"
git push origin main   # triggers GitHub Pages deploy
```

No build step. Edit `index.html` directly.

### Running locally (needed for PDF import)

```bash
open iniciar-financas.command   # kills :8742, starts servidor.py, opens localhost:8742/index.html
# or: python3 servidor.py  → http://localhost:8742/index.html
```

`servidor.py` serves the static files **and** exposes `POST /extrair-pdf`, which writes the
uploaded PDF to a temp file and runs the Claude Code CLI (`claude … --allowedTools Read
--model claude-opus-4-8`) with `ANTHROPIC_API_KEY` stripped from the env, so PDF OCR runs on
the subscription (same pattern as `../Dashboard Hemato/servidor.py` and
`../Transcrição exames/lab_transcribe.py`). `claude` must be installed and logged in.

### Verify changes with Playwright (Python)

```bash
python3 - << 'EOF'
import asyncio
from playwright.async_api import async_playwright
FILE = "file:///Users/viniciuscamposdemolla/pCloud%20Drive/_/Claude/Transa%C3%A7%C3%B5es/index.html"
async def main():
    async with async_playwright() as p:
        page = await (await p.chromium.launch()).new_page()
        await page.goto(FILE)
        await page.wait_for_timeout(1000)
        print(await page.evaluate("guessCategory('Netflix', 'despesa')"))
asyncio.run(main())
EOF
```

### Code Organization (`index.html`)

Line numbers drift as the file grows — treat them as approximate and confirm by grepping the `// ── SECTION ──` comment banners.

| Lines | Section |
|---|---|
| 11–155 | CSS — variables, layout, components, import banner/status |
| 157–432 | HTML — login, header/nav, import-pending banner, dashboard/transações/import tabs, modals |
| 433–463 | `<script>` start · Firebase init + global state (`ALL_TX`, `filtros`, `editingId`, `importBannerDismissed`) + constants |
| 464–489 | Auth (`loginGoogle`, `onAuthStateChanged`) |
| 490–533 | Firestore listener, month filter population, `txFiltradas()` |
| 534–543 | Toggle pessoa (dashboard) |
| 544–629 | Dashboard render (KPIs, charts, table) |
| 630–701 | Import status (`prevMonthStr`, `monthLabel`, `renderImportStatus`, banner show/dismiss) |
| 702–780 | Transações render (category breakdown, chronological list, sort) |
| 781–878 | Transaction CRUD (delete modal @781, add/edit form @813) |
| 879–940 | Import routing (`routeFile`, `handleFile`, `handleDrop`) + settings + `migrateCategorias` |
| 941–986 | PDF → local `/extrair-pdf` (Claude CLI, subscription) → preview; `isLocalHost()` guard |
| 987–1037 | OFX parser |
| 1038–1128 | CSV parser |
| 1129–1169 | Category memory (`loadCatMemory`, `saveCatMemory`, `lookupCatMemory`, `applyMemory`) + `escHtml` @1165 |
| 1170–1192 | `isCreditCardPayment` @1170, `guessCategory` @1175 |
| 1193–1252 | `renderPreview` @1193, `updatePreviewCount` @1221, `savePreview` @1229, `cancelPreview` |
| 1253–1291 | Helpers (`fmt`, `fmtDate`, `fileToBase64`, `toast`, modal/tab utils) |

### Data Model

Firestore collection `transacoes` — fields per document:

```
descricao  string
valor      number  (always positive)
data       string  YYYY-MM-DD
tipo       string  "receita" | "despesa"
categoria  string  one of CATEGORIAS
conta      string  Nubank | Bradesco | Mastercard | Visa | Outros
pessoa     string  "vini" | "esposa"
criadoEm   string  ISO timestamp
```

### Key Constants (update all of these together when adding a category or account)

**CATEGORIAS** (array, line 454): controls all dropdowns and chart legend  
**CAT_CORES** (object, line 455): hex color per category  
**CONTA_CORES** (object, line 460): hex color per account — `Nubank #820AD1`, `Bradesco #CC0000`, `Mastercard #EB001B`, `Visa #1A1F71`  
**CONTA_TIPO** (object, line 461): `"extrato"` or `"fatura"` per account — drives the wording in the import-status panel (cartões = fatura, contas = extrato)  
**HTML `<option>` lists**: `fil-conta`, `tx-conta`, `pdf-conta`, `fil-cat`, `tx-cat` — must stay in sync with constants above

### Import Logic

Three parsers share the same post-processing pipeline:
1. `applyMemory(t)` — overrides categoria with user's saved merchant→category mapping (localStorage `cat_memory_v1`)
2. `isCreditCardPayment(desc)` — detects credit card bill payments; sets `_faturaCartao = true` → unchecked + ⚠️ in preview
3. `renderPreview()` — shows editable rows; changing a category calls `saveCatMemory()` to persist the mapping

**Double-counting prevention**: OFX and CSV both call `isCreditCardPayment`. PDF prompt instructs the AI to skip "pagamento de fatura" credits. The migration button (⚙️ → Recategorizar) re-applies `guessCategory` using the stored `tipo` field.

**Sibling app (PJ income)**: the NF-tracking app at `../vcmltda/nf/` exports paid invoices as a `;`-separated CSV (receita, categoria Salário, net value) that is imported here via the same CSV parser — so `Salário` receitas with descriptions like `NF 0001 - <cliente> (PJ, líquido)` originate there. See `../vcmltda/nf/CLAUDE.md`.

### Import Status / pending-month reminder

`renderImportStatus()` (called from the Firestore listener on every snapshot) derives the **last imported month per account** purely from `ALL_TX` — no separate tracking state. It compares each account's latest month against `prevMonthStr()` (the month before today; the statement/fatura you'd normally have just imported). Accounts whose latest data is older are listed as pending in the Import-tab status panel and surfaced in a banner at the top of `.content` (visible on all tabs). The banner only lists accounts that already have history, so unused accounts never nag. `importBannerDismissed` hides it for the session; it reappears on reload until the month is actually imported. Because status is derived, importing the missing month clears the warning automatically on the next snapshot.

### `guessCategory(desc, tipo)` — priority order

1. `tipo === 'receita'` → returns Salário or Outros immediately  
2. Assinaturas (Netflix, Spotify, Prime, Disney, HBO, Apple, Google, YouTube, iCloud, Microsoft)  
3. Comércio Eletrônico (Amazon, Mercado Livre, Shopee, Magalu, Americanas, AliExpress, Shein, Wish)  
4. Alimentação → Moradia → Saúde → Educação → Transporte → Lazer → Vestuário → Investimento → Outros

**Assinaturas before Comércio Eletrônico** is intentional: "Amazon Prime" must match Assinaturas before the generic "amazon" e-commerce pattern fires.

### Category Memory (localStorage)

Keys are the first 20 chars of `desc.toLowerCase().replace(/[^a-z0-9 ]/g,'')`. `lookupCatMemory` tries exact match first, then partial match on keys ≥ 8 chars. Module-level `_catMemoryCache` avoids repeated `JSON.parse` during batch imports.

### XSS Safety

All user-derived values inserted into `innerHTML` must go through `escHtml()` (line 1165). This includes `t.descricao`, `t.data`, category names from Firestore. Use `data-*` attributes + event delegation instead of inline `onclick="...${value}..."`.
