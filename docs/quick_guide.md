# Detection Explorer — quick guide

A two-page guide to what this tool shows and how to read it. No technical background needed.

## What it is for

Satellites find fires in two quite different ways, and each is good at something the other is
not. This tool puts both on one map so the difference is visible rather than described.

**Geostationary satellites** sit over the same spot on Earth and photograph it every ten
minutes. Himawari-9, which watches Australia, is one of these. The catch is distance: it is
36,000 km up, so each of its pixels covers about 2 km of ground. It notices a fire quickly but
sees it coarsely.

**Polar-orbiting satellites** fly low and fast, circling the planet pole to pole. They see far
more sharply, roughly 375 m per pixel for the VIIRS instrument. The catch is timing: they pass
over any given place only once or twice a day.

Fire agencies need both. This tool shows an hour where both were watching the same fire.

## The hour you are looking at

**9 April 2026, 04:00 to 05:00 UTC, in New South Wales.**

That hour was chosen because both kinds of satellite saw the same fire in it. That is rarer
than it sounds: of eight hours examined that day, five had no polar satellite overhead at all.

In this one hour:

- The geostationary satellite produced **six views**, ten minutes apart.
- Two polar satellites passed over: **Suomi-NPP at 04:27** and **NOAA-20 at 04:47**.

## Reading the map

Each row in the Layers panel names the algorithm, version, sensor and satellite that produced
those detections. **Warm colours** identify geostationary products; **cool colours** identify
polar-orbiting products. The exact hue separates products within those two families, and the
legend shows only the layers currently switched on.

Footprints are drawn at their true size: about 2 km for the geostationary satellite and as
little as 375 m for VIIRS. In the default **Auto** mode, a small marker carries each detection
until its footprint is large enough to see. Choose **Footprints** to hold every available
polygon at true scale, or **Points** to compare detections without their different pixel sizes.

Some sources do not publish enough information to reconstruct a footprint. Their detections
remain points in every mode rather than being given invented shapes.

Click any of them for the full detail: time, fire radiative power (a measure of how much heat
the fire is releasing), location, confidence, and which satellite and algorithm produced it.

## Why some polar shapes come in pairs

Every polar footprint is drawn as **two overlapping shapes**, and this is deliberate.

The satellite record says where a detection was and how big its pixel was, but not which side
of the satellite's flight path it fell on. At Australian latitudes those two possibilities are
meaningfully different: about a fifth of the pixel area, and up to 476 m apart at the corners.

Rather than pick one and imply a precision the data does not have, the tool draws both. The
true footprint is one of the two.

## The strip along the bottom

This is the hour's timeline. The buttons show each moment something was observed: the six
geostationary frames, and the exact instants the polar satellites passed.

Click any of them to move through the hour. The badges tell you what each satellite was doing
at that moment, either observing now or last seen some minutes ago. A frame button shows only
the corresponding ten-minute geostationary view. Polar detections retain the complete latest
pass for each satellite and product, then dim once that pass is over, because a satellite that
flew past twenty minutes ago is not telling you anything about the fire now.

## Running the detection yourself

The panel marked **Run BRIGHT** does something unusual: it runs the team's fire detection
algorithm live, on the original satellite data, while you watch.

Press it and each of the six frames is computed in turn. On the research workstation the
verified cold run took about 77 seconds per frame, or roughly eight minutes in total. The counts
appear as they finish. This is genuine computation, not a replay of stored answers, which is
why it takes time. Run it again and it returns the stored result immediately, and says so.

## What this tool is not

**It is not live.** It re-runs real satellite data from April 2026. The label on every source
says so. Only the "Current" scene shows genuinely current information, and that comes from
Geoscience Australia's operational service rather than from this project.

**The shapes are not fire boundaries.** They are the areas the satellite's individual pixels
covered. A 2 km square does not mean a 2 km fire; it means a detector that cannot see finer
than 2 km noticed heat somewhere inside it.

**The polar footprints are marked experimental.** The method for orienting them correctly at
Australian latitudes has been worked out but not yet checked against independent satellite
navigation data. The tool says so on every one of them rather than burying it.

## Getting it running

Two commands, in two terminals, from the project folder.

```
cd backend
C:\Users\nurfa\.conda\envs\bright\python.exe -m uvicorn app.main:app --port 8000
```

```
cd frontend
npm run dev
```

Then open `http://localhost:5173`.

The map, the detections and the export all work with nothing further. Running the detection
algorithm additionally needs the BRIGHT pipeline and its staged satellite data; without them
the Run panel will tell you what is missing rather than failing silently.
