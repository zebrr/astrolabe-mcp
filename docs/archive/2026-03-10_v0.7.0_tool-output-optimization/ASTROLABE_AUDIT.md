# Astrolabe Tools Audit

Append-only protocol. New entries below `---`.

---

## 2026-03-10 09:48 — Tool Output Research

Systematic testing of all 8 astrolabe MCP tools on a live index (1209 documents, 7 projects).

### What works well (compact output)

| Tool call | Result |
|---|---|
| `get_cosmos()` | Great overview, ~2KB |
| `get_doc_types()` | Compact, ~3KB |
| `get_card(doc_id)` | Single card — perfect, ~0.5KB |
| `read_doc(section=...)` | Targeted read — perfect |
| `read_doc(range=...)` | Targeted read — perfect |
| `reindex_tool()` | Compact summary — perfect |
| `update_index_tool()` | Targeted operation — ok |
| `list_docs(stale=true)` | 6 cards — ok (when few stale) |
| `list_docs(project+type)` | 7 cards — ok (narrow filter) |

### What breaks (output exceeds token limit, dumped to file)

| Call | Size | Problem |
|---|---|---|
| `list_docs()` no filters | **626K** chars | 1209 cards with all fields |
| `list_docs(project="paideia-agent")` | **318K** | 710 cards |
| `list_docs(project="thing-sandbox")` | **75K** | 144 cards |
| `list_docs(type="instruction")` | Passed, but **35 cards** with full summary/keywords — borderline |
| `search_docs(query="md")` | **360K** | Common word — hundreds of results |
| `search_docs(query="agent")` | Passed, but **~70 results** — very noisy |
| `read_doc()` no section/range on large file | **107K** | 3247 lines returned whole |

### Root problems

1. **No pagination** — `list_docs` and `search_docs` return EVERYTHING. No `limit`/`offset`.

2. **No result limit for search** — `search_docs` has no `top_k` / `max_results`. Search for "agent" returned ~70 results, most with relevance 1.5–3.0 (noise).

3. **Too verbose `list_docs` output** — each card includes `summary` + `keywords` + `modified` + `enriched_at`. When you just need a list of doc_ids — that's ~10x excess volume.

4. **`read_doc` truncation insufficient** — `max_file_size_kb=100` in config truncates large files to ~100KB, adds `truncated: true` + warning. But 100KB post-truncation is still too large for agent context window (107K chars dumped to file for a 208KB source). The safeguard exists but the threshold is too generous. **Not "no limit" — limit exists but doesn't prevent the overflow.**

5. **`search_docs` no relevance threshold** — results with relevance 1.5 (practically irrelevant) are still included.

### Proposed solutions

1. **`limit` parameter** for `list_docs` and `search_docs` (default ~50 for list, ~20 for search)
2. **`offset`** for pagination in `list_docs`
3. **Compact mode for `list_docs`** — optional `brief=true` returning only `doc_id`, `type`, `filename` (no summary/keywords/dates)
4. **`max_results` for `search_docs`** with sensible default (10–20)
5. **Relevance threshold** in `search_docs` — don't return results below minimum score
6. **Lower effective truncation for `read_doc`** — current 100KB still overflows; consider ~30-50KB or returning headings list + first N lines when file is large

---

## 2026-03-10 09:55 — MCP Output Limit Clarification

Claude Code MCP tool output limits (source: Claude Code docs):
- **Warning threshold**: 10,000 tokens
- **Hard limit (dump to file)**: **25,000 tokens** (default)
- Configurable via `MAX_MCP_OUTPUT_TOKENS` env var
- ~25K tokens ≈ ~75–100K chars depending on content

**Implication for `max_file_size_kb`**: current value of 100 (KB) produces ~107K chars which exceeds the 25K token limit. Should be tuned to stay under the MCP output cap — roughly **50KB** would be a safer hard ceiling. But this is just a safety net — the real fixes are pagination and result limits (proposed solutions 1–5 above).

---

## 2026-03-10 11:36 — Decision: Final Solution Set

Discussion narrowed down the proposed solutions. Key decisions:

**Dropped:**
- ~~`brief` mode for `list_docs`~~ — with `limit` in place, full cards (with summary/keywords) fit fine. Agent needs context to make decisions; brief mode forces extra `get_card` calls.
- ~~Relevance threshold for `search_docs`~~ — cards are enriched by agents, should be read semantically. Hard numeric cutoff is artificial. Agent should decide relevance itself.
- ~~`limit` for `search_docs`~~ — replaced by `max_results` (same thing, clearer name for ranked search).
- ~~`offset` for `search_docs`~~ — meaningless for ranked results.

**Accepted — 6 changes:**

1. **`limit` + `offset` for `list_docs`** — catalog pagination. Default limit ~50. Agent fetches next page if needed.
2. **`max_results` for `search_docs`** — top-K ranked results. Default ~20.
3. **Agent hints on truncation** (reactive) — when output is cut by limit, prepend a hint to help the agent refine. Different hints for different scenarios (designed in 2026-03-10 12:04 entry below).
4. **Tune `max_file_size_kb`** — reduce from 100 to ~50 as a safety net to stay under MCP 25K token limit. Does not solve the root problem but prevents dump-to-file for `read_doc`.
5. **Strip timestamps from list/search output** — `modified` and `enriched_at` not included in `list_docs` and `search_docs` responses. Data stays in the model and in `get_card()` — only removed from list/search serialization.
6. **Proactive agent guidance in tool descriptions** — add usage tips to tool docstrings so agents make better choices before calling. E.g. "use get_card() to check metadata before reading full content", "use get_cosmos() first for project overview". Same token cost, fewer wasted calls.

---

## 2026-03-10 12:04 — Decision: Agent Hint Design

Hints are adaptive — content depends on which filters are already applied and current pagination state.

### `list_docs` hint (when results truncated by limit)

```
Showing {returned} of {total}.
Filters applied: project={...}, type={...}   (or "none")
Narrow down: type=task ({N}), type=content ({N}), ...   ← only unused filter axis, with counts
Next page: offset={current_offset + limit}
```

- If `project` is set → suggest narrowing by `type` (count cards per type within that project)
- If `type` is set → suggest narrowing by `project` (count cards per project within that type)
- If both set → no narrowing suggestions, only offset
- If neither set → suggest both axes with counts

### `search_docs` hint (when results truncated by max_results)

```
Showing top {returned} of {total} matches.
Try: project={...} or type={...} filter, or more specific query.
```

### `read_doc` hint (when file truncated by max_file_size_kb)

```
Showing lines 1–{N} of {total}.
Available sections: {list of headings}
Use section="..." or range="..." for targeted read.
```

---

## 2026-03-10 13:00 — Implementation Complete: v0.7.0

All 6 accepted changes implemented and tested (227 tests, all green):

1. `list_docs`: `limit`/`offset` pagination, envelope response, adaptive hints by unused filter axis
2. `search_docs`: `max_results` param, envelope response, hint on truncation
3. `read_doc`: enhanced truncation hint with available sections list
4. `max_file_size_kb`: config template reduced 100 → 50
5. Timestamps (`modified`/`enriched_at`) stripped from list/search output, kept in `get_card()`
6. All 8 tool docstrings enhanced with proactive agent guidance

Config defaults: `default_list_limit=50`, `default_search_limit=20` in AppConfig (not hardcoded).
Envelope format: `{total, limit/max_results, offset?, result, hint?}`.
search.py unchanged — slicing in server.py only.
enrich-index skill updated for envelope response + pagination.
