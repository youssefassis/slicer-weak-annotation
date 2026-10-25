# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""Regenerate the sample case in ``data/sample_case/``.

The case is a synthetic angiogram — bright vessels on a dark background, the way a subtracted
or MR angiogram looks — plus a finished annotation of it. No patient data is involved, which
is why the result can be committed.

The volume is the same phantom the sibling ReformatViz extension ships, drawn from the same
constants, so the two projects can be demonstrated on one case. Only the NIfTI ``descrip``
string differs; the voxels are identical.

Both files come out of :data:`TARGETS` below, so the annotation cannot drift away from the
targets drawn in the image: the same base and tip are what get rasterised *and* what get
written as the two control points of a sphere. That join is the whole reason the sample is worth
shipping — the sphere the module derives from a pair lands **on** the target, not near it.

The output is deterministic: same constants, same bytes. Regenerating it should leave
``git status`` clean.

Run it with an interpreter that has numpy — the dev environment, or Slicer's::

    python tools/make_sample_data.py
    /Applications/Slicer.app/Contents/bin/PythonSlicer tools/make_sample_data.py

This is a development tool, not part of the extension: it is not listed in
``SphereAnnotation/CMakeLists.txt`` and nothing in ``SphereAnnotation/`` imports it.
"""

import gzip
import itertools
import json
import struct
from pathlib import Path

import numpy as np

#: Where the case is written, relative to the repository root.
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_case"

VOLUME_NAME = "volume.nii.gz"
ANNOTATION_NAME = "annotation.mrk.json"

#: Voxel size in mm, isotropic — around what a 3D-rotational angiogram is reconstructed at.
SPACING = 0.5

#: Volume extent in RAS millimetres: a 68 x 60 x 50 mm block around the circle of Willis.
#: Everything below is authored in these coordinates, which are also the coordinates the
#: annotation speaks — see docs/annotation-format.md.
BOUNDS = ((-34.0, 34.0), (-30.0, 30.0), (-20.0, 30.0))

#: Intensities. Arbitrary units, like an angiogram that has been windowed: dark tissue,
#: bright contrast-filled lumen.
BACKGROUND = 40
FOREGROUND = 900

#: Peak-to-peak amplitude of the background texture, and how many voxels one grain spans.
#: Grainy rather than per-voxel noise: it looks like an acquisition and it compresses, which
#: keeps the committed volume small. Per-voxel noise is incompressible and would take this
#: file from ~100 KiB to well over a megabyte.
NOISE = 36
NOISE_GRAIN = 4

#: Fixed so the volume is reproducible byte for byte.
SEED = 20250727

#: Width in mm of the soft edge on every structure, so surfaces do not come out as stair steps
#: under volume rendering.
EDGE = 1.5 * SPACING

#: The arterial tree: ``(radius in mm, centre-line through RAS points)``. A crude circle of
#: Willis — enough that the annotator is looking at a bifurcation rather than at a lone blob,
#: not an anatomical model.
VESSELS = (
    # Internal carotid arteries, rising through the siphon to the terminus.
    (2.0, ((16, -12, -16), (15, -8, -10), (14, -2, -6), (13, 3, -3), (13, 4.5, 1), (13, 5, 4))),
    (2.0, ((-16, -12, -16), (-15, -8, -10), (-14, -2, -6), (-13, 3, -3), (-13, 4.5, 1), (-13, 5, 4))),
    # Middle cerebral arteries: M1 laterally to the bifurcation, then two M2 branches.
    (1.6, ((13, 5, 4), (17, 4, 5), (21, 3.5, 6), (24, 3.5, 6.8))),
    (1.1, ((24, 3.5, 6.8), (25, 1.5, 12), (25.5, -1, 18))),
    (1.1, ((24, 3.5, 6.8), (25, 6, 10), (24.5, 9, 15))),
    (1.6, ((-13, 5, 4), (-17, 4, 5), (-21, 3.5, 6), (-24, 3.5, 6.8))),
    (1.1, ((-24, 3.5, 6.8), (-25, 1.5, 12), (-25.5, -1, 18))),
    (1.1, ((-24, 3.5, 6.8), (-25, 6, 10), (-24.5, 9, 15))),
    # Anterior cerebral arteries: A1 medially, the communicating artery across the midline,
    # then A2 climbing anteriorly.
    (1.3, ((13, 5, 4), (9, 9, 6), (4, 11, 7), (2, 11.5, 7.5))),
    (1.3, ((-13, 5, 4), (-9, 9, 6), (-4, 11, 7), (-2, 11.5, 7.5))),
    (0.8, ((2, 11.5, 7.5), (0, 12, 7.6), (-2, 11.5, 7.5))),
    (1.1, ((2, 11.5, 7.5), (2, 14, 12), (2.5, 15, 20), (2, 14, 26))),
    (1.1, ((-2, 11.5, 7.5), (-2, 14, 12), (-2.5, 15, 20), (-2, 14, 26))),
    # Vertebral arteries joining into the basilar, and the posterior cerebral arteries.
    (1.1, ((5, -21, -19.5), (2, -20, -19), (0, -19, -19))),
    (1.1, ((-5, -21, -19.5), (-2, -20, -19), (0, -19, -19))),
    (1.5, ((0, -19, -19), (0, -18, -12), (0.5, -16, -5), (0, -14, 0), (0, -13.5, 2))),
    (1.1, ((0, -13.5, 2), (5, -13, 4), (11, -11, 6), (16, -13, 8))),
    (1.1, ((0, -13.5, 2), (-5, -13, 4), (-11, -11, 6), (-16, -13, 8))),
)

#: The objects to annotate — aneurysm-like bulges off the vessels. Each is drawn as a sphere
#: from its base on the vessel wall to its tip *and* written to the annotation as that same
#: pair of control points, so the module's sphere lands on the target.
#:
#: ``note`` is for ``data/README.md``; it is not written to the annotation, because the format
#: has nowhere to put per-sphere information — see docs/annotation-format.md.
TARGETS = (
    {
        "base": (24.0, 3.5, 6.8),
        "tip": (29.0, 2.6, 9.0),
        "note": "right MCA bifurcation, 5.5 mm — the unmistakable one",
    },
    {
        "base": (0.0, 12.0, 8.0),
        "tip": (0.8, 15.7, 11.2),
        "note": "anterior communicating artery, 5.0 mm, pointing anterosuperiorly",
    },
    {
        "base": (-14.5, 6.0, 4.9),
        "tip": (-16.6, 7.4, 6.1),
        "note": "left ICA terminus, 2.8 mm — small enough to be a genuine judgement call",
    },
)

#: Drawn, but deliberately not annotated: a bright thing that is not a target. It gives the
#: sample something the annotator is meant to leave alone, and it is why the committed
#: annotation has three spheres rather than four.
DECOYS = ((1.5, (-20.0, -9.0, -6.0)),)


def _midpoint(a, b):
    return (np.asarray(a, dtype=float) + np.asarray(b, dtype=float)) / 2


def _grid():
    """Return the RAS coordinate of every voxel centre, and the volume's shape and origin."""
    axes = [np.arange(lo + SPACING / 2, hi, SPACING, dtype=np.float32) for lo, hi in BOUNDS]
    origin = tuple(float(axis[0]) for axis in axes)
    x, y, z = np.meshgrid(*axes, indexing="ij")
    return (x, y, z), tuple(len(axis) for axis in axes), origin


def _fill_capsule(fill, grid, a, b, radius):
    """Raise ``fill`` towards 1 inside the capsule of ``radius`` around segment ``a``-``b``.

    A capsule rather than a cylinder so consecutive segments of a centre-line join without a
    notch at the corner. The fraction is a soft ramp across :data:`EDGE`, which is what keeps
    the surfaces from looking like stair steps under volume rendering.
    """
    x, y, z = grid
    a = np.asarray(a, dtype=np.float32)
    ab = np.asarray(b, dtype=np.float32) - a
    px, py, pz = x - a[0], y - a[1], z - a[2]

    # A sphere is drawn as a zero-length segment: the floor keeps the division defined, and the
    # numerator is zero there too, so the projection stays at ``a``.
    length2 = max(float(ab @ ab), 1e-12)
    t = np.clip((px * ab[0] + py * ab[1] + pz * ab[2]) / length2, 0.0, 1.0)

    distance = np.sqrt((px - t * ab[0]) ** 2 + (py - t * ab[1]) ** 2 + (pz - t * ab[2]) ** 2)
    np.maximum(fill, np.clip((radius + EDGE / 2 - distance) / EDGE, 0.0, 1.0), out=fill)


def sphere_of(target):
    """Return the ``(centre, radius)`` the module derives from a target's two points.

    The single definition of the pairing, used both to rasterise the target and to check the
    committed annotation against it.
    """
    base = np.asarray(target["base"], dtype=float)
    tip = np.asarray(target["tip"], dtype=float)
    return _midpoint(base, tip), float(np.linalg.norm(tip - base) / 2)


def _build_volume(grid, shape):
    """Return the phantom as ``int16``, indexed ``[i, j, k]``."""
    fill = np.zeros(shape, dtype=np.float32)

    for radius, centreline in VESSELS:
        for a, b in itertools.pairwise(centreline):
            _fill_capsule(fill, grid, a, b, radius)

    for target in TARGETS:
        # The target as a sphere on the base-to-tip axis, plus a short neck of the same radius,
        # which is what stops it reading as a ball floating beside the vessel.
        centre, radius = sphere_of(target)
        _fill_capsule(fill, grid, centre, centre, radius)
        _fill_capsule(fill, grid, target["base"], centre, radius * 0.55)

    for radius, centre in DECOYS:
        _fill_capsule(fill, grid, centre, centre, radius)

    volume = BACKGROUND + (FOREGROUND - BACKGROUND) * fill
    volume += _texture(shape)
    return np.rint(volume).astype(np.int16)


def _texture(shape):
    """Return grainy background texture of the shape given.

    Drawn at one value per :data:`NOISE_GRAIN` voxels and repeated, so it reads as acquisition
    texture and still compresses — per-voxel noise would multiply the size of the committed
    volume.
    """
    rng = np.random.default_rng(SEED)
    coarse = tuple(-(-n // NOISE_GRAIN) for n in shape)
    grain = rng.uniform(-NOISE / 2, NOISE / 2, size=coarse).astype(np.float32)
    for axis in range(grain.ndim):
        grain = np.repeat(grain, NOISE_GRAIN, axis=axis)
    return grain[: shape[0], : shape[1], : shape[2]]


def _nifti_header(shape, origin):
    """Return a 348-byte NIfTI-1 header for an ``int16`` volume with an identity direction.

    Hand-packed rather than written with nibabel, which the project does not depend on and
    would not use anywhere else — adding it to ``requirements-dev.txt`` would install it on
    every CI run for a script CI never executes. Fields are placed at the offsets fixed by the
    NIfTI-1 standard (nifti1.h); everything not set stays zero, which is its documented
    default.

    The ``sform`` is a plain diagonal voxel-to-RAS mapping, so voxel ``(i, j, k)`` sits at
    ``origin + (i, j, k) * SPACING`` in the RAS millimetres the annotation uses.
    """
    header = bytearray(348)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<c", header, 38, b"r")
    struct.pack_into("<8h", header, 40, 3, *shape, 1, 1, 1, 1)
    struct.pack_into("<h", header, 70, 4)  # datatype: DT_INT16
    struct.pack_into("<h", header, 72, 16)  # bitpix
    struct.pack_into("<8f", header, 76, 1.0, SPACING, SPACING, SPACING, 0.0, 0.0, 0.0, 0.0)
    struct.pack_into("<f", header, 108, 352.0)  # vox_offset: header + 4 extension bytes
    struct.pack_into("<f", header, 112, 1.0)  # scl_slope
    struct.pack_into("<B", header, 123, 2)  # xyzt_units: NIFTI_UNITS_MM
    struct.pack_into("<80s", header, 148, b"SphereAnnotation synthetic sample case")
    struct.pack_into("<h", header, 254, 1)  # sform_code: NIFTI_XFORM_SCANNER_ANAT
    struct.pack_into("<4f", header, 280, SPACING, 0.0, 0.0, origin[0])
    struct.pack_into("<4f", header, 296, 0.0, SPACING, 0.0, origin[1])
    struct.pack_into("<4f", header, 312, 0.0, 0.0, SPACING, origin[2])
    struct.pack_into("<4s", header, 344, b"n+1\0")
    return bytes(header)


def write_volume(path, volume, origin):
    """Write ``volume`` to ``path`` as a gzipped single-file NIfTI-1.

    ``mtime=0`` because the default stamps the current time into the gzip header, which would
    make every regeneration a new blob in git for no change in content.
    """
    payload = (
        _nifti_header(volume.shape, origin)
        + bytes(4)  # extension flags: none
        + volume.astype("<i2").tobytes(order="F")  # NIfTI stores the first axis fastest
    )
    with gzip.GzipFile(path, "wb", compresslevel=9, mtime=0) as f:
        f.write(payload)


def annotation_file():
    """Return the annotation as the structure Slicer's ``.mrk.json`` holds.

    Base then tip, one target after another, because sphere *n* is control points *2n* and
    *2n+1*. Written in RAS: the file records which convention it uses and the module works in
    RAS, so saying so here avoids a silent flip of every coordinate's sign. Slicer's own Save
    writes LPS by default — see docs/annotation-format.md.

    Only the fields a reader needs are emitted. Slicer fills in the rest on load, and a
    hand-listed copy of its defaults would be one more thing to keep current with Slicer.
    """
    positions = [point for target in TARGETS for point in (target["base"], target["tip"])]
    return {
        "@schema": (
            "https://raw.githubusercontent.com/slicer/slicer/master/Modules/Loadable/"
            "Markups/Resources/Schema/markups-schema-v1.0.3.json#"
        ),
        "markups": [
            {
                "type": "Fiducial",
                "coordinateSystem": "RAS",
                "coordinateUnits": "mm",
                "controlPoints": [
                    {"id": str(i + 1), "label": f"F-{i + 1}", "position": list(position)}
                    for i, position in enumerate(positions)
                ],
            }
        ],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grid, shape, origin = _grid()

    volume_path = OUT_DIR / VOLUME_NAME
    write_volume(volume_path, _build_volume(grid, shape), origin)

    annotation_path = OUT_DIR / ANNOTATION_NAME
    annotation_path.write_text(json.dumps(annotation_file(), indent=2) + "\n")

    print(
        f"{volume_path}: {shape[0]}x{shape[1]}x{shape[2]} at {SPACING} mm, {volume_path.stat().st_size / 1024:.0f} KiB"
    )
    print(f"{annotation_path}: {len(TARGETS)} spheres from {2 * len(TARGETS)} control points")


if __name__ == "__main__":
    main()
