# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""Every sphere as one mesh, copied from a single template."""

import numpy as np
import pytest
from SphereAnnotationLib import mesh

# A stand-in template: the six points of a unit octahedron and its eight triangles, in the
# offsets/connectivity layout vtkCellArray uses.
TEMPLATE = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)], dtype=float)
TRIANGLES = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
CONNECTIVITY = np.array(TRIANGLES).ravel()
OFFSETS = np.arange(0, 3 * len(TRIANGLES) + 1, 3)


class TestPlaceSphere:
    def test_scales_by_the_radius_and_moves_to_the_centre(self):
        points = mesh.place_sphere(TEMPLATE, (10, 20, 30), 2.0)

        assert points.min(axis=0) == pytest.approx([8, 18, 28])
        assert points.max(axis=0) == pytest.approx([12, 22, 32])

    def test_every_point_is_one_radius_from_the_centre(self):
        points = mesh.place_sphere(TEMPLATE, (1, 2, 3), 5.0)

        assert np.linalg.norm(points - (1, 2, 3), axis=1) == pytest.approx([5.0] * len(TEMPLATE))

    def test_a_zero_radius_collapses_onto_the_centre(self):
        # What a freshly placed pair looks like; it must not raise.
        assert mesh.place_sphere(TEMPLATE, (4, 5, 6), 0.0) == pytest.approx(np.tile((4, 5, 6), (6, 1)))


class TestPlaceSpheres:
    def test_one_template_copy_per_sphere_in_order(self):
        centers = [(0, 0, 0), (100, 0, 0)]
        points = mesh.place_spheres(TEMPLATE, centers, [1.0, 3.0])

        assert points.shape == (2 * len(TEMPLATE), 3)
        assert points[: len(TEMPLATE)] == pytest.approx(mesh.place_sphere(TEMPLATE, centers[0], 1.0))
        assert points[len(TEMPLATE) :] == pytest.approx(mesh.place_sphere(TEMPLATE, centers[1], 3.0))

    def test_no_spheres_is_no_points(self):
        assert mesh.place_spheres(TEMPLATE, np.zeros((0, 3)), []).shape == (0, 3)


class TestTileCells:
    def test_each_copy_refers_to_its_own_points(self):
        _, connectivity = mesh.tile_cells(OFFSETS, CONNECTIVITY, 3, len(TEMPLATE))

        per_copy = len(CONNECTIVITY)
        for k in range(3):
            assert list(connectivity[k * per_copy : (k + 1) * per_copy]) == list(CONNECTIVITY + k * len(TEMPLATE))

    def test_offsets_count_every_cell_of_every_copy(self):
        offsets, connectivity = mesh.tile_cells(OFFSETS, CONNECTIVITY, 3, len(TEMPLATE))

        assert len(offsets) == 3 * len(TRIANGLES) + 1
        assert offsets[0] == 0
        assert offsets[-1] == len(connectivity)
        assert set(np.diff(offsets)) == {3}

    def test_keeps_the_integer_type_vtk_needs(self):
        offsets, connectivity = mesh.tile_cells(OFFSETS.astype(np.int64), CONNECTIVITY.astype(np.int64), 2, 6)

        assert offsets.dtype == np.int64
        assert connectivity.dtype == np.int64

    def test_no_copies_is_no_cells(self):
        offsets, connectivity = mesh.tile_cells(OFFSETS, CONNECTIVITY, 0, len(TEMPLATE))

        assert list(offsets) == [0]
        assert len(connectivity) == 0
