# Annotation format

An annotation produced by this module is **an ordinary Slicer markups fiducial node**. There
is no format of our own: the module reads and writes markups through
`slicer.util.loadMarkups` and Slicer's Save Data dialog, so the files are whatever Slicer
writes — `.mrk.json` by default in Slicer 5, or legacy `.fcsv`.

What *is* ours is the convention layered on top of it, and it is the whole contract:

> **Each consecutive pair of control points defines one sphere.** The two points sit at
> opposite ends of a diameter. Sphere *n* is control points *2n* and *2n+1*.

So for points `P0, P1, P2, P3, …`:

| sphere | points | centre | radius |
| --- | --- | --- | --- |
| 0 | `P0`, `P1` | `(P0 + P1) / 2` | `‖P0 − P1‖ / 2` |
| 1 | `P2`, `P3` | `(P2 + P3) / 2` | `‖P2 − P3‖ / 2` |

Positions are **RAS world coordinates, in millimetres** — so a radius is a radius in
millimetres, and an annotation stays meaningful next to the volume it was made on.

`SphereAnnotationLib/spheres.py` is the executable statement of the above, and
`tests/test_spheres.py` is what holds it in place.

## What follows from it

- **Order is meaningful.** The point list is not a set. Reordering control points re-pairs
  the spheres into different ones.
- **There is no per-sphere record.** A sphere has no identity, name or attribute of its own —
  only the two points. Anything a consumer wants to attach to a sphere has to go on its
  points.
- **Removing a point from the middle re-pairs everything after it.** This is why the module's
  **Remove** button removes only the *last* point. Deleting an interior point from the
  Markups module is allowed, and will shuffle every sphere beyond it; that is a property of
  the format, not a bug in the module.
- **An odd number of points means the last sphere is half-placed.** It is drawn as nothing.
  This is the normal state between the two clicks of a pair, so it is not an error and is not
  reported as one — but a *saved* annotation with an odd point count is almost certainly
  unfinished.
- **A pair may be coincident.** The radius is then zero. Again the normal state for the
  moment between placing the second point and dragging it out.
- **Nothing enforces this on the file.** Any markups file loads. A file that was not written
  under this convention will still be read as pairs, which is meaningless but harmless.

## Reading an annotation elsewhere

Slicer's `.mrk.json` holds control points under `markups[0].controlPoints`, each with a
`position` triple. In Python, outside Slicer:

```python
import json, math

with open("annotation.mrk.json") as f:
    points = [p["position"] for p in json.load(f)["markups"][0]["controlPoints"]]

for a, b in zip(points[::2], points[1::2]):
    center = [(x + y) / 2 for x, y in zip(a, b)]
    radius = math.dist(a, b) / 2
    print(center, radius)
```

`zip` without `strict=True` is what silently drops a trailing unpaired point, which is the
behaviour the module has too.

Note that `.mrk.json` records a `coordinateSystem` — `"LPS"` or `"RAS"`. Slicer writes LPS by
default while the module works in RAS, so a reader outside Slicer must honour that field
rather than assuming. Slicer itself converts on load.

Or skip the arithmetic: **Export CSV** writes the spheres themselves, one row per sphere
with `label,sphere,center_r,center_a,center_s,radius`, already in RAS. That table is derived
from the points and never read back — the markups file stays the annotation.

## Changing this

The convention is not versioned and nothing in a file declares it. A change to the pairing
rule is therefore **a breaking change for every annotation ever saved**, with no way for a
reader to tell old from new. If it has to happen, it needs a marker in the file — a node
attribute or a naming convention — decided before the change, not after.
