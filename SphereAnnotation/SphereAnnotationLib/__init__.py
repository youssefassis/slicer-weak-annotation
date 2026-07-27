# Copyright the SphereAnnotation authors. Licensed under the Apache License, Version 2.0.
"""Slicer-free core of the SphereAnnotation module.

Nothing in this package may import ``slicer``, ``vtk``, ``qt`` or ``ctk`` — the linter
enforces that (see ``pyproject.toml``). Keeping the boundary means the sphere maths and the
display maths can be tested with plain pytest in seconds, instead of only by launching
Slicer and clicking points into a 3D view.

Slicer object handling lives on the other side of the boundary, in ``SphereAnnotation.py``.
"""

__version__ = "0.1.0"
