# SEARCH_FIX_VALIDATION

Generated: 2026-03-10 22:39:15

## Deterministic URL Decode Check (Bug 1)
- Sample URL: `https://www.bing.com/ck/a?u=aHR0cHM6Ly9leGFtcGxlLmNvbS9wYWdlP3g9MQ==`
- Resolved URL: `https://example.com/page?x=1`
- Status: `ok=true`

## Runtime Reachability
- `SearXNG` local endpoint: `200 OK` on `http://localhost:18082/search?...`
- `Qdrant` local endpoint:
  - without key: `401`
  - with configured key: `200`
- Direct host outbound probes (`duckduckgo`, `wikipedia`, `google`) may still fail in restricted shell environments, but live search now succeeds through SearXNG.

## Test 1
Query: `what is the cost of franklin batting gloves`

- Engines returned: `brave`, `startpage`
- Rows returned: `8`
- Bing redirect URLs: `0`
- Relevance before filter: `[0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6]`
- Relevance after filter: `[0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6]`
- Time to first Ollama token: `7.5662s`
- Final answer quality: `correct_or_grounded`

## Test 2
Query: `latest transformer architecture research 2025`

- Engines returned: `bing news`, `duckduckgo news`, `yahoo news`
- Rows returned: `10`
- Bing redirect URLs: `0`
- Relevance before filter: `[0.6, 0.4, 0.4, 0.4, 0.2, 0.2, 0.0, 0.0, 0.0, 0.0]`
- Relevance after filter: `[0.6, 0.4, 0.4, 0.4, 0.2, 0.2]`
- Time to first Ollama token: `0.6746s`
- Final answer quality: `honest_failure` (explicitly reports irrelevant results and falls back to general knowledge)

## Test 3
Query: `best mlops tools 2025`

- Engines returned: `brave`, `startpage`
- Rows returned: `10`
- Bing redirect URLs: `0`
- Relevance before filter: `[1.0, 1.0, 1.0, 1.0, 1.0, 0.75, 0.75, 0.5, 0.5, 0.5]`
- Relevance after filter: `[1.0, 1.0, 1.0, 1.0, 1.0, 0.75, 0.75, 0.5, 0.5, 0.5]`
- Time to first Ollama token: `0.8692s`
- Final answer quality: `correct_or_grounded`

## Summary
- Bug 1 fixed: Bing redirect URLs are decoded and normalized before use/fetch.
- Bug 2 fixed: intent detection now routes shopping/news/general categories for SearXNG.
- Bug 3 fixed: relevance scoring/filtering + retry gate prevents low-quality context from driving hallucinated synthesis.
- Bug 4 fixed: fake flat `%` scoring removed; scores are now computed or taken from provider data.
- Page fetcher fixed: redirect handling, realistic UA, tag stripping, main-content extraction, graceful fallback.
