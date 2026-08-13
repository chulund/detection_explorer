# DEV-02 — Code lives in a separate repository

**Status:** approved
**Date recorded:** 2026-08-13

## What was agreed

The interface is built in its own repository, `chulund/detection_explorer`, rather than inside
the grant repository. The grant repository keeps the paperwork.

## What this overrides

`DELIVERY_PROMPT.md:112` — "Put all new work in this repo; commit as you go."

## Why

Three reasons, in order of weight.

The interface is meant to outlive the grant. A codebase that may become public, gain
contributors and keep running after August does not belong inside a folder of milestone
reports, and extracting it later is real work that tends not to happen.

It has different licensing exposure. The grant repository contains reports and correspondence
that are internal by default. The interface repository is built to be published once the team
approves, and mixing the two makes that decision harder rather than easier.

It has its own dependency graph and test suite. `polar-footprint` is pinned into it, the
BRIGHT pipeline is resolved through an environment variable, and it carries 137 backend and 8
frontend tests. That is a project, not a deliverable artefact.

## What keeps the grant record whole

`deliverable_3_august/` in the grant repository retains, and must retain before submission:

- the design spec and this set of decision records
- the D3 report
- the exact release commit SHA of the interface repository
- an archival source bundle of that tagged release

So the grant record stands alone even if the code repository moves, is renamed, or is made
public under different terms.
