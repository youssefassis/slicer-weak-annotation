# Sphere Annotation

> Part of the original Inria GitLab project at
> [gitlab.inria.fr/yassis/slicer-sphere-annotation](https://gitlab.inria.fr/yassis/slicer-sphere-annotation),
> developed at the [Loria](https://www.loria.fr/) lab.

A [3D Slicer](https://www.slicer.org/) extension for annotating intracranial aneurysms — or
any ball-shaped object — with spheres.

**You place two points; you get a sphere.** The two points sit at opposite ends of a
diameter, so the sphere appears between them and follows either one as you drag it. That is
the whole interaction, and the whole file format. It gives you a weak label — a location and
a size — in a couple of clicks, without segmenting anything.

<img width=100% src="docs/sample.gif" alt="Placing and adjusting a sphere in the 3D view">

## Requirements

**3D Slicer 5.12 or later.** Developed and tested against
[5.12.3](https://download.slicer.org/). Earlier 5.x releases are untested and may work;
Slicer 4 will not — the module uses Slicer 5's markups API.

Nothing else to install: Slicer supplies numpy, VTK and Qt, and the module drives only
modules that ship with Slicer.

## Install

```bash
git clone https://github.com/youssefassis/slicer-weak-annotation.git
```

Then either point Slicer at it for one session:

```bash
# macOS; adjust for your install
/Applications/Slicer.app/Contents/MacOS/Slicer --additional-module-paths slicer-weak-annotation/SphereAnnotation
```

…or add it permanently: *Edit → Application Settings → Modules*, drag the inner
`SphereAnnotation/` directory (the one containing `SphereAnnotation.py`) into **Additional
module paths**, and restart Slicer.

Either way the module then appears in the module list as **Sphere Annotation**, under
*Aneurysms*.

## Your first annotation

1. **Volume → Load.** Pick a `.nii` or `.nii.gz` angiogram. It appears in the 3D view.
2. Drag **Threshold** until the vessels stand out. This is the one control worth playing
   with — it is what turns the volume into a vessel tree you can aim at.
3. **Annotations → Create**, then click one edge of the aneurysm.
4. **Create** again, then click the opposite edge. *The sphere appears.*
5. Nudge either point — in the 3D view or in any 2D slice view — until the sphere covers the
   aneurysm. It resizes as you drag.
6. **Save** when you are done, and pick a location. Your annotation is the markups node.

Repeat steps 3–5 for each aneurysm. Every pair of points is a new sphere.

> Nothing is drawn after step 3, and that is correct: one point does not define a sphere. If a
> sphere you expected is missing, an odd number of points is the first thing to check.

The [user guide](docs/user-guide.md) covers every control, and the parts that surprise people.

## What you can do with it

- Annotate any number of aneurysms in one volume, each with two clicks.
- Adjust position and size by dragging points in the 3D view or on the 2D slices.
- Set the colour and opacity of the spheres, and hide them without deleting them.
- **Load two annotations at once** and compare them side by side — a second **Load** adds to
  the scene rather than replacing what is there.
- Save to Slicer's standard markups formats (`.mrk.json`, or legacy `.fcsv`), which any
  Slicer install and [any script](docs/annotation-format.md#reading-an-annotation-elsewhere)
  can read back.

Opening this module leaves whatever you already had loaded alone, and so does **Clean**.

## Documentation

Everything lives in [`docs/`](docs/README.md). Start there, or jump straight to:

| | |
| --- | --- |
| [user guide](docs/user-guide.md) | every control, in the annotator's terms |
| [annotation format](docs/annotation-format.md) | the point-pairing contract — read this if you consume the files |
| [architecture](docs/architecture.md) | how the code is split, node ownership, the sphere maths |
| [development](docs/development.md) | the two Python environments, the test loop, open decisions |

## Develop

The sphere maths and the display maths live in `SphereAnnotation/SphereAnnotationLib/`, which
is kept free of `slicer`/`vtk`/`qt`/`ctk` so it can be tested without launching Slicer:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest     # 39 tests, well under a second
ruff check .         # lint, and the import boundary above
```

Both checks run on every push, on GitHub and GitLab alike. Anything touching widgets or MRML
nodes needs Slicer — see [development](docs/development.md).

## Citation

If you find this repository useful for your work, please consider citing our paper:

```
Assis et al. Aneurysm Pose Estimation with Deep Learning. In: International Conference on
Medical Image Computing and Computer-Assisted Intervention (MICCAI), Springer, 2023.
```

## License

Copyright 2023-2026 Youssef Assis. Licensed under [Apache 2.0](LICENSE).
