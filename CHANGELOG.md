# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow
[Semantic Versioning](https://semver.org/).

Note that the **annotation convention is not versioned** — nothing in a saved file declares
it — so a change to the point-pairing rule is a breaking change for every annotation ever
made. See `docs/annotation-format.md`.

## [Unreleased]

### Added

- **A volume selector beside Volume → Load** picks a volume that is already in the scene —
  one loaded through Slicer's DICOM module, for instance. A picked volume is borrowed: Clean
  and replacing it leave it in the scene, and its rendering nodes are only removed if the
  module created them.
- **Export CSV** writes one row per sphere — label, number, centre (RAS mm) and radius — for
  pipelines that do not read Slicer markups. The label is the points node's name. A trailing
  unpaired point is left out, with a warning naming the annotation.

### Changed

- **Dragging a point and placing points are much faster with many spheres, using half the
  memory.** All spheres are now one mesh copied from a single template, and a drag rewrites
  only the moved sphere instead of re-tessellating and re-appending every one. Measured in
  Slicer 5.12.4 at 200 spheres: a drag event 193 → ~50 ms (what remains is Slicer redrawing
  the 2D outlines), placing 200 spheres 61 → 17 s, and 28.6 → 14.1 MB of mesh. The drawn
  geometry is unchanged.
- **Volume → Load accepts every common single-file format Slicer reads** — NRRD, NIfTI,
  MetaImage, Analyze, TIFF — plus *All files* for anything else, instead of NIfTI only.
- **The sample case files are now `volume.nii.gz` and `annotation.mrk.json`** (were
  `angio.nii.gz` and `aneurysms.mrk.json`). The voxels and points are unchanged.
- **The module is now listed under *Annotation* instead of *Aneurysms*,** and its description
  and documentation present it as a tool for any ball-shaped object. The behaviour is
  unchanged.

## [0.1.0] - 2026-09-20

### Fixed

- **Opening the module no longer empties the scene.** The widget's `__init__` called
  `slicer.mrmlScene.Clear(0)`, so loading a volume in any other module and then opening this
  one destroyed it. The module now owns only the nodes it created and never searches the scene
  by class or by name.
- **Opening the module no longer clears the Python console.**
- **Clean removes only this module's nodes** — its volume, its points and its spheres —
  instead of clearing the whole scene.
- **Loading a volume no longer deletes other modules' data.** It used to remove every scalar
  volume *and every ROI node* in the scene, including the crop ROI belonging to whatever else
  was open. It now replaces only the volume this module loaded previously.
- **Markups observers are attached once, through `VTKObservationMixin`.** Every **Create** and
  every **Load** used to attach three more observers to every fiducial node in the scene, via
  `node.AddObserver` — so they accumulated without bound, ran the handler once per accumulated
  copy on a single drag, and were never released, because the mixin's `removeObservers()` did
  not know about them.
- **The first point of a new annotation is observed.** `StartPlaceMode` was called before any
  markups node existed, and the observers were then attached to whatever was already in the
  scene — so the node Slicer created on that first click was watched by nothing, and its
  spheres never appeared until something else forced a redraw.
- **The module no longer takes over the annotator's own markups nodes.** Place mode is pointed
  at a node this module owns.
- **The annotation opacity slider reaches full opacity.** The value was halved between the
  slider and the display node, so the right-hand end of its travel meant 50%.
- **Remove takes one point off the end**, not one off the end of every fiducial node in the
  scene — which quietly damaged the other annotations whenever more than one was loaded for
  comparison.
- **The Load filter matches the files Slicer writes.** It named only `*.Fcsv`, which matches
  neither Slicer 5's default `.mrk.json` nor a lowercase `.fcsv` on a case-sensitive
  filesystem — so an annotation often could not be loaded back after being saved.
- **The volume opacity slider no longer depends on a control-point index.** It patched point
  number 1 of the opacity transfer function in place, which only held for as long as the
  threshold slider happened to leave the upper point at that index. Both sliders now rebuild
  the ramp.
- **The opacity ramp's two nodes are always at distinct scalars.** They could land on the same
  one — a threshold at the bottom of its travel, or any volume whose maximum is below zero —
  and `vtkPiecewiseFunction.AddPoint` *replaces* a node at an x it already holds rather than
  adding one, so the ramp collapsed to a single node and the volume rendered opaque
  everywhere, with no threshold. Clamping the lower node into the volume's scalar range was
  what put the two together; only the threshold is clamped now, and a node below the minimum
  is both representable and what a threshold at the bottom of the range means.
- **The ramp margin is a tenth of the scalar *span*, not of the maximum.** It was 20% of the
  span for a volume ranging over (1000, 2000), and *negative* for any volume whose maximum is
  below zero — which pointed the ramp the wrong way before the clamp hid it.
- **A fresh volume opens a third of the way up its own range.** `(min + max) / 3` is that only
  for a volume whose minimum is zero; for a range that sits high it falls below the minimum, so
  a (2000, 3000) volume opened at 1666, was clamped to the bottom of its own slider, and
  rendered fully opaque until the annotator found the threshold by hand.
- **A second volume gets the opacity ramp the sliders are describing.** Setting the threshold
  slider only takes effect when the value *changes*, and a second volume with the same scalar
  range as the first does not change it — the same protocol, the next patient. Its display
  node kept the five-node preset Slicer gave it while the panel went on claiming the threshold
  and opacity the *first* volume was shown at, so the two controls described a volume that was
  not the one on screen.
- **A volume's rendering nodes are removed along with the volume.** `RemoveNode` on the volume
  leaves its volume rendering display node, its volume property node and its ROI behind, so
  every volume after the first added another set to the scene and to the Save dialog.
- **A points node deleted from the Data module stops being drawn.** Its spheres stayed on
  screen until an unrelated point event happened to force a redraw.
- **The spheres follow a transform applied to their markups node.** Positions are read in world
  coordinates, so a transform moves every point at once without firing a point event.
- **The appearance controls survive a missing display node.** All three checked the model node
  and then reached straight through it, so deleting the display node from the Data module made
  every subsequent slider move raise.
- **A control point position is read into zeroed memory.** `GetNthControlPointPositionWorld`
  logs and returns without writing when it does not like the index, and the `np.empty` buffer
  then handed whatever was in that memory to `vtkSphereSource` as a centre.
- **An annotation with no whole pair in it no longer creates an empty model node** and ticks a
  visibility box over it.
- **Loading a file that is already open asks first.** It used to produce a second markups node
  and a second identical set of spheres drawn through the first, with nothing to tell them
  apart. Asked rather than refused — re-reading a file edited on disk is a real thing to want.
- **Sphere positions are read in world coordinates.** `GetNthControlPointPosition` returns the
  markups node's own frame, which differs from world as soon as a transform is applied to it.
- **A failed file load says what went wrong.** The bare `except:` around the markups loader
  swallowed everything, including programming errors, and reported one fixed message.

### Changed

- **The spheres are drawn into one model node, updated in place.** It was removed by name and
  recreated on every point event, which churned the subject hierarchy and reset its display
  properties on every drag.
- **Reloading the module keeps your points.** `cleanup()` removes the derived spheres model —
  otherwise a reload orphans it and adds a second — but leaves the markups nodes, which are
  the annotator's work and cannot be rebuilt from anything.
- Closing the scene from the File menu now leaves the widget with no stale node references.
- **Dragging a point no longer forces a render.** `move_spheres` called
  `forceRenderAllViews()` on every `PointModifiedEvent` — a synchronous render of every 2D and
  3D view, for an event that also fires for the preview point tracking the cursor in place
  mode. The model node already observes the appender's output, so updating it raises a render
  request that Slicer schedules at each view's own update rate. Confirmed in Slicer 5.12.3:
  dragging a point still raises `PolyDataModifiedEvent`, moves the model's polydata with the
  point, and renders the 3D view, with nothing forcing it.
- **The file dialogs are the platform's own**, parented to the main window so they cannot end
  up stranded behind it, and they reopen where the last one left off rather than in whatever
  directory Slicer was started from.

### Changed (project, not behaviour)

- **Relicensed from MIT to Apache 2.0**, matching the sibling review extension. `LICENSE.md`
  becomes `LICENSE` with the full Apache text, and the source headers follow.
- **The screenshots moved into `docs/`**, so `docs/` holds the documentation and its
  assets together and the repository root stays down to the files that have to be there.
- **The README was rewritten around getting a first sphere placed**, and the user guide gained
  the annotated panel screenshot and a symptom-to-cause table.
- **The extension is named `SphereAnnotation`, like its module.** The CMake project was
  `AneurysmAnnotation` while everything a user sees said `SphereAnnotation`; the subject stays
  in `EXTENSION_CATEGORY`, which is where it belongs for a module that measures any
  ball-shaped object.
- **The extension wizard's placeholder metadata is gone.** `John Doe (AnyWare Corp.)`, "This
  is an example of a simple extension" and two `example.com` image URLs are replaced by the
  real contributor, a description of what the module does, and the icon and screenshot in
  `docs/`. Those URLs resolve once the GitHub repository is public.
- **The copyright holder is named.** Headers said "the SphereAnnotation authors"; they now say
  Youssef Assis, as the README does. `LICENSE` is left as canonical Apache-2.0 text.
- **The supported Slicer version is 5.12 or later**, the version actually tested, rather than
  the whole 5.x line.

### Added

- **A sample case, in `data/sample_case/`.** A synthetic angiogram (~100 KiB) shaped into a
  crude circle of Willis with three aneurysms, plus a finished annotation of it. Trying the
  module no longer requires having a real angiogram to hand, and the documentation figures are
  taken on it, so they contain no patient data. Both files are regenerated by
  `tools/make_sample_data.py` from one set of constants: the sac that is rasterised is the sac
  the annotation points at, and `tests/test_sample_data.py` holds the two together. The volume
  is the same phantom the sibling ReformatViz extension ships, so one case serves both.
- **Step-by-step screenshots in the README and the user guide**, showing the vessel tree, a
  half-placed pair drawing nothing, the sphere appearing on the second point, and three
  aneurysms annotated — plus a low/high threshold pair in the user guide.
- `SphereAnnotationLib`, a Slicer-free package holding the sphere maths and the display maths,
  so that logic can be tested without launching Slicer. `ruff` bans `slicer`/`vtk`/`qt`/`ctk`
  imports inside it, so the boundary fails CI rather than eroding quietly.
- `tests/`, a pytest suite covering `SphereAnnotationLib` (46 cases, well under a second, no
  Slicer needed).
- `SphereAnnotationTest`, an in-Slicer test covering what genuinely needs a scene — including
  the guarantee that opening the module and cleaning up leave other nodes alone, that a second
  volume is shown like the first, and that deleting a points node takes its spheres with it.
- CI on both remotes (`.github/workflows/checks.yml`, `.gitlab-ci.yml`), each running `ruff`
  and `pytest`.
- `docs/`, indexed by [`docs/README.md`](docs/README.md):
  [architecture](docs/architecture.md), [annotation format](docs/annotation-format.md),
  [user guide](docs/user-guide.md) and [development](docs/development.md), the last of which
  lists the open decisions blocking a first release.
- This changelog, `pyproject.toml`, `requirements-dev.txt` and a `.gitignore`.
