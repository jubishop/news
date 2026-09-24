---
status: draft
---

# A personal AI news agency

News is a personal news site with a staff of AI reporters. The owner is the
editor in chief and directs what the agency covers and how often it reports.

## Why build it

Scheduled AI tasks already provide updates about health topics, new AI
models, new products, and other interests. These updates arrive as text
summaries inside a chat app, at weekly or other intervals. Chat is an awkward
place to read and return to a growing collection of news.

The idea is to turn those recurring updates into articles on a dedicated
site. A front page shows new articles, and sections organize coverage by
topic.

## The newsroom

- **Editor in chief:** The owner hires AI reporters, assigns their coverage,
  and sets how often they run.
- **Reporter:** An AI agent responsible for reporting on an assigned subject.
- **Beat:** A reporter's area of coverage, such as AI model releases, a health
  topic, or new products.
- **Article:** A report produced for the site from a reporter's coverage.
- **Section:** A place to browse related articles. The relationship between
  sections and beats can be decided later.

## An example

The editor hires an AI reporter to cover new AI models and sets it to run
weekly. The reporter gathers updates and produces articles. Once published,
those articles appear on the front page and in a relevant section. Other
reporters cover different beats on their own schedules.

The editor can adjust the newsroom as their interests change. Exact controls,
article formats, and the steps between reporting and publication are still
open.

## Starting point

On September 24, 2026, the owner chose to begin with a public `jubishop/news`
repository, the Project Starter foundation, and this rough idea document.
The purpose is to establish a place to iterate without settling implementation
or design details in the initial setup.

## Questions for later

- Who can read the site, and how much of the experience is personal?
- What instructions, sources, and tools does each reporter use?
- Does a reporter publish directly or submit drafts for editorial review?
- How should articles cite sources, handle corrections, and avoid repeats?
- How should schedules, failed runs, and reporting costs be managed?
- Which application stack, storage, and hosting fit the first useful version?

These are open design questions. Use GitHub Issues when a question becomes
actionable work.
