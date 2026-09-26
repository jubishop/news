---
status: draft
---

# A personal AI news agency

News is a personal news site with a staff of AI reporters. The owner is the
editor in chief and directs what the agency covers and how often it reports.
Published articles are publicly readable. The newsroom is owner-only, and
the API requires authentication.

The [product design](product-design.md) develops this concept and records
accepted decisions for the first version.

## Why build it

Scheduled AI tasks already provide updates about health topics, new AI
models, new products, and other interests. These updates arrive as text
summaries inside a chat app, at weekly or other intervals. Chat is an awkward
place to read and return to a growing collection of news.

The idea is to turn those recurring updates into articles on a dedicated
site. The first version has a newest-first front page and a reporter filter.
Named topic sections are a possible later addition.

## The newsroom

- **Editor in chief:** The owner hires AI reporters, assigns their coverage,
  and sets how often they run.
- **Reporter:** An AI agent responsible for reporting on an assigned subject.
- **Beat:** A reporter's area of coverage, such as AI model releases, a health
  topic, or new products.
- **Article:** A report produced for the site from a reporter's coverage.

## An example

The editor hires an AI reporter to cover new AI models and sets it to run
weekly. The reporter gathers updates and produces articles. Once published,
those articles appear on the front page and can be found through the reporter
filter. Other reporters cover different beats on their own schedules.

The editor can adjust the newsroom as their interests change. The
[product design](product-design.md) defines the accepted publication workflow
and newsroom controls. Each article stores a title, summary, Markdown body,
and sources independently of the page layout.

## Starting point

On September 24, 2026, the owner chose to begin with a public `jubishop/news`
repository, the Project Starter foundation, and this rough idea document.
The purpose is to establish a place to iterate without settling implementation
or design details in the initial setup.

## Questions for later

- What instructions, sources, and tools does each reporter use?
- How should articles cite sources, handle new developments, and avoid repeats?
- How should schedules, failed runs, and reporting costs be managed?
- Which reporting tools and execution approach fit the selected application stack?

These are open design questions. Use GitHub Issues when a question becomes
actionable work.
