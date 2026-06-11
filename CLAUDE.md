# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Transações Família

Family financial management web app for tracking and importing transactions.

**Live**: https://vcm-sudo.github.io/financas-familia/  
**Repo**: https://github.com/vcm-sudo/financas-familia/

### Tech Stack

- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript — single file `index.html` (~1250 lines)
- **Backend**: Firebase Authentication + Firestore
- **Charts**: Chart.js 4.4 (CDN)
- **Hosting**: GitHub Pages — push to `main` deploys automatically
- **AI (PDF extraction)**: Anthropic API (`claude-opus-4-8`) called directly from the browser with `anthropic-dangerous-direct-browser-access: true`

### Deploy

```bash
git add index.html
git commit -m "description"
git push origin main   # triggers GitHub Pages deploy
```

No build step. Edit `index.html` directly.

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

| Lines | Section |
|---|---|
| 11–147 | CSS — variables, layout, components |
| 149–410 | HTML — login screen, header/nav, dashboard tab, transações tab, import tab, modals |
| 411–428 | Firebase init + global state (`ALL_TX`, `filtros`, `editingId`) |
| 424–428 | Constants: `CATEGORIAS`, `CAT_CORES`, `CONTA_CORES` |
| 439–475 | Auth (`loginGoogle`, `onAuthStateChanged`) |
| 476–518 | Firestore listener, month filter population, `txFiltradas()` |
| 519–604 | Dashboard render (KPIs, charts, table) |
| 605–683 | Transações render (category breakdown, chronological list, sort) |
| 684–780 | Transaction CRUD (add, edit, delete modal) |
| 782–855 | Import routing (`routeFile`, `handleFile`, `handleDrop`) |
| 856–947 | PDF → Anthropic API → preview |
| 948–998 | OFX parser |
| 999–1089 | CSV parser |
| 1090–1130 | Category memory (`loadCatMemory`, `saveCatMemory`, `lookupCatMemory`, `applyMemory`) |
| 1131–1175 | `isCreditCardPayment`, `guessCategory` |
| 1176–1215 | `renderPreview`, `updatePreviewCount`, `savePreview`, `cancelPreview` |
| 1214–1252 | Helpers (`fmt`, `fmtDate`, `fileToBase64`, `toast`, `escHtml`, modal/tab utils) |

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

### Key Constants (update all four when adding a category or account)

**CATEGORIAS** (array, ~line 422): controls all dropdowns and chart legend  
**CAT_CORES** (object, ~line 423): hex color per category  
**CONTA_CORES** (object, ~line 428): hex color per account — `Nubank #820AD1`, `Bradesco #CC0000`, `Mastercard #EB001B`, `Visa #1A1F71`  
**HTML `<option>` lists**: `fil-conta`, `tx-conta`, `pdf-conta`, `fil-cat`, `tx-cat` — must stay in sync with constants above

### Import Logic

Three parsers share the same post-processing pipeline:
1. `applyMemory(t)` — overrides categoria with user's saved merchant→category mapping (localStorage `cat_memory_v1`)
2. `isCreditCardPayment(desc)` — detects credit card bill payments; sets `_faturaCartao = true` → unchecked + ⚠️ in preview
3. `renderPreview()` — shows editable rows; changing a category calls `saveCatMemory()` to persist the mapping

**Double-counting prevention**: OFX and CSV both call `isCreditCardPayment`. PDF prompt instructs the AI to skip "pagamento de fatura" credits. The migration button (⚙️ → Recategorizar) re-applies `guessCategory` using the stored `tipo` field.

### `guessCategory(desc, tipo)` — priority order

1. `tipo === 'receita'` → returns Salário or Outros immediately  
2. Assinaturas (Netflix, Spotify, Prime, Disney, HBO, Apple, Google, YouTube, iCloud, Microsoft)  
3. Comércio Eletrônico (Amazon, Mercado Livre, Shopee, Magalu, Americanas, AliExpress, Shein, Wish)  
4. Alimentação → Moradia → Saúde → Educação → Transporte → Lazer → Vestuário → Investimento → Outros

**Assinaturas before Comércio Eletrônico** is intentional: "Amazon Prime" must match Assinaturas before the generic "amazon" e-commerce pattern fires.

### Category Memory (localStorage)

Keys are the first 20 chars of `desc.toLowerCase().replace(/[^a-z0-9 ]/g,'')`. `lookupCatMemory` tries exact match first, then partial match on keys ≥ 8 chars. Module-level `_catMemoryCache` avoids repeated `JSON.parse` during batch imports.

### XSS Safety

All user-derived values inserted into `innerHTML` must go through `escHtml()` (~line 1230). This includes `t.descricao`, `t.data`, category names from Firestore. Use `data-*` attributes + event delegation instead of inline `onclick="...${value}..."`.
