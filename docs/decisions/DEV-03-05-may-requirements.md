# DEV-03 to DEV-05 — Departures from the May functional requirements

**Status:** recorded
**Date:** 2026-08-13
**Design contract:** `reference/deliverable_1_may2026_ui_design_deck.md`

The May deck set six functional requirements. Three are met as written: FR-LAYOUT (the
five-region layout at 1280 px and above), FR-DETAIL (the detection card), and FR-PORTABLE, in
so far as DEV-01 permits. The other three changed, and each is recorded below with what was
promised, what shipped, and why.

---

## DEV-03 — FR-MODES: three modes became two scenes

**Promised:** "Three operating modes selectable from the header: **live**, **historical
replay**, **fire-spread simulation**."

**Shipped:** two scenes, `current` and `april-9-demo`. No simulation.

**Why.** Fire-spread simulation depended on the Inferno API, which ran on competition
infrastructure that no longer exists. Shipping a simulation panel would have meant either
inventing model output, which the honesty rules forbid outright, or displaying frozen results
from April as though they were current. Neither is worth a tab.

Dropping it also removes a fourth data nature, `simulated`, from an interface whose central
discipline is that every record says what it is.

The live and replay modes survive as scenes, which is a stronger construct than a mode: a
scene binds a time window to the set of sources admitted inside it, so live and historical
records cannot be shown together even by accident.

---

## DEV-04 — FR-EXPORT: four formats became two

**Promised:** "exported as a downloadable bundle (GeoJSON · CSV · PNG · ZIP)".

**Shipped:** GeoJSON and CSV.

**Why.** GeoJSON and CSV carry the data and its full provenance, including the footprint
geometry, the confidence scheme and the footprint status. PNG carries a picture, which the
walkthrough video already provides, and ZIP is a container rather than a format.

The two that shipped are the two that let someone else check the work.

---

## DEV-05 — FR-LAYERS: no fire perimeters

**Promised:** layers for "hotspots, fire radiative power, perimeters, and contextual overlays".

**Shipped:** hotspots and fire radiative power, as pixel footprints and point detections.
Contextual overlays are present in the layer panel. **No perimeter layer.**

**Why.** This is the most important of the three, because it is about not misleading anyone.

A satellite pixel footprint is the ground area a detector saw, not the extent of a fire. The
two are constantly confused, and the confusion runs in the dangerous direction: a 2 km AHI
footprint drawn as a perimeter implies a 2 km fire. Every polygon this interface emits carries
`footprint_kind: "satellite_pixel_footprint"` for exactly that reason, and adding a layer
called "perimeters" alongside would undo the distinction.

The BRIGHT pipeline does produce dissolved supercluster polygons, which could ship as an
optional layer labelled "detection cluster extent, not a mapped fire perimeter". That remains
available and is not in this build.
