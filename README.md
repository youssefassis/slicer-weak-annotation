# Sphere Annotation

> Part of the original Inria GitLab project at
> [gitlab.inria.fr/yassis/slicer-sphere-annotation](https://gitlab.inria.fr/yassis/slicer-sphere-annotation),
> developed at the [Loria](https://www.loria.fr/) lab.

A [3D Slicer](https://www.slicer.org/) extension for annotating any ball-shaped object in a 3D
volume with spheres — aneurysms, nodules, lesions, cells, or whatever your labelling project
is about. Nothing in it is specific to one anatomy or one kind of image.

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
*Annotation*.

## Your first annotation

**No volume to hand?** A synthetic angiogram with three aneurysms ships with the module — see
[`data/`](data/README.md). Everything below is shown on it; on your own data, read
"aneurysm" as whatever you are labelling.

1. **Volume → Load.** Pick a `.nii` or `.nii.gz` angiogram. It appears in the 3D view.
2. Drag **Threshold** until the vessels stand out. This is the one control worth playing
   with — it is what hides the background so you can see what you are aiming at.

   <img width=70% src="docs/images/step-1-volume.png" alt="A vessel tree in the 3D view after loading a volume and setting the threshold">

3. **Annotations → Create**, then click one edge of the aneurysm. *Nothing is drawn yet.*

   <img width=70% src="docs/images/step-2-one-point.png" alt="A single control point placed on the edge of an aneurysm, with no sphere drawn">

4. **Create** again, then click the opposite edge. *The sphere appears.*

   <img width=70% src="docs/images/step-3-sphere.png" alt="The sphere appearing between the two control points, covering the aneurysm">

5. Nudge either point — in the 3D view or in any 2D slice view — until the sphere covers the
   aneurysm. It resizes as you drag.
6. **Save** when you are done, and pick a location. Your annotation is the markups node.

Repeat steps 3–5 for each aneurysm. Every pair of points is a new sphere:

<img width=70% src="docs/images/step-4-all-spheres.png" alt="Three aneurysms annotated with three spheres in one volume">

> Nothing is drawn after step 3, and that is correct: one point does not define a sphere. If a
> sphere you expected is missing, an odd number of points is the first thing to check.

> The volume above is deliberately half-transparent. Each sphere is exactly the size of the
> sac it covers, so at full opacity the sac hides it — turn **Volume → Opacity** down to see
> one against the other.

The [user guide](docs/user-guide.md) covers every control, and the parts that surprise people.

## What you can do with it

- Annotate any number of objects in one volume, each with two clicks.
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
python -m pytest     # 58 tests, well under a second
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
