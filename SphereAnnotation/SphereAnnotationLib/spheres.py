# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""The annotation itself: pairs of control points read as spheres.

An annotation is a flat list of markup control points in which **each consecutive pair
defines one sphere** — the two points sit at opposite ends of a diameter, so the sphere is
centred on their midpoint with a radius of half their separation. That convention is the
entire format (see ``docs/annotation-format.md``), and it is what lets the annotator drag
either point in any view and have the sphere follow.

The maths is here rather than in the widget because it is a function of six numbers: it can
be tested without launching Slicer, which is the point of the boundary this package sits
behind.
"""

import numpy as np

#: Control points per sphere — the two ends of a diameter.
POINTS_PER_SPHERE = 2


def sphere_count(point_count):
    """How many whole spheres ``point_count`` control points define.

    A trailing point with no partner defines nothing yet, so it is not counted. That is the
    state the annotator is in for as long as it takes to place the second point of a pair.
    """
    return point_count // POINTS_PER_SPHERE


def has_unpaired_point(point_count):
    """Whether the last control point is still waiting for its partner.

    Worth asking before treating a node as finished: an odd point count means one sphere is
    half-placed, and nothing downstream will draw it.
    """
    return point_count % POINTS_PER_SPHERE != 0


def point_indices(sphere_index):
    """Return the ``(first, second)`` control-point indices defining sphere ``sphere_index``.

    Spheres are positionally tied to the points that define them: sphere *n* is always points
    *2n* and *2n+1*. Nothing renumbers, so removing a point from the middle of a node
    re-pairs every sphere after it — which is why the only removal the UI offers is of the
    last point.
    """
    first = sphere_index * POINTS_PER_SPHERE
    return first, first + 1


def center_and_radius(first, second):
    """Return ``(center, radius)`` for the sphere spanned by two diametrically opposed points.

    ``center`` is a length-3 float array and ``radius`` a float, both in the units the points
    came in — RAS millimetres, when they come from a markups node. Two coincident points give
    a radius of zero rather than an error: that is what a freshly placed pair looks like
    before the annotator drags the second point out, and a zero-radius sphere source is
    harmless.
    """
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    return (a + b) / 2, float(np.linalg.norm(a - b)) / 2
