---
status: current
---

# Article history search

Reporters search prior News coverage through one private QMD index on the worker
Mac. They receive short search results and read selected articles on demand.
The server remains the source of truth and runs no AI. See
[worker operations](worker-operations.md) for batch recovery and scheduling.

## Decisions and retrieval

Accepted September 27, 2026: use one archive snapshot for the whole batch. The
owner chose this because up to eight reporters run in parallel. A shared
snapshot gives them the same history; live updates would depend on when each
reporter searched. Publications, deletions, and restorations during a batch
appear in the next batch. Two parallel reporters can still independently cover
the same new story. This feature does not coordinate their proposed stories.

Also accepted September 27, 2026: semantic search is required. The owner wants
reporters to find related coverage even when it uses different words. QMD was
an example, not a required product.

The implementation uses QMD after comparing these approaches:

| Approach | Fit and maintenance cost |
| --- | --- |
| SQLite full-text search alone | Small and fast, but matching words alone does not satisfy the semantic-search requirement. |
| A local embedding library, such as FastEmbed, plus SQLite | Provides meaning-based vectors. News would also need to own chunking, keyword retrieval, result combination, ranking, index reconciliation, and serving. |
| QMD hybrid search | Supplies those retrieval components and a read-only agent interface. Adds its Node/Bun runtime and local models, which are already installed on the worker Mac. |

QMD combines keyword and semantic retrieval, expands natural-language queries,
and reranks the candidates. Keyword matching helps preserve exact product
names and version numbers. Reporters must search both their topic and proposed
stories, try different wording when results are weak, and read promising
matches. A related article can establish prior coverage without ruling out a
new development. No-match results are not proof that a story was never covered.

[QMD's documentation](https://github.com/tobi/qmd) and
[FastEmbed's documentation](https://qdrant.github.io/fastembed/) were reviewed
September 27, 2026. FastEmbed supplies local embeddings; it is not a complete
replacement for QMD's retrieval pipeline. No Python dependency was added.

## Snapshot and access boundaries

The first research attempt downloads all retained articles through the existing
paginated worker API. Other attempts wait for this shared preparation. Paused
acknowledgments and empty batches do not start QMD. Saved pending publications
are delivered before snapshot preparation, so they are included when visible
in the API. Each reporter still receives up to 20 recent article summaries and
30 recent run outcomes.

The supervisor validates every page and article before replacing article files.
Each Markdown record includes its article ID, original reporter attribution,
article and coverage dates, summary, body, and source links. Unchanged files
keep their modification times. QMD updates its index, removes inactive records
and orphaned content, and embeds only missing or changed content. A failed
refresh prevents research from using the old index. Preparation failure is
cached for that batch; its retry attempts report failure. A new worker start
tries preparation again.

The API uses offset pagination. It does not provide a transactionally frozen
export. No new reporter research starts until download completes, but an owner
can still change Trash while pages are being fetched. Such changes can shift
pages. The snapshot means the completed local download shared by all reporters,
not an atomic database view at a precise timestamp.

The worker starts one QMD HTTP process on a selected loopback port. Its index
contains only News articles. Personal QMD collections and the repository's
knowledge index are separate. Codex receives only `query` and `get`; it receives
no News credentials and no full archive file. Its existing read-only shell
sandbox and disabled shell networking remain unchanged.

Prompts request five results, at most ten, and article reads of 80 lines with
further pages as needed. Codex enforces tool-output budgets of 3,000 tokens for
search and 5,000 for reading, before its standard serialization allowance.
Result counts and read lengths are agent instructions; the output token caps
are the enforced context bound. Search errors are explicit tool errors, and
reporters are instructed to return a retryable failure when history is
unavailable. Required MCP startup prevents research when the connection cannot
initialize. Tests cannot guarantee that a model obeys every instruction.

QMD setup commands have a 30-minute limit. Search startup has a 60-second limit;
each Codex history tool call has a 180-second limit inside the existing
30-minute research deadline. The search process and indexing commands run
under a small watcher that stops their process groups when the supervisor's
pipe closes. The watcher retains the worker lock until cleanup finishes, so a
replacement batch cannot mutate the index while the old search process stops.
Each Codex attempt has a separate guardian that enforces its original deadline
even after supervisor death; see [worker recovery](worker-operations.md#daily-batch-and-recovery).
Shared history stops when the supervisor dies, so surviving research cannot
rely on further history calls. Its guardian still bounds its remaining lifetime.

## Installation and checks

News requires QMD >=2.8.3,<3 and checks this before downloading history. Version
2.8.3 was tested with Bun 1.4.2 on this Mac. Install QMD with its supported Node
or Bun runtime; the tested launcher accepts Bun directly. QMD's upstream Node
minimum is 22. Review compatibility before a new QMD major version. The allowed
range is not a claim that every future release has been tested.

Set `qmd_command` in the private worker configuration. It is an argument list,
not a shell command. For an unattended Bun installation, use absolute paths to
Bun and QMD's JavaScript launcher, for example:

```json
{
  "qmd_command": [
    "/Users/REPLACE_ME/.bun/bin/bun",
    "/Users/REPLACE_ME/.bun/install/global/node_modules/@tobilu/qmd/bin/qmd"
  ]
}
```

The runtime directory is added to QMD's child PATH so its launcher works under
cron. Without this setting the worker finds `qmd` on PATH; that is suitable for
an interactive shell but must not be assumed to work under cron.

Run QMD's `pull` command with the configured executable to download its models
before unattended use. The inspected default files total about 2.1 GB: a 300M
embedding model, a 0.6B reranker, and a 1.7B query-expansion model. They use the
normal shared `~/.cache/qmd/models` cache; the article index is private to News.
No paid search account is needed. Local inference and its model files are
additional resource requirements.

```sh
bin/worker --config ~/.config/news/worker.json --check
bin/worker --config ~/.config/news/worker.json --prepare-history
```

`--check` verifies the QMD version, Codex login, and API access without calling
a model. `--prepare-history` downloads the archive, updates embeddings, and
verifies search-service startup without claiming jobs or publishing. It obtains
the same worker lock and refuses to run during a reporting batch. It can call
local embedding models and download missing model files. It does not run Codex
or prove query-expansion/reranking quality; use the smoke test below for that.

After this change merges, update the permanent worker checkout to the reviewed
revision, provision its QMD command and models, and run these two checks. Run
the synthetic smoke test with the same configured command. Preserve the cron
entry and pending delivery state. This immediate verification does not require
waiting for tomorrow's batch or claiming a real reporter.

## Private state and recovery

`state_dir/history/` holds the latest Markdown records, QMD configuration,
SQLite index, snapshot timestamp/count, and logs from the latest preparation
and search service. Its parent directory is mode 0700. This derived state can
be rebuilt from the API. It is separate from durable `pending/` submissions.
Article files removed from the API are removed here at the next successful
refresh. Older reporter diagnostics can retain summaries and retrieved excerpts
for the existing seven-day log period.

On failure, inspect `history/indexing.log`, `history/search.log`, and the
attempt's `failure.json`. Correct the runtime, model, disk, or API problem,
then rerun preparation when no batch is active. A damaged derived index can be
moved aside for rebuilding after confirming the worker is stopped. Never remove
the worker lock or pending results as an index-repair step. Do not copy private
logs to the public issue tracker.

## Validation and limits

Ordinary worker tests fake QMD only at its executable/network boundary. They
exercise real synchronization, process ownership, reporter tool access,
concurrency, failure handling, and publication recovery. They require no models
or network services outside local fixtures.

The opt-in local-model smoke test uses
[14 synthetic articles](../tests/fixtures/article-history.json), including
related stories with different wording and similar but distinct versions:

```sh
.venv/bin/python -B tests/history_search_smoke.py
```

Use `--qmd-command /absolute/runtime /absolute/qmd-launcher` when needed. The
[smoke test](../tests/history_search_smoke.py) checks eight concurrent clients,
six query cases, article metadata and source retrieval, deletion, and an empty
archive. It uses an isolated temporary index inside this checkout's `.cache/`
and writes `.cache/history-search-smoke.json`. It calls only local models.

The September 27 pilot ranked the intended primary article first in all six
queries. All three expected articles were returned for the broader medicine
query. A real Codex CLI 0.157.1 / GPT-6 Luna probe also searched the fictional
Orion 2.1 story and retrieved its identity and coverage dates through these
MCP tools, without a production API call. These small synthetic checks do not
establish recall on a large archive or guarantee that reporters avoid repeats.
