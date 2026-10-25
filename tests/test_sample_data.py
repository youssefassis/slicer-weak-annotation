# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""The committed sample case: still loadable, and still describing the image it ships with.

The case in ``data/sample_case/`` is what a new user opens first, so it failing to load is a
bad first impression of the module. These tests guard the two ways that happens: the annotation
drifting from ``tools/make_sample_data.py`` (edited by hand, or the tool changed without
regenerating), and a sphere ceasing to sit on the target drawn for it.

The volume's *content* is not re-rasterised here — that takes seconds, and the geometry it is
drawn from is the same constants this file checks the annotation against.
"""

import gzip
import json
import struct
from pathlib import Path

import make_sample_data as gen
import numpy as np
import pytest
from SphereAnnotationLib import spheres

CASE = Path(__file__).parent.parent / "data" / "sample_case"
VOLUME = CASE / gen.VOLUME_NAME
ANNOTATION = CASE / gen.ANNOTATION_NAME


def read_nifti_header(path):
    """Return the fields of ``path``'s NIfTI-1 header that matter here.

    A reader for what :func:`make_sample_data.write_volume` writes, independent of the writer:
    it re-reads the offsets from the standard rather than sharing the packing code, so a field
    written to the wrong offset fails here instead of round-tripping.
    """
    with gzip.open(path, "rb") as f:
        header = f.read(348)
    dim = struct.unpack_from("<8h", header, 40)
    srow = [struct.unpack_from("<4f", header, offset) for offset in (280, 296, 312)]
    return {
        "sizeof_hdr": struct.unpack_from("<i", header, 0)[0],
        "magic": struct.unpack_from("<4s", header, 344)[0],
        "datatype": struct.unpack_from("<h", header, 70)[0],
        "bitpix": struct.unpack_from("<h", header, 72)[0],
        "vox_offset": struct.unpack_from("<f", header, 108)[0],
        "sform_code": struct.unpack_from("<h", header, 254)[0],
        "xyzt_units": struct.unpack_from("<B", header, 123)[0],
        "ndim": dim[0],
        "shape": dim[1:4],
        "spacing": struct.unpack_from("<8f", header, 76)[1:4],
        "origin": tuple(row[3] for row in srow),
        "direction": [row[:3] for row in srow],
    }


@pytest.fixture(scope="module")
def header():
    return read_nifti_header(VOLUME)


@pytest.fixture(scope="module")
def positions():
    """The annotation's control points, read the way a consumer outside Slicer would."""
    markup = json.loads(ANNOTATION.read_text())["markups"][0]
    assert markup["coordinateSystem"] == "RAS", "the targets are authored in RAS"
    return [point["position"] for point in markup["controlPoints"]]


class TestTheCaseIsPresent:
    def test_both_files_are_committed(self):
        assert VOLUME.is_file()
        assert ANNOTATION.is_file()

    def test_the_volume_stays_small_enough_to_keep_in_git(self):
        assert VOLUME.stat().st_size < 1_000_000


class TestTheVolume:
    def test_is_a_single_file_nifti1_of_int16(self, header):
        assert header["sizeof_hdr"] == 348
        assert header["magic"] == b"n+1\0"
        assert header["datatype"] == 4  # DT_INT16
        assert header["bitpix"] == 16
        assert header["vox_offset"] == 352

    def test_declares_its_geometry_in_millimetres(self, header):
        assert header["ndim"] == 3
        assert header["sform_code"] == 1  # NIFTI_XFORM_SCANNER_ANAT
        assert header["xyzt_units"] == 2  # NIFTI_UNITS_MM
        assert header["spacing"] == pytest.approx((gen.SPACING,) * 3)

    def test_maps_voxels_to_the_ras_millimetres_the_annotation_uses(self, header):
        assert header["direction"] == pytest.approx(np.diag([gen.SPACING] * 3))
        for (low, _), origin in zip(gen.BOUNDS, header["origin"], strict=True):
            assert origin == pytest.approx(low + gen.SPACING / 2)

    def test_covers_the_extent_it_was_authored_in(self, header):
        for (low, high), size in zip(gen.BOUNDS, header["shape"], strict=True):
            assert size == round((high - low) / gen.SPACING)


class TestTheAnnotation:
    def test_is_exactly_what_the_generator_produces(self):
        # So a hand-edit of the sample, or a change to the tool that was never regenerated,
        # shows up here rather than in Slicer.
        assert ANNOTATION.read_text() == json.dumps(gen.annotation_file(), indent=2) + "\n"

    def test_holds_two_control_points_per_target(self, positions):
        assert len(positions) == 2 * len(gen.TARGETS)
        assert spheres.sphere_count(len(positions)) == len(gen.TARGETS)

    def test_has_no_half_placed_pair(self, positions):
        # An odd count draws the last sphere as nothing, which in a shipped sample would look
        # like the module losing a sphere.
        assert len(positions) % 2 == 0

    def test_every_sphere_lands_on_the_target_that_was_drawn_for_it(self, positions):
        # The join that makes the sample worth shipping: the sphere the module derives from a
        # pair is the sphere the generator rasterised, so the overlay sits on the target.
        for target, (a, b) in zip(gen.TARGETS, zip(positions[::2], positions[1::2], strict=True), strict=True):
            drawn_centre, drawn_radius = gen.sphere_of(target)
            centre, radius = spheres.center_and_radius(a, b)
            assert centre == pytest.approx(drawn_centre)
            assert radius == pytest.approx(drawn_radius)

    def test_every_sphere_sits_inside_the_volume(self, positions, header):
        low = np.array(header["origin"])
        high = low + (np.array(header["shape"]) - 1) * gen.SPACING
        for a, b in zip(positions[::2], positions[1::2], strict=True):
            centre, radius = spheres.center_and_radius(a, b)
            assert np.all(np.array(centre) - radius >= low)
            assert np.all(np.array(centre) + radius <= high)

    def test_the_decoy_is_not_annotated(self, positions):
        # The decoy is drawn so the sample has something the annotator is meant to leave alone.
        # If a sphere ever lands on it, the sample is teaching the opposite of what it means to.
        for _, decoy_centre in gen.DECOYS:
            for a, b in zip(positions[::2], positions[1::2], strict=True):
                centre, _ = spheres.center_and_radius(a, b)
                assert np.linalg.norm(np.array(centre) - decoy_centre) > 5.0
