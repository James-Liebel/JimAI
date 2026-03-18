# SEARCH_TEST_RESULTS

Generated: 2026-03-10 22:40:57

## Service Status
```json
{
  "searxng": {
    "name": "searxng",
    "ok": true,
    "status_code": 200,
    "url": "http://localhost:18082/search?q=test&format=json"
  },
  "bing": {
    "name": "bing",
    "ok": false,
    "status_code": 0,
    "url": "https://www.bing.com/search?q=test",
    "error": "All connection attempts failed"
  },
  "google": {
    "name": "google",
    "ok": false,
    "status_code": 0,
    "url": "https://www.google.com/search?q=test",
    "error": "All connection attempts failed"
  },
  "duckduckgo": {
    "name": "duckduckgo",
    "ok": false,
    "status_code": 0,
    "url": "https://api.duckduckgo.com/?q=test&format=json&no_html=1&skip_disambig=1",
    "error": "All connection attempts failed"
  },
  "qdrant": {
    "name": "qdrant",
    "ok": true,
    "status_code": 200,
    "url": "http://localhost:16333/collections"
  },
  "ollama": {
    "name": "ollama",
    "ok": true,
    "model_count": 8
  }
}
```

## Scenario Runs
### Query: latest advances in transformer architecture 2025
```json
{
  "status_code": 200,
  "elapsed_seconds": 1.717,
  "ok": true,
  "from_memory": true,
  "source_count": 0,
  "raw_mode": false,
  "timings": {
    "query_rewrite": 0.9636,
    "cache_check": 0.7482,
    "total": 1.7122
  },
  "answer_preview": "I could not retrieve live web results for 'latest advances in transformer architecture 2025'.",
  "provider_errors": {},
  "query": "latest advances in transformer architecture 2025"
}
```

### Query: what is SMOTE oversampling technique
```json
{
  "status_code": 200,
  "elapsed_seconds": 1.429,
  "ok": true,
  "from_memory": true,
  "source_count": 0,
  "raw_mode": false,
  "timings": {
    "query_rewrite": 0.6735,
    "cache_check": 0.753,
    "total": 1.4268
  },
  "answer_preview": "I could not retrieve live web results for 'what is SMOTE oversampling technique'.",
  "provider_errors": {},
  "query": "what is SMOTE oversampling technique"
}
```

### Query: SpaceX launches 2025
```json
{
  "status_code": 200,
  "elapsed_seconds": 1.522,
  "ok": true,
  "from_memory": true,
  "source_count": 0,
  "raw_mode": false,
  "timings": {
    "query_rewrite": 0.7852,
    "cache_check": 0.7341,
    "total": 1.5198
  },
  "answer_preview": "I could not retrieve live web results for 'SpaceX launches 2025'.",
  "provider_errors": {},
  "query": "SpaceX launches 2025"
}
```

## Cache Repeat
```json
{
  "query": "what is SMOTE oversampling technique",
  "first": {
    "status_code": 200,
    "elapsed_seconds": 0.002,
    "ok": true,
    "from_memory": true,
    "source_count": 0,
    "raw_mode": false,
    "timings": {
      "total": 0.0
    },
    "answer_preview": "I could not retrieve live web results for 'what is SMOTE oversampling technique'.",
    "provider_errors": {}
  },
  "second": {
    "status_code": 200,
    "elapsed_seconds": 0.001,
    "ok": true,
    "from_memory": true,
    "source_count": 0,
    "raw_mode": false,
    "timings": {
      "total": 0.0
    },
    "answer_preview": "I could not retrieve live web results for 'what is SMOTE oversampling technique'.",
    "provider_errors": {}
  }
}
```

## SearXNG Forced Down
```json
{
  "status_code": 200,
  "elapsed_seconds": 4.796,
  "ok": true,
  "from_memory": false,
  "source_count": 0,
  "raw_mode": true,
  "timings": {
    "query_rewrite": 0.7262,
    "cache_check": 0.0,
    "parallel_search": 3.3313,
    "page_fetch": 0.0,
    "synthesis": 0.7366,
    "total": 4.7946
  },
  "answer_preview": "I could not retrieve live web results for 'SpaceX launches 2025'.",
  "provider_errors": {
    "searxng": "forced_searxng_down",
    "bing": "All connection attempts failed",
    "google": "All connection attempts failed",
    "duckduckgo": "All connection attempts failed",
    "wikipedia": "All connection attempts failed"
  }
}
```
