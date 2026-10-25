# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""Pairs of control points read as spheres."""

import numpy as np
import pytest
from SphereAnnotationLib import spheres


class TestSphereCount:
    def test_a_pair_is_one_sphere(self):
        assert spheres.sphere_count(2) == 1

    def test_no_points_is_no_spheres(self):
        assert spheres.sphere_count(0) == 0

    def test_a_lone_point_is_not_a_sphere(self):
        # It is half of one. Drawing it would mean inventing the second point.
        assert spheres.sphere_count(1) == 0

    def test_a_trailing_point_is_not_counted(self):
        assert spheres.sphere_count(7) == 3

    def test_scales(self):
        assert [spheres.sphere_count(n) for n in range(10)] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


class TestHasUnpairedPoint:
    def test_an_odd_count_is_unpaired(self):
        assert spheres.has_unpaired_point(1)
        assert spheres.has_unpaired_point(5)

    def test_an_even_count_is_complete(self):
        assert not spheres.has_unpaired_point(0)
        assert not spheres.has_unpaired_point(2)
        assert not spheres.has_unpaired_point(6)


class TestPointIndices:
    def test_the_first_sphere_is_the_first_two_points(self):
        assert spheres.point_indices(0) == (0, 1)

    def test_spheres_do_not_share_points(self):
        used = [index for sphere in range(4) for index in spheres.point_indices(sphere)]
        assert used == sorted(set(used))

    def test_the_pairing_is_contiguous(self):
        # Sphere n owns points 2n and 2n+1, with nothing skipped in between — which is what
        # makes the flat point list a complete description of the annotation.
        assert [spheres.point_indices(n) for n in range(3)] == [(0, 1), (2, 3), (4, 5)]

    def test_every_index_below_the_count_belongs_to_a_sphere(self):
        count = spheres.sphere_count(8)
        covered = {index for n in range(count) for index in spheres.point_indices(n)}
        assert covered == set(range(8))


class TestCenterAndRadius:
    def test_the_center_is_the_midpoint(self):
        center, _ = spheres.center_and_radius([0, 0, 0], [10, 0, 0])
        assert center == pytest.approx([5, 0, 0])

    def test_the_radius_is_half_the_separation(self):
        _, radius = spheres.center_and_radius([0, 0, 0], [10, 0, 0])
        assert radius == pytest.approx(5)

    def test_the_points_are_on_the_sphere(self):
        # The defining property: both points sit exactly one radius from the centre. A slip
        # to a full-diameter radius, or to the first point as the centre, breaks this.
        a, b = [1.0, -2.0, 3.5], [-4.0, 6.0, 0.5]
        center, radius = spheres.center_and_radius(a, b)
        assert np.linalg.norm(np.array(a) - center) == pytest.approx(radius)
        assert np.linalg.norm(np.array(b) - center) == pytest.approx(radius)

    def test_the_order_of_the_points_does_not_matter(self):
        a, b = [1.0, -2.0, 3.5], [-4.0, 6.0, 0.5]
        forward = spheres.center_and_radius(a, b)
        backward = spheres.center_and_radius(b, a)
        assert forward[0] == pytest.approx(backward[0])
        assert forward[1] == pytest.approx(backward[1])

    def test_coincident_points_give_a_zero_radius(self):
        # What a freshly placed pair looks like before the second point is dragged out.
        center, radius = spheres.center_and_radius([2, 2, 2], [2, 2, 2])
        assert center == pytest.approx([2, 2, 2])
        assert radius == 0.0

    def test_it_works_off_a_diagonal(self):
        # An axis-aligned-only test would pass with the radius taken from a single component.
        center, radius = spheres.center_and_radius([0, 0, 0], [2, 2, 2])
        assert center == pytest.approx([1, 1, 1])
        assert radius == pytest.approx(np.sqrt(12) / 2)

    def test_it_accepts_numpy_arrays(self):
        # Which is what the widget passes: the out-parameters of GetNthControlPointPositionWorld.
        center, radius = spheres.center_and_radius(np.array([0.0, 0.0, 0.0]), np.array([0.0, 4.0, 0.0]))
        assert center == pytest.approx([0, 2, 0])
        assert radius == pytest.approx(2)

    def test_integer_input_does_not_truncate_the_result(self):
        # Integer arrays would floor the midpoint of an odd separation without the float cast.
        center, radius = spheres.center_and_radius(np.array([0, 0, 0]), np.array([3, 0, 0]))
        assert center == pytest.approx([1.5, 0, 0])
        assert radius == pytest.approx(1.5)

    def test_the_radius_is_a_plain_float(self):
        # vtkSphereSource.SetRadius wants a number, not a 0-d numpy array.
        _, radius = spheres.center_and_radius([0, 0, 0], [1, 0, 0])
        assert isinstance(radius, float)


class TestCentersAndRadii:
    def test_matches_center_and_radius_pair_by_pair(self):
        positions = [(0, 0, 0), (10, 0, 0), (5, 5, 5), (5, 5, 9)]

        centers, radii = spheres.centers_and_radii(positions)

        for n in range(2):
            center, radius = spheres.center_and_radius(positions[2 * n], positions[2 * n + 1])
            assert centers[n] == pytest.approx(center)
            assert radii[n] == pytest.approx(radius)

    def test_a_trailing_point_is_left_out(self):
        centers, radii = spheres.centers_and_radii([(0, 0, 0), (2, 0, 0), (9, 9, 9)])

        assert centers.shape == (1, 3)
        assert radii.shape == (1,)

    def test_no_points_is_no_spheres(self):
        centers, radii = spheres.centers_and_radii(np.zeros((0, 3)))

        assert centers.shape == (0, 3)
        assert radii.shape == (0,)


class TestSphereOfPoint:
    def test_both_points_of_a_pair_belong_to_the_same_sphere(self):
        assert spheres.sphere_of_point(4) == spheres.sphere_of_point(5) == 2

    def test_inverts_point_indices(self):
        for n in range(5):
            assert all(spheres.sphere_of_point(i) == n for i in spheres.point_indices(n))
