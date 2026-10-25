# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""Every sphere as one mesh, copied from a single template.

All spheres are the same shape, so the module tessellates one unit sphere once and places a
copy of it per sphere: scaled by the radius, moved to the centre. The copies live in one
points array, so a dragged point rewrites only its own sphere's slice of it instead of
re-tessellating and re-appending every sphere — at 200 spheres, the difference between about
100 ms and well under one per drag event, measured in Slicer 5.12.4.

Normals and triangles never change: a uniform positive scale and a translation leave every
normal as it was, and the triangles only ever refer to a sphere's own points.
"""

import numpy as np


def place_sphere(template_points, center, radius):
    """Return ``template_points`` (a unit sphere at the origin) scaled to ``radius`` at ``center``."""
    return np.asarray(template_points) * radius + np.asarray(center)


def place_spheres(template_points, centers, radii):
    """Return the points of every sphere, one template copy after another, as ``(n * p, 3)``."""
    template = np.asarray(template_points)
    radii = np.asarray(radii, dtype=float).reshape(-1, 1, 1)
    centers = np.asarray(centers, dtype=float).reshape(-1, 1, 3)
    return (template[np.newaxis] * radii + centers).reshape(-1, 3)


def tile_cells(offsets, connectivity, count, points_per_sphere):
    """Return the ``(offsets, connectivity)`` of ``count`` copies of one sphere's cells.

    In the layout ``vtkCellArray.SetData`` takes: ``offsets`` has one entry per cell plus a
    leading zero, and copy *k* refers to points ``k * points_per_sphere`` onwards — the slice
    :func:`place_spheres` put it in.
    """
    offsets = np.asarray(offsets)
    connectivity = np.asarray(connectivity)
    copies = np.arange(count)
    tiled_connectivity = (connectivity[np.newaxis] + (copies * points_per_sphere)[:, np.newaxis]).ravel()
    tiled_offsets = (offsets[np.newaxis, 1:] + (copies * offsets[-1])[:, np.newaxis]).ravel()
    return np.concatenate([[0], tiled_offsets]).astype(offsets.dtype), tiled_connectivity.astype(connectivity.dtype)
