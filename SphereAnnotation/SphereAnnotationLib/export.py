# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""The spheres as a table, for pipelines that do not read Slicer markups.

One row per sphere: which annotation it came from, its position within it, its centre and its
radius. The markups file stays the annotation itself — this is a derived view of it, written
out on request, and it is not read back.
"""

import csv

from SphereAnnotationLib import spheres

#: Column order of the exported table. Coordinates are RAS millimetres, as the points are.
CSV_COLUMNS = ("label", "sphere", "center_r", "center_a", "center_s", "radius")


def sphere_rows(annotations):
    """Return one row per whole sphere in ``annotations``.

    ``annotations`` is an iterable of ``(label, positions)``, where ``positions`` is the
    sequence of control-point positions of one markups node. ``sphere`` counts from zero
    within each annotation, following the pairing in :mod:`SphereAnnotationLib.spheres`; a
    trailing unpaired point defines no sphere and so produces no row.
    """
    rows = []
    for label, positions in annotations:
        for index in range(spheres.sphere_count(len(positions))):
            first, second = spheres.point_indices(index)
            center, radius = spheres.center_and_radius(positions[first], positions[second])
            rows.append({
                "label": label,
                "sphere": index,
                "center_r": float(center[0]),
                "center_a": float(center[1]),
                "center_s": float(center[2]),
                "radius": radius,
            })
    return rows


def write_csv(path, rows):
    """Write ``rows`` from :func:`sphere_rows` to ``path``, with a header line."""
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
