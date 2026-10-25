# Documentation

**Sphere Annotation** is a 3D Slicer scripted module (shown as **Sphere Annotation**, under
*Annotation*). It annotates any ball-shaped object — aneurysms, nodules, lesions, cells —
with spheres: you place **two points per sphere**, at opposite ends of a diameter, and the
sphere follows either point as you drag it.

## Where to start

| if you want to… | read |
| --- | --- |
| annotate a volume | [user-guide.md](user-guide.md) |
| try the module without a volume of your own | [../data/README.md](../data/README.md) |
| read or generate annotation files | [annotation-format.md](annotation-format.md) |
| change the code | [architecture.md](architecture.md), then the rest of this page |
| set up a dev environment, run the tests | [development.md](development.md) |
| see what changed | [../CHANGELOG.md](../CHANGELOG.md) |

The four pages are the source of truth for their areas. Read the relevant one before working
in that area rather than relying on the summary here.

---

The rest of this page is for people changing the code.

## Commands

```bash
python -m pip install -r requirements-dev.txt
python -m pytest        # Slicer-free suite; 65 tests, well under a second
python -m pytest -k center_and_radius
ruff check .            # lint + the Slicer-free import boundary
```

Running the module itself needs Slicer, which is not installed on every dev machine:

```bash
/Applications/Slicer.app/Contents/MacOS/Slicer --additional-module-paths SphereAnnotation
```

Anything touching widgets, MRML nodes or views is therefore **unverifiable without Slicer** —
say so plainly rather than implying it was tested. `SphereAnnotationTest` in
`SphereAnnotation.py` is the in-Slicer test; `ctest -R SphereAnnotation` runs it in a build
tree.

## The rule that shapes everything

`SphereAnnotation/SphereAnnotationLib/` **may not import `slicer`, `vtk`, `qt` or `ctk`** —
ruff enforces it via banned-api rules in `pyproject.toml`. New logic goes behind that boundary
unless it genuinely needs an MRML node, because that is the only part of the project that can
be tested. The pattern is: read plain values out of widgets/nodes, compute in
`SphereAnnotationLib`, write results back into nodes.

Do not add a runtime dependency to `pyproject.toml`. Slicer supplies numpy/VTK/Qt to the
extension; `requirements-dev.txt` is only for running tests and the linter outside Slicer.

## Constraints that look like bugs but are not

Each of these is load-bearing, and each replaced something that was wrong. Undoing one
reintroduces a specific defect, so change them deliberately rather than in passing.

- **The module never empties the scene and never looks a node up by class or by name.**
  `self.volNode` is what `loadVolume` returned, `self.pointsNodes` are the markups nodes it
  created or loaded, `self.modelNode` is the model it made — each reached through a
  `current*Node` accessor that prunes once the node has left the scene. All three were scene
  searches, and `__init__` called `mrmlScene.Clear(0)`, which is why opening the module used
  to wipe everything. Do not reintroduce either.
- **`self.pointsNodes` is a list on purpose.** Loading a second annotation file adds to it
  rather than replacing, because comparing two annotations of the same volume is a documented
  feature.
- **Sphere *n* is control points *2n* and *2n+1*, across the flattened pairs of every owned
  node**, and `self.spheres[n]` is its `vtkSphereSource`. Nothing renumbers. An odd point
  count draws nothing rather than guessing the missing point.
- **`move_spheres` checks the sphere count before writing.** `PointModifiedEvent` also fires
  while points are added and removed, so without the check it would move the wrong sphere or
  index past the end. It falls back to `draw_spheres`.
- **Attach markups observers through `adoptPointsNode`, never `node.AddObserver`.** The
  `hasObserver` guard and the mixin are both load-bearing: this runs on every Create and every
  Load, and the original accumulated three observers per click that `removeObservers()` could
  not release.
- **`cleanup()` removes the model node but keeps the points.** The model is derived and a
  reload would otherwise orphan it; the points are the annotator's work and cannot be rebuilt.
  The cost — the new widget not knowing about them — is the accepted trade.
- **`forgetSceneState()` touches nothing in the scene.** It is the half of `reset()` that is
  safe after a scene close, when the nodes are already gone. `reset()` (the Clean button) must
  remove them itself; `onSceneEndClose` must not try.

## Working here

- Keep `pytest` and `ruff check .` green; both are CI-gated on both remotes. Lint exemptions
  need a comment giving the reason, as the existing ones do.
- Add new `SphereAnnotationLib` modules to `MODULE_PYTHON_SCRIPTS` in
  `SphereAnnotation/CMakeLists.txt`, or they work in development and vanish from the packaged
  extension.
- Behaviour change → [`../CHANGELOG.md`](../CHANGELOG.md). Point-pairing change →
  [annotation-format.md](annotation-format.md) too, and treat it as breaking for every
  annotation ever saved, since nothing in a file declares the convention.
- A test that stays green when you break the real logic is decorative — check it fails.
  [development.md](development.md) lists four mutations that must go red.
- Undecided items are listed under "Open decisions" in [development.md](development.md). Those
  are the lab's calls, not something to fill in while working on the code.
