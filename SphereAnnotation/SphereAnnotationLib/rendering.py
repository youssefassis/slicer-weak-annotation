# Copyright the SphereAnnotation authors. Licensed under the Apache License, Version 2.0.
"""Display maths: colour conversion and the volume-rendering opacity ramp."""

import math

#: The ramp always has this many control points, so the widget can rebuild it from the two
#: slider values alone instead of patching a control point by index and hoping the index
#: still means what it meant when it was written.
SCALAR_OPACITY_POINT_COUNT = 2

#: The ramp rises over this fraction of the volume's scalar range. A tenth of the range is
#: what the module has always used; it is proportional rather than absolute because the
#: scalar range of an angiogram depends on how it was acquired and reconstructed.
OPACITY_RAMP_FRACTION = 0.1

# vtkPiecewiseFunction node values are (x, y, midpoint, sharpness).
_MIDPOINT = 0.5
_SHARPNESS = 0.0


def to_rgb(color):
    """Convert a QColor to the 0-1 RGB triplet that VTK/MRML display nodes expect."""
    return (color.red() / 255, color.green() / 255, color.blue() / 255)


def ramp_margin(min_value, max_value, fraction=OPACITY_RAMP_FRACTION):
    """How far below the threshold the ramp starts, in scalar units.

    A fraction of the *span*, not of the maximum. Taken from the maximum alone it was 20% of
    the span for a (1000, 2000) volume, and negative — pointing the ramp the wrong way — for
    any volume whose maximum is below zero.
    """
    return (max_value - min_value) * fraction


def scalar_opacity_points(min_value, max_value, threshold, opacity, fraction=OPACITY_RAMP_FRACTION):
    """Return the opacity ramp control points for the volume rendering.

    Everything below ``threshold - margin`` is transparent and everything at or above
    ``threshold`` is drawn at ``opacity``, which is what turns a windowed angiogram into a
    vessel tree the annotator can place points on.

    ``threshold`` is clamped into ``[min_value, max_value]`` because the slider reaches both
    ends of the range, and a volume swapped underneath it can leave the value outside for as
    long as it takes the new range to be applied.

    The lower node is **not** clamped, and that is the whole point of this function. It only
    has to sit strictly below the upper one; a node below the volume's minimum is perfectly
    representable and simply means the darkest voxel actually present is already drawn at
    full opacity, which is what a threshold at the bottom of the range asks for. Clamping it
    into the range is what used to let both nodes land on the same scalar — and
    ``vtkPiecewiseFunction.AddPoint`` *replaces* a node at an x it already holds, so the ramp
    silently collapsed to a single opaque step every time the annotator dragged the threshold
    to the bottom.

    Returns ``SCALAR_OPACITY_POINT_COUNT`` lists of ``(x, y, midpoint, sharpness)``, in
    strictly ascending x — so the caller can feed them to ``AddPoint`` in order.
    """
    upper = _clamp(threshold, min_value, max_value)
    lower = upper - ramp_margin(min_value, max_value, fraction)
    if lower >= upper:
        # A constant volume leaves no span to ramp over. One float step apart is all
        # vtkPiecewiseFunction asks for, and there is nothing better to ask of a volume with
        # a single scalar value in it.
        lower = math.nextafter(upper, -math.inf)
    ramp = [(lower, 0.0), (upper, opacity)]
    return [[x, y, _MIDPOINT, _SHARPNESS] for x, y in ramp]


def default_threshold(min_value, max_value):
    """The threshold a freshly loaded volume starts at.

    A third of the way up the range is low enough that the vessels are visible without any
    fiddling, which is what the annotator needs before they can place a single point.

    A third of the way up *the volume's own range*, which ``(min + max) / 3`` only is for a
    volume whose minimum is zero. Anywhere else it drifts, and for a range that sits high it
    leaves the range altogether: a (2000, 3000) volume used to open at 1666, off the bottom
    of its own slider, so the whole volume rendered opaque.
    """
    return min_value + (max_value - min_value) / 3


def _clamp(value, low, high):
    return min(max(value, low), high)
