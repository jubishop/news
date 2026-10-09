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

The first research attempt refreshes the retained archive through the authenticated
[manifest protocol](server-contract.md#archive-manifest-protocol). Other attempts
wait for this shared preparation. Paused acknowledgments and empty batches do not
start QMD. Saved pending publications are delivered first, so the snapshot includes
them when visible in the API. Each reporter still receives up to 20 recent article
summaries and 30 recent run outcomes.

The supervisor lists IDs and revisions in pages of 100, then downloads only new,
changed, restored, or locally damaged articles. It checks cached Markdown and
summary metadata against local SHA-256 digests. Missing records are downloaded
again. An unchanged archive transfers no article bodies. The first download, a
missing cache manifest, or an invalid manifest requires all bodies once.

Every page and body request after the first carries the archive version. A final
manifest request with `limit=1` checks that version again, including for an empty
archive. Publication, content or attribution edits, Trash, restore, or purge change
the version. The worker restarts an inconsistent download, with at most three
complete attempts. Network failures, malformed or incomplete pages, and repeated
archive changes fail the batch explicitly. A partial listing never removes cached
records. The successful version defines a complete archive at the final check;
changes after that check wait until the next batch.

Preparation builds a separate local generation. Unchanged Markdown files use hard
links to retain their contents and modification times. Each record includes its
ID, original reporter attribution, dates, summary, body, and source links. The
worker copies the previous SQLite index with SQLite's backup API, including any
committed WAL content. QMD updates that copy, removes inactive records and orphaned
content, and embeds only missing or changed content.

QMD can exit successfully after skipping unreadable files or failing to embed
some articles. The worker rejects skipped reads and checks QMD's index status:
the document count must match the archive, no embeddings may be pending, and a
nonempty archive must have a vector index. This status check is supervisor-only;
reporters still receive only `query` and `get`.

Only after validation does one atomic pointer replacement publish the generation.
Old generations are then removed. A download, index, or promotion failure leaves
the previous valid generation intact and prevents research from using it. The
failure is cached for that batch; retries report the failure. A new worker start
tries preparation again. Up to eight reporters share the same fixed generation.

The worker starts one QMD HTTP process on a selected loopback port. Its index
contains only News articles. Personal QMD collections and the repository's
knowledge index are separate. Claude Code receives only `query` and `get`; the
worker hides QMD's other tools. It receives no News credentials and no full
archive file. It has no shell, and its file tools are confined to the attempt
directory.

Prompts request five results, at most ten, and article reads of 80 lines with
further pages as needed. Claude Code applies one MCP output budget to every
tool; the worker sets it to 5,000 tokens. Codex had a separate 3,000-token
budget for search, so search results can now use more context. Result counts
and read lengths are agent instructions; the output token cap is the enforced
context bound. Reporters are instructed to return a retryable
failure for explicit tool errors. QMD can also hide embedding, expansion, or
reranker failures behind ordinary results. Before accepting each research result,
the supervisor checks the search process and its known model-failure diagnostics.
A detected failure rejects that result and prevents further research for the
batch. Concurrent attempts can finish, but their results also become retryable
failures; already saved results remain valid. The diagnostic strings are part
of the QMD compatibility check when upgrading. Claude Code continues when the
history server cannot connect, so the supervisor rejects any result whose
startup event does not show the connection. That failure costs one attempt.
Tests cannot guarantee that a model obeys every instruction.

QMD setup commands have a 30-minute limit. Search startup has a 60-second limit;
Claude Code allows 30 seconds to connect, and each history tool call has a
180-second limit inside the existing 30-minute research deadline. The search
process and indexing commands run under a small watcher that stops their
process groups when the supervisor's pipe closes. The watcher retains the worker lock until cleanup finishes, so a
replacement batch cannot mutate the index while the old search process stops.
Each Claude Code attempt has a separate guardian that enforces its original deadline
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
launchd. Without this setting the worker finds `qmd` on PATH; that is suitable
for an interactive shell but must not be assumed to work under launchd.

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

`--check` verifies the QMD version, Claude Code login, and API access without calling
a model. `--prepare-history` synchronizes the archive, updates embeddings, and
verifies search-service startup without claiming jobs or publishing. It obtains
the same worker lock and refuses to run during a reporting batch. It can call
local embedding models and download missing model files. It does not run
Claude Code or prove query-expansion/reranking quality; use the smoke test below for that.

After the manifest change merges, verify successful server deployment and its
schema migration before updating the permanent worker checkout. The new worker
requires the manifest endpoint; it fails explicitly against an older server.
Preserve its QMD command and models, then run these two checks twice. The second
preparation should download no bodies and reuse embeddings. Run
the synthetic smoke test with the same configured command. Preserve the
scheduled LaunchAgent and pending delivery state. This immediate verification does not require
waiting for tomorrow's batch or claiming a real reporter.

## Private state and recovery

`state_dir/history/current` points to the last validated `generation-*` directory.
Each generation contains `articles/`, `cache.json` (revisions, summaries, and
integrity digests), `config/`, `index.sqlite`, and `snapshot.json` (timestamp,
count, and archive version). `history/indexing.log` and `history/search.log` hold
diagnostics from the latest attempt. The history directory is mode 0700, and
article and manifest files are mode 0600. This derived state is separate from
durable `pending/` submissions.

The first refresh after upgrading an older cache downloads all bodies once and
copies its existing index to retain embeddings. The old layout is removed only
after successful validation. Articles removed from the server disappear from the
active cache and index at the next successful refresh. Older reporter diagnostics
can retain excerpts for the existing seven-day log period.

On failure, inspect the history logs and the attempt's `failure.json`. Correct the
runtime, model, disk, or API problem, then rerun preparation when no batch is active.
A missing or corrupt cache record is repaired from the server. An unreadable SQLite
database is rebuilt from the cached article files. If QMD still rejects an index,
move the derived `history/` directory aside while the worker is stopped and prepare
again. A crash before the pointer switch leaves the previous generation current;
an unreferenced generation is discarded after the next successful refresh. Allow
space for a second index and changed articles during preparation. Cached Markdown
is read locally to check integrity; this change reduces network transfer, not all
local disk work.

Never remove the worker lock or pending results as an index-repair step. Do not
copy private logs to the public issue tracker.

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
six query cases, article metadata and source retrieval, an unchanged refresh,
deletion, and an empty
archive. It uses an isolated temporary index inside this checkout's `.cache/`
and writes `.cache/history-search-smoke.json`. It calls only local models.
The broad medicine query requires all three related articles in the first five
results and any one of those articles first. The focused queries still require
their specified article first, including Orion 2.1 ahead of Orion 2. The fixture
records the required set in `expected` and the allowed first results in
`first_any_of`; the order of `expected` does not define ranking.

Each invocation replaces the previous report with `status: running` before
loading the fixture or preparing QMD. It saves every completed client's ranked
IDs, response, timing, and failure, then finishes with `passed` or `failed`.
Handled failures exit nonzero. An interrupted run can leave `running`, which
is not a successful result. Indexing and search logs from all generations are
copied into the report before the temporary index is removed. Query failures
do not suppress the other clients, article read, or model-health checks.
Copy this report after each invocation when comparing independent runs; the
next invocation replaces it. Diagnose any failed run instead of retrying until
one passes. These synthetic reports contain no private archive articles.

The September 27 pilot ranked the intended primary article first in all six
queries. All three expected articles were returned for the broader medicine
query. A real Codex CLI 0.157.1 / GPT-6 Luna probe also searched the fictional
Orion 2.1 story and retrieved its identity and coverage dates through these
MCP tools, without a production API call. On October 9, 2026, two real Claude
Code 2.1.296 / Haiku 5.5 attempts searched the same fictional coverage through
the worker's MCP configuration before reporting; see
[worker tests](worker-operations.md#tests). These small synthetic checks do not
establish recall on a large archive or guarantee that reporters avoid repeats.


### Synchronization cost

The September 27, 2026 automated HTTP measurement uses the real Flask/SQLite API
with 205 synthetic articles, each with about 21 KB of Markdown. Counts include
all manifest pages and the final version check. Bytes are uncompressed JSON
response bodies; HTTP headers and transport overhead are excluded. Opaque IDs can
slightly change the final one-record check's size.

| Refresh | Requests | Article bodies | Response bytes, approximately |
| --- | ---: | ---: | ---: |
| Previous full-search protocol, every batch | 3 | 205 | 4.71 MB |
| New initial synchronization | 209 | 205 | 4.72 MB |
| New unchanged synchronization | 4 | 0 | 13.5 KB |
| New synchronization with one changed article | 5 | 1 | 36.5 KB |

Trash and purge need no bodies; restoration and one addition each need one.
The remaining manifest cost grows with article count: one ID and 32-character
revision per article, page envelopes, and one final one-record check. Initial
synchronization makes more requests because bodies use individual retrieval.
Local preparation copies the index and checks cached file bytes. A change feed
or bulk body-fetch endpoint is not required for this network improvement.

The real-QMD check also verified 14 unchanged documents, zero new or updated
documents, and reuse of all existing embeddings after the generation switch.
