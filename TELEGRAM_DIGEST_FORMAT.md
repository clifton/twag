# Twitter Digest Format for Telegram

## Command

```bash
twag search --time 2h -s 6 -f json -n 50
```

Adjust `--time` for the lookback window (e.g., `10h` for overnight, `42h` for weekend).

## JSON Input

Each entry in the JSON array looks like:

```json
{
  "id": "2018168852144701668",
  "url": "https://x.com/DeItaone/status/2018168852144701668",
  "author_handle": "DeItaone",
  "author_name": "DeItaone",
  "created_at": "2026-02-02T03:45:00+00:00",
  "relevance_score": 9.2,
  "categories": ["commodities"],
  "signal_tier": "critical",
  "tickers": ["GC=F", "GLD"],
  "bookmarked": false,
  "summary": "Spot Gold suffers biggest one-day plunge in over a decade, down 5%.",
  "content": "*SPOT GOLD FALLS 5%, ADDING TO BIGGEST PLUNGE IN OVER A DECADE",
  "has_media": false,
  "has_link": false,
  "has_quote": false,
  "is_x_article": false,
  "is_retweet": false,
  "media_analysis": "Chart shows gold price collapse with volume spike"
}
```

Key fields for formatting:
- **`has_media`** — use `[📊](url)` when `true`, `[🔗](url)` when `false`
- **`categories`** — helps group tweets by theme
- **`tickers`** — mention when relevant
- **`summary`** — use as the basis for bullet text
- **`media_analysis`** — incorporate chart context when present

## Transformation Rules

1. **Group by theme** — Don't list tweets chronologically; group by topic (Fed, metals, earnings, etc.)
2. **Condense** — Multiple tweets on same topic become bullet points under one header
3. **Extract key facts** — Pull out the numbers and key claims
4. **Add context** — Note who said what when attribution matters (e.g., "BofA:", "Timiraos:")
5. **Chart emoji** — Use `[📊](url)` when `has_media: true`
6. **Link emoji** — Use `[🔗](url)` when `has_media: false`
7. **Skip noise** — Omit low-signal tweets, RTs without added value

## Formatting Rules

1. **No markdown tables** — use bullet lists
2. **No ### headers** — use **BOLD CAPS** for section headers
3. **Citations** — use `[🔗](url)` or `[📊](url)` inline at the end of each bullet
4. **Bullet points** — use `•` character

## Example Output

```
**WARSH FED CHAIR NOMINATION**

• Plans to slash Fed's $6T+ balance sheet via QT [🔗](https://x.com/firstadopter/status/2018132908276437156)
• Blames QE for inflation hurting 52% with no financial assets
• BofA: Changes will be gradual, not radical [🔗](https://x.com/DeItaone/status/2018349881027367422)
• MS: Balance sheet changes will steepen yield curve [🔗](https://x.com/DeItaone/status/2018345818260934677)
• Confirmation risk via Sen. Tillis on Banking Committee [🔗](https://x.com/plur_daddy/status/2018348929947988266)
• fejau/Joseph Wang deep dive dropping tomorrow [🔗](https://x.com/fejau_inc/status/2018396690781540460)

**PRECIOUS METALS BLOODBATH**

• Gold down 5% single day - biggest in a decade [🔗](https://x.com/DeItaone/status/2018168852144701668)
• Silver crashed 26-37% - rarest move in 50 years [🔗](https://x.com/DeItaone/status/2018312497548152944)
• UBS: Too early to buy despite nearing LT forecasts
• gnoble79: Debasement trade intact, miners > metals [📊](https://x.com/gnoble79/status/2018335773934657558)

**ISM MANUFACTURING SURPRISE**

• 52.6 vs 48.6 expected - first expansion in 12mo, fastest in 4yr [📊](https://x.com/Geiger_Capital/status/2018345549401899318)
• New orders surged, prices paid highest since Sept [📊](https://x.com/KevRGordon/status/2018338955448447386)
• Timiraos: Tariff confusion plaguing companies, "anti-American" sentiment hurting sales [🔗](https://x.com/NickTimiraos/status/2018344075003367535)
• March rate cut odds collapsed to <11% [📊](https://x.com/Barchart/status/2018431209144258791)

**PLTR CRUSHED EARNINGS**

• Q4 EPS 25c vs 23c, Rev $1.41B vs $1.33B [🔗](https://x.com/DeItaone/status/2018430822315901067)
• FY26 guidance $7.18B vs $6.22B consensus
• 70% Y/Y growth, US commercial 137% Y/Y

**ORCL MASSIVE DEBT RAISE**

• Priced ~$25B multi-tranche bonds (3Y-40Y) [🔗](https://x.com/TheValueist/status/2018465741926699399)
• $248B lease commitments, negative $13B FCF [🔗](https://x.com/MilkRoadAI/status/2018121580191367611)

**OTHER**

• China CXMT selling RAM at $138 vs global $300-400 (bearish MU) [🔗](https://x.com/Pirat_Nation/status/2018158180187226128)
• S. Korea halted program trading sell orders in KOSPI [🔗](https://x.com/zerohedge/status/2018176244911632696)
```

## Example Date

This example is from **2026-02-02**.
