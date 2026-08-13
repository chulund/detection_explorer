# DEV-01 — Delivered on localhost, not at a public URL

**Status:** approved by A/Prof. Karin Reinke
**Approval evidence:** ⚠️ **outstanding — see below**
**Date recorded:** 2026-08-13

## What was agreed

Detection Explorer is delivered as software that runs on a local machine. There is no public
deployment, and an examiner runs it themselves rather than visiting a URL.

## What this overrides

Two written acceptance criteria, both of which say the opposite.

`DELIVERY_PROMPT.md:93` — "Deployed web interface at a public URL, consuming the D2 feed."

`CONTEXT.md:70` — "**'Accessible' means an examiner can reach it independently** — a public
URL, not localhost."

These were written in July, when the assumption was that D3 would be examined remotely.

## Why it is defensible

The grant milestone is a working interface, and the examination is a walkthrough video plus a
quick guide rather than an unaccompanied visit to a website. Karin confirmed that a local
demonstration satisfies that.

The technical case is stronger than convenience. The interface recomputes BRIGHT from 593 MB
of staged Himawari inputs, and a public deployment would either have to carry that data and
the detection pipeline, which is unpublished team research, or drop the computation and become
a viewer of precomputed output. The local build keeps the part of the deliverable that is
actually novel.

## What limits the damage

The repository is built public-ready rather than local-only. It has no committed secrets, no
data in git, and a fixture profile that runs from a clean clone with no credentials. Deploying
it is a decision, not a rewrite.

## Outstanding

**This record needs Karin's confirmation quoted, with its date.** An approval that overrides a
written acceptance criterion should be evidenced in the deliverable, not merely asserted in
it. Paste the email or message text here before the D3 report is submitted.
