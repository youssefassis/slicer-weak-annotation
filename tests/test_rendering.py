# Copyright the SphereAnnotation authors. Licensed under the Apache License, Version 2.0.
"""Colour conversion and the volume-rendering opacity ramp."""

import pytest
from SphereAnnotationLib import rendering


class FakeQColor:
    """Stands in for a QColor, which only exists inside Slicer."""

    def __init__(self, r, g, b):
        self._rgb = (r, g, b)

    def red(self):
        return self._rgb[0]

    def green(self):
        return self._rgb[1]

    def blue(self):
        return self._rgb[2]


class TestToRGB:
    def test_scales_bytes_to_the_unit_range(self):
        assert rendering.to_rgb(FakeQColor(255, 128, 0)) == pytest.approx([1.0, 128 / 255, 0.0])

    def test_black_and_white_land_on_the_ends(self):
        assert rendering.to_rgb(FakeQColor(0, 0, 0)) == (0, 0, 0)
        assert rendering.to_rgb(FakeQColor(255, 255, 255)) == (1, 1, 1)

    def test_channels_are_not_transposed(self):
        # An (r, g, g) style slip here silently drops one channel of the annotator's choice.
        assert rendering.to_rgb(FakeQColor(10, 20, 30)) == pytest.approx([10 / 255, 20 / 255, 30 / 255])


class TestDefaultThreshold:
    def test_a_fresh_volume_starts_a_third_of_the_way_up(self):
        assert rendering.default_threshold(0, 300) == pytest.approx(100)

    def test_it_is_a_third_of_the_range_and_not_of_the_sum(self):
        # `(min + max) / 3` agrees with a third of the way up only when min is 0, which is
        # why the zero-based case above passed while every other volume drifted.
        assert rendering.default_threshold(100, 200) == pytest.approx(133 + 1 / 3)
        assert rendering.default_threshold(-1024, 3071) == pytest.approx(341)

    def test_a_range_that_sits_high_still_starts_inside_it(self):
        # The case that reached the slider as an out-of-range value and was clamped to the
        # bottom, opening the volume fully opaque.
        assert rendering.default_threshold(2000, 3000) == pytest.approx(2333 + 1 / 3)

    def test_it_stays_inside_the_range(self):
        for low, high in [(0, 1), (-1000, 3000), (100, 200), (2000, 3000), (-2000, -100)]:
            assert low <= rendering.default_threshold(low, high) <= high

    def test_it_is_strictly_inside_a_range_with_room_in_it(self):
        # `low <= threshold` alone passes for a threshold pinned to the bottom of the range,
        # which is the failure it is meant to catch.
        for low, high in [(0, 1), (100, 200), (2000, 3000)]:
            assert low < rendering.default_threshold(low, high) < high


class TestScalarOpacityPoints:
    def points(self, *args, **kwargs):
        return rendering.scalar_opacity_points(*args, **kwargs)

    def test_the_point_count_is_fixed(self):
        assert len(self.points(0, 1000, 500, 1.0)) == rendering.SCALAR_OPACITY_POINT_COUNT

    def test_every_point_is_a_piecewise_function_node(self):
        # vtkPiecewiseFunction node values are (x, y, midpoint, sharpness); a 2-tuple here
        # would be accepted by the list and then fail at AddPoint.
        assert all(len(point) == 4 for point in self.points(0, 1000, 500, 1.0))

    def test_the_scalars_ascend_strictly(self):
        # Strictly: `sorted` accepts a tie, and a tie is the actual failure. AddPoint at an x
        # the function already holds replaces that node instead of adding one, so two equal
        # scalars leave a one-node function — opaque everywhere, with no ramp at all.
        for threshold in [-500, 0, 1, 250, 999, 1000, 5000]:
            xs = [point[0] for point in self.points(0, 1000, threshold, 1.0)]
            assert xs[0] < xs[1], threshold

    def test_the_scalars_ascend_strictly_whatever_the_range(self):
        ranges = [(0, 1000), (-1024, 3071), (-2000, -100), (1000, 2000), (2000, 3000), (0, 1)]
        for min_value, max_value in ranges:
            for threshold in [min_value, (min_value + max_value) / 2, max_value]:
                xs = [point[0] for point in self.points(min_value, max_value, threshold, 1.0)]
                assert xs[0] < xs[1], (min_value, max_value, threshold)

    def test_a_constant_volume_still_gives_two_distinct_scalars(self):
        # No span to ramp over, and still not allowed to hand AddPoint the same x twice.
        xs = [point[0] for point in self.points(500, 500, 500, 1.0)]
        assert xs[0] < xs[1]

    def test_the_ramp_reaches_the_requested_opacity(self):
        _, upper = self.points(0, 1000, 500, 0.7)
        assert upper[0] == pytest.approx(500)
        assert upper[1] == pytest.approx(0.7)

    def test_below_the_ramp_is_transparent(self):
        lower, _ = self.points(0, 1000, 500, 0.7)
        assert lower[1] == 0.0

    def test_the_ramp_starts_a_tenth_of_the_range_below_the_threshold(self):
        lower, _ = self.points(0, 1000, 500, 1.0)
        assert lower[0] == pytest.approx(400)

    def test_a_threshold_above_the_range_is_clamped_into_it(self):
        # The slider maximum is set from the volume, but a volume swapped underneath it can
        # leave the value out of range for as long as it takes the new maximum to be applied.
        lower, upper = self.points(0, 1000, 5000, 1.0)
        assert upper[0] == pytest.approx(1000)
        assert 0 <= lower[0] <= 1000

    def test_a_threshold_below_the_range_is_clamped_into_it(self):
        lower, upper = self.points(0, 1000, -5000, 1.0)
        assert upper[0] == pytest.approx(0)
        # And the lower node drops below the minimum rather than joining it there. Nothing in
        # the volume is that dark, so the ramp is fully risen by the time it meets real data
        # — which is what a threshold at the bottom of the range means.
        assert lower[0] < 0

    def test_the_threshold_never_leaves_the_range(self):
        for threshold in [-5000, 0, 500, 1000, 5000]:
            _, upper = self.points(0, 1000, threshold, 1.0)
            assert 0 <= upper[0] <= 1000, threshold

    def test_a_negative_range_still_ascends(self):
        # CT in Hounsfield units starts around -1024.
        xs = [point[0] for point in self.points(-1024, 3071, 200, 1.0)]
        assert xs[0] < xs[1]
        assert xs[0] == pytest.approx(200 - (3071 + 1024) / 10)

    def test_a_range_with_a_negative_maximum_still_ascends(self):
        # The margin taken from the maximum alone was negative here, which put the lower node
        # above the upper one before the clamp dragged the two together.
        xs = [point[0] for point in self.points(-2000, -100, -500, 1.0)]
        assert xs[0] < xs[1]
        assert xs[0] == pytest.approx(-500 - 190)

    def test_opacity_is_passed_through_untouched(self):
        # It used to be halved between the slider and the display node, so the top of the
        # slider's travel meant half opacity.
        for opacity in [0.0, 0.25, 1.0]:
            assert self.points(0, 1000, 500, opacity)[1][1] == pytest.approx(opacity)


class TestRampMargin:
    def test_it_is_a_tenth_of_the_span(self):
        assert rendering.ramp_margin(0, 1000) == pytest.approx(100)

    def test_the_span_is_measured_from_the_minimum_not_from_zero(self):
        assert rendering.ramp_margin(1000, 2000) == pytest.approx(100)
        assert rendering.ramp_margin(-1024, 3071) == pytest.approx(409.5)

    def test_it_is_positive_for_a_range_that_is_entirely_negative(self):
        # A margin of `max * fraction` was negative here, and a negative margin puts the foot
        # of the ramp above its top.
        assert rendering.ramp_margin(-2000, -100) == pytest.approx(190)

    def test_the_fraction_is_overridable(self):
        assert rendering.ramp_margin(0, 1000, fraction=0.5) == pytest.approx(500)
