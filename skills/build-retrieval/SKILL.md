---
name: build-retrieval
description: "Build or change search and retrieval-augmented generation (RAG): a labeled query set with a recall baseline, ingestion with source IDs, versions, ACLs, and deletions, structure-aware chunking, versioned embeddings, hybrid keyword and vector retrieval, permission filters inside the query, reranking, citations, and retrieval evals. Use when adding or changing a search index, embedding pipeline, vector store, or RAG context step. Not for prompts and answer generation (use the build-llm-feature skill) or answer-quality evals (use the llm-eval-harness skill)."
---

# Build Retrieval

Build search or a RAG retrieval step that finds the right documents, only for
people allowed to see them, and keeps up as sources change. The stance is
**measure recall before tuning, filter before retrieving**: every change is
judged against a labeled query set, and permission filters run inside the
query so content a user cannot see never reaches the model or the user. The
workflow fits pgvector, OpenSearch or Elasticsearch, or a vector database.

## When to use

- Adding search or a RAG context step over documents, tickets, code, product
  data, or a knowledge base.
- Changing chunking, the embedding model, ranking, or the store.
- Retrieval misses obvious documents, returns deleted or stale content, or
  shows content from another tenant or to a user without access.

## When not to use

- The prompt, output validation, and model call that consume the retrieved
  context: use the `build-llm-feature` skill.
- Answer-level datasets, judges, and release gates: use the `llm-eval-harness`
  skill. This skill owns the retrieval metrics.
- A warehouse or batch pipeline that feeds the index: use the
  `data-pipeline-design` skill.
- Deciding who may see what: use the `access-control-design` skill. This skill
  enforces that model at query time.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- The questions users actually ask: search logs, support tickets, chat
  transcripts, or product requirements, and who asks them (roles, tenants).
- Sources: systems, document types (prose, tables, code, PDFs), volume, how
  often documents change or are deleted, and where permission data lives
  (tenant IDs, ACLs, group membership).
- The store and its version, existing index mappings or table schemas, the
  embedding provider and model from configuration, and existing ingestion jobs.
- Latency and cost targets: use the project's SLO and budget. The context
  budget comes from the model's context window and the feature's cost limits.
- Data rules: which content may be sent to a third-party embedding or rerank
  API, and retention requirements.
- Test, lint, and eval commands from `AGENTS.md`, package scripts, or the
  `Makefile`.

## Workflow

1. **Start from questions and a labeled set.** Collect real, redacted queries
   (for example 50 to 200), stratified by kind: exact identifiers (error
   codes, SKUs, ticket numbers, names), natural-language questions, multi-part
   questions, and questions the corpus cannot answer. Label the relevant
   documents for each by stable source ID, not chunk ID, so labels survive
   re-chunking. Run the current system, or plain keyword search for a new one,
   and record recall@k and MRR as the baseline before tuning anything. Keep a
   dev split for tuning and a held-out split for decisions.
2. **Design the index record.** Each chunk carries a deterministic chunk ID
   (for example source ID, document version, and ordinal), source system and
   source ID, parent document ID and heading path, document version or
   `updated_at`, tenant ID and ACL fields (allowed groups, visibility), content
   hash, embedding model name and version, and the text or a pointer to it.
3. **Ingest with deletes and permission changes as first-class events.**
   - Upsert by chunk ID so a rerun is idempotent. When a new version yields
     fewer chunks, delete the parent's chunks from older versions; otherwise
     orphans keep matching.
   - A deleted, archived, or permission-revoked source document must leave the
     index or have its ACL fields updated. Consume source change events or CDC
     where available, and run a periodic reconciliation that removes index
     entries whose source IDs no longer exist or are no longer visible.
   - Store group IDs on chunks and resolve the user's groups at query time from
     the identity system, so a membership change applies without re-indexing.
     Document the remaining propagation lag.
   - Rebuild into a new index or table and switch an alias or view once it is
     verified, so a failed rebuild never serves half an index.
   - Record documents seen, chunks written and deleted, failures, and lag.
4. **Chunk by structure.** Split on the document's own structure first:
   headings and sections for prose, whole tables (or row groups with the
   header repeated), functions or classes for code, lists with their lead-in.
   Then cap size below the embedding model's input limit, counted in its
   tokens. Starting points such as a few hundred tokens with 10 to 20 percent
   overlap are only examples; tune on the labeled set. Prefix the text sent to
   both indexes with the document title and heading path, strip repeated
   boilerplate (navigation, footers), and keep the parent reference so the
   answer step can expand to the surrounding section.
5. **Embed with a recorded model version.** Read the model from configuration
   and record its name and version on every vector or on the index. Never mix
   embedding models in one index: their vector spaces are not comparable. When
   the model changes, re-embed everything into a new index, evaluate it on the
   labeled set, then switch; keep the old index until the new one is verified.
   Follow the model's documented conventions for query versus document inputs
   and its recommended distance metric. Batch calls, respect rate limits, and
   cache embeddings by content hash plus model version.
6. **Retrieve with hybrid search.** Pure vector search misses exact
   identifiers, codes, names, and rare terms; pure keyword search misses
   paraphrases. Run both (BM25 or the store's full-text search, plus vector
   similarity) and fuse the lists, for example with reciprocal rank fusion:
   score = sum over lists of 1 / (c + rank), with c = 60 a common default.
   Elasticsearch, OpenSearch, and several vector databases offer built-in
   hybrid or RRF queries in recent versions; check the documentation for your
   version and license. In PostgreSQL, combine a `tsvector` query and a
   pgvector query in SQL or in application code.
7. **Apply permission and metadata filters inside the query.** Build filters
   on the server from the authenticated identity: tenant ID (required; fail
   closed when it is missing), group IDs, visibility, and business filters such
   as product, language, or date. Pass them in the search request itself (a
   filter clause, a `WHERE` clause, a metadata filter), never as a pass over
   the top-k results. Post-filtering leaks, because the text may already be
   logged, cached, reranked by a third party, or sent to the model, and it
   silently empties results when the top k belong to someone else. Never take
   filter values from model output or free text. With approximate indexes, a
   selective filter can return fewer than k results: pgvector, for example,
   applies `WHERE` to the candidates an HNSW or IVFFlat scan returns. That is
   still safe, since filtered rows never leave the database, but recall drops.
   Recent pgvector versions add iterative scans (check your version); otherwise
   use per-tenant partitions or indexes, or the store's filtered-search
   options, never a weaker filter. For strict isolation, consider a separate index or namespace per
   tenant, or PostgreSQL row-level security. Any cache of retrieval results is
   keyed by the caller's permission scope.
8. **Rerank and fit the context budget.** Optionally retrieve a larger set
   (for example 50 to 100) and rerank it with a cross-encoder or rerank API;
   keep it only if the labeled set shows a gain worth the latency. Then
   deduplicate near-identical chunks, merge neighbors from the same document,
   order by relevance, and stop at the token budget. When nothing is relevant
   enough (a threshold calibrated on the labeled set), return no context so the
   answer step can say it does not know.
9. **Return citations.** Each chunk passed on carries source ID, title, link,
   and version. The answer cites them, and code checks that every cited ID was
   in the retrieved set, because models invent citations. Source links open
   through the normal authorization path.
10. **Treat retrieved content as data.** Documents can carry instructions,
    hidden text, or exfiltration links, especially from sources outsiders can
    edit (tickets, email, wikis, web pages). Delimit retrieved text in the
    prompt, never let it trigger tools or change filters, and sanitize links
    and images on render; the `build-llm-feature` skill covers the prompt side.
11. **Keep it fresh.** Update incrementally from change events or an
    `updated_at` watermark with a lookback, alert on ingestion lag against the
    agreed freshness target, and show each source's last-updated date.
12. **Evaluate and gate changes.** Compute recall@k at the k you actually pass
    on, MRR, and nDCG when relevance is graded (DCG = sum of
    gain / log2(rank + 1); nDCG = DCG / ideal DCG), per query category, for
    baseline and candidate on the same queries. Report per-category results, since averages hide
    regressions on identifier queries. Check no-answer queries separately. Use
    the `llm-eval-harness` skill for faithfulness and answer relevance, and run
    the retrieval eval in CI or on a schedule.

## Worked example: recall@k and MRR over a labeled set (illustrative)

Standard library only. Labels are document IDs, so ranked chunks are collapsed
to documents first.

```python
from __future__ import annotations

from collections import defaultdict
from statistics import fmean


def to_documents(ranked_chunks: list[str], chunk_to_doc: dict[str, str]) -> list[str]:
    """Collapse ranked chunk IDs to ranked document IDs, keeping the best rank."""
    seen: set[str] = set()
    ranked_docs: list[str] = []
    for chunk_id in ranked_chunks:
        doc_id = chunk_to_doc[chunk_id]
        if doc_id not in seen:
            seen.add(doc_id)
            ranked_docs.append(doc_id)
    return ranked_docs


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str], k: int) -> float:
    for position, doc_id in enumerate(ranked[:k], start=1):
        if doc_id in relevant:
            return 1.0 / position
    return 0.0


def evaluate(labels: dict[str, set[str]], results: dict[str, list[str]],
             category_of: dict[str, str], k: int) -> dict[str, dict[str, float]]:
    """labels: query ID to relevant document IDs; results: query ID to ranked document IDs."""
    buckets: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for query_id, relevant in labels.items():
        if not relevant:
            continue  # no-answer queries are checked separately
        ranked = results.get(query_id, [])  # a missing result list counts as a miss
        scores = (recall_at_k(ranked, relevant, k), reciprocal_rank(ranked, relevant, k))
        buckets["all"].append(scores)
        buckets[category_of.get(query_id, "uncategorized")].append(scores)
    return {
        name: {"queries": len(rows),
               f"recall@{k}": fmean(r for r, _ in rows),
               f"mrr@{k}": fmean(rr for _, rr in rows)}
        for name, rows in buckets.items()
    }


labels = {"q1": {"doc-7"}, "q2": {"doc-2", "doc-9"}, "q3": set()}
category_of = {"q1": "identifier", "q2": "question", "q3": "no-answer"}
chunk_to_doc = {"c1": "doc-7", "c2": "doc-7", "c3": "doc-2", "c4": "doc-5"}
results = {
    "q1": to_documents(["c4", "c1", "c2"], chunk_to_doc),  # doc-5, doc-7
    "q2": to_documents(["c3", "c4"], chunk_to_doc),        # doc-2, doc-5
}
print(evaluate(labels, results, category_of, k=5))
# all: recall@5 0.75, mrr@5 0.75; identifier: 1.0 and 0.5; question: 0.5 and 1.0
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  deleting or rebuilding a production index, switching a production alias, and
  bulk embedding against a paid API (estimate the cost first).
- Never weaken a test, check, or threshold to make work pass, and never drop
  hard queries from the labeled set or tune on the held-out split.
- Permission filters are built server-side from the authenticated identity and
  applied inside the retrieval query. Never filter after retrieval.
- Never mix embedding models or model versions in one index.
- Send content to a third-party embedding or rerank API only when the data
  classification allows it; ask when unsure. Log document and chunk IDs, not
  chunk text or raw queries containing personal data.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Chunker tests on fixtures with headings, a table, and code; chunk IDs are
  deterministic across runs.
- Ingesting the same source twice leaves chunk counts unchanged; a new version
  with fewer chunks leaves no orphans.
- A deleted or permission-revoked source document returns zero hits after
  ingestion or reconciliation.
- Isolation tests at the retrieval layer, before any model call: a tenant A
  user searching a phrase unique to tenant B's document gets no results, a user
  removed from a group loses access after sync, and a request without a tenant
  fails instead of searching unfiltered.
- A count of index records grouped by embedding model version returns one row,
  matching configuration.
- Recall@k and MRR per category meet or beat the baseline on the held-out
  split, with the identifier category reported separately.
- Retrieval latency at p50 and p95 is within the project's SLO.
- Lint, type check, and the test suite pass.

## Report

- **Corpus and ingestion:** sources, index record fields, delete and ACL
  propagation path, reconciliation schedule, and measured lag.
- **Chunking and embeddings:** chunking rules and sizes, embedding model and
  version from configuration, index name, and the re-embed plan.
- **Retrieval:** keyword and vector queries, fusion method, filters, reranker,
  k, and context budget.
- **Permissions:** where filters are built and applied, and the isolation tests.
- **Evaluation:** labeled set size per category, and baseline versus candidate
  recall@k, MRR, and nDCG if graded.
- **Not verified:** checks that could not run and why (for example no
  production-like corpus), and assumptions about store behavior taken from
  documentation only.

## Optional delegation

The `security-reviewer` subagent can review permission filtering, tenant
isolation, and the injection surface. The `llm-evaluator` subagent can check
the labeled set and the eval results before a decision. The `data-engineer`
subagent can review ingestion for idempotency and delete handling, and the
`docs-researcher` subagent can confirm version-specific store features. The
workflow above stays complete for a single agent.
