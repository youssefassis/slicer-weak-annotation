# Copyright the SphereAnnotation authors. Licensed under the Apache License, Version 2.0.
"""Display maths: colour conversion and the volume-rendering opacity ramp."""

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


def ramp_margin(max_value, fraction=OPACITY_RAMP_FRACTION):
    """How far below the threshold the ramp starts, in scalar units."""
    return max_value * fraction


def scalar_opacity_points(min_value, max_value, threshold, opacity, fraction=OPACITY_RAMP_FRACTION):
    """Return the opacity ramp control points for the volume rendering.

    Everything below ``threshold - margin`` is transparent and everything at or above
    ``threshold`` is drawn at ``opacity``, which is what turns a windowed angiogram into a
    vessel tree the annotator can place points on.

    Both scalars are clamped into ``[min_value, max_value]`` because the threshold slider
    reaches both ends of the range: a control point outside it would leave the node scalars
    non-ascending, which ``vtkPiecewiseFunction`` cannot represent. The lower point is then
    held strictly below the upper one, so a threshold at the bottom of the range degrades to
    a step rather than to two points sharing an x.

    Returns ``SCALAR_OPACITY_POINT_COUNT`` lists of ``(x, y, midpoint, sharpness)``, in
    ascending x — so the caller can feed them to ``AddPoint`` in order.
    """
    upper = _clamp(threshold, min_value, max_value)
    lower = _clamp(upper - ramp_margin(max_value, fraction), min_value, upper)
    ramp = [(lower, 0.0), (upper, opacity)]
    return [[x, y, _MIDPOINT, _SHARPNESS] for x, y in ramp]


def default_threshold(min_value, max_value):
    """The threshold a freshly loaded volume starts at.

    A third of the way up the range is low enough that the vessels are visible without any
    fiddling, which is what the annotator needs before they can place a single point.
    """
    return (min_value + max_value) / 3


def _clamp(value, low, high):
    return min(max(value, low), high)
