# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project has not been
released yet; once it is, versions follow [Semantic Versioning](https://semver.org/).

Note that the **annotation convention is not versioned** — nothing in a saved file declares
it — so a change to the point-pairing rule is a breaking change for every annotation ever
made. See `docs/annotation-format.md`.

## [Unreleased]

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
- **The opacity ramp stays inside the volume's scalar range.** A threshold at either end of
  its travel could put a control point outside it, leaving the `vtkPiecewiseFunction` node
  scalars non-ascending.
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

### Added

- `SphereAnnotationLib`, a Slicer-free package holding the sphere maths and the display maths,
  so that logic can be tested without launching Slicer. `ruff` bans `slicer`/`vtk`/`qt`/`ctk`
  imports inside it, so the boundary fails CI rather than eroding quietly.
- `tests/`, a pytest suite covering `SphereAnnotationLib` (39 cases, well under a second, no
  Slicer needed).
- `SphereAnnotationTest`, an in-Slicer test covering what genuinely needs a scene — including
  the guarantee that opening the module and cleaning up leave other nodes alone.
- CI on both remotes (`.github/workflows/checks.yml`, `.gitlab-ci.yml`), each running `ruff`
  and `pytest`.
- `docs/`, indexed by [`docs/README.md`](docs/README.md):
  [architecture](docs/architecture.md), [annotation format](docs/annotation-format.md),
  [user guide](docs/user-guide.md) and [development](docs/development.md), the last of which
  lists the open decisions blocking a first release.
- This changelog, `pyproject.toml`, `requirements-dev.txt` and a `.gitignore`.
