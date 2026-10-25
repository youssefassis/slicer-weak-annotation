# Architecture

The module is a 3D Slicer scripted loadable module. Its layout is dictated by Slicer more
than by preference: the scripted-modules directory is on `sys.path`, and a module file must
be named after the class it defines.

```
SphereAnnotation/
├── SphereAnnotation.py         Slicer + Qt glue: widget, MRML nodes, signal wiring
├── SphereAnnotationLib/        the Slicer-free core
│   ├── rendering.py            colour conversion and the volume opacity ramp
│   └── spheres.py              point pairs read as spheres
├── Resources/UI/               the Qt Designer layout
└── Testing/Python/             build-time test scaffolding
```

## The import boundary

**`SphereAnnotationLib` may not import `slicer`, `vtk`, `qt` or `ctk`.** `ruff` enforces this
via `flake8-tidy-imports` banned-api rules in `pyproject.toml`, so breaking it fails CI rather
than eroding quietly.

The reason is testability. Everything behind the boundary is a function over numbers, lists
and dicts, so `tests/` runs it in a fraction of a second with no GUI. Before the split, none
of this logic could run without launching Slicer and clicking points into a 3D view — which
is why the project had no tests at all.

Slicer objects are the glue's business. The pattern is: read plain values out of widgets and
nodes, compute in `SphereAnnotationLib`, write the result back into nodes.
`spheres.center_and_radius` is that pattern at its smallest: it was inline in the widget as
`getSphereCenterAndRadius`, where nothing could reach it.

The core here is deliberately small. Most of what this module does *is* MRML manipulation,
and inventing an abstraction to make it look otherwise would buy nothing. What is behind the
boundary is what can be got wrong in silence: the pairing rule and the opacity ramp.

## The annotation

This is what the module exists for. **Each consecutive pair of control points defines one
sphere**, with the two points at opposite ends of a diameter — so the sphere is centred on
their midpoint with a radius of half their separation, and dragging either point in any view
resizes and moves it. The full contract is in [`annotation-format.md`](annotation-format.md).

Three consequences follow, and they are what `SphereAnnotationLib/spheres.py` exists to keep
straight:

1. **Sphere *n* is always points *2n* and *2n+1*** (`point_indices`). Nothing renumbers, so
   removing a point from the middle of a node re-pairs every sphere after it. That is why the
   only removal the UI offers is of the *last* point.
2. **An odd point count defines a half-placed sphere, which is drawn as nothing**
   (`sphere_count`, `has_unpaired_point`). This is the normal state between the two clicks of
   a pair; guessing at the missing point would be worse than drawing nothing.
3. **Coincident points give a radius of zero**, not an error — what a freshly placed pair
   looks like before the second point is dragged out.

## Volume rendering

`rendering.scalar_opacity_points` builds a fixed 2-point opacity ramp: transparent below
`threshold - margin`, rising to the chosen opacity at `threshold`. The margin is a tenth of
the volume's scalar *span*, proportional rather than absolute because the scalar range of a
volume depends on how it was acquired.

**The two node scalars must be strictly ascending**, and that is the invariant the whole
function exists to hold. `vtkPiecewiseFunction.AddPoint` *replaces* a node at an x it already
holds rather than adding one, so two equal scalars leave a one-node function — opaque
everywhere, with no ramp and no threshold. Only the threshold is clamped into `[min, max]`;
the lower node is left free to fall below the minimum, which is both representable and the
honest reading of a threshold at the bottom of the range. Clamping *it* into the range was
what used to collide the two.

`rendering.default_threshold` starts a fresh volume a third of the way up its own range —
`min + (max - min) / 3`, not `(min + max) / 3`, which agrees only for a volume whose minimum
is zero and which lands below the minimum for a range that sits high.

Both sliders rebuild the whole ramp through `applyOpacityRamp`. The opacity slider used to
patch control point number 1 in place, which only worked for as long as the threshold slider
happened to leave the upper point at that index.

## State in the widget

### Scene ownership

**The module owns the nodes it created, and nothing else.** It never empties the scene and
never looks a node up by class or by name, so it can be opened alongside another module's
data.

Three references are what make that possible:

| | |
| --- | --- |
| `self.volNode` | whatever `slicer.util.loadVolume` returned |
| `self.pointsNodes` | the markups nodes this module created or loaded, in order |
| `self.modelNode` | the model node it draws the spheres into |

All three used to be searches — `getNodesByClass("vtkMRMLScalarVolumeNode")[0]`,
`getNodesByClass("vtkMRMLMarkupsFiducialNode")`, `GetNodesByName("Annotations")` — and the
widget's `__init__` called `slicer.mrmlScene.Clear(0)`, so **opening the module destroyed
everything already in the scene**, and what survived was then taken over. `load_volume` also
removed every `vtkMRMLMarkupsROINode` it found, which belonged to whatever else was open.

Keep it that way: a `getNodesByClass` in this file is a bug waiting for someone who had their
own volume loaded. `test_opening_the_module_leaves_the_rest_of_the_scene_alone` is the guard.

Each reference is reached through a `current*Node` accessor that returns `None` — or prunes
the list — once the node has left the scene, and `ensurePointsNode()` / `ensureModelNode()`
create on demand. That is what makes a node deleted from the Data module a no-op rather than
a crash.

### Several annotations at once

`self.pointsNodes` is a **list**, not a single node, because loading a second annotation file
is how two annotations of the same volume are compared. Spheres are drawn from every node in
it, in order. **Create** places into the most recent one; **Remove** takes the last point off
the most recent node that has any — it used to take one off the end of *every* fiducial node
in the scene, which quietly damaged the other annotations whenever more than one was loaded.

### The model node and the append pipeline

`self.spheres` is a `vtkSphereSource` per sphere, index-parallel with the flattened pairs
across all of `pointsNodes`. They feed a `vtkAppendPolyData`, whose output the model node
observes. That aliasing is what makes the two update paths differ:

- **`draw_spheres`** rebuilds the source list and the appender, then re-points the model at
  the new output. Called when the *set* of points changes.
- **`move_spheres`** writes new centres and radii into the existing sources and lets the
  observed output carry them through. Called when a point *moves*.

`PointModifiedEvent` also fires while points are being added and removed, so `move_spheres`
compares the sphere count first and falls back to `draw_spheres` when they disagree —
otherwise it would move the wrong sphere, or index past the end.

**Neither path renders anything itself.** Updating the appender modifies the polydata the
model node is observing, the model node re-emits that, and the displayable managers turn it
into a render request Slicer schedules at each view's own update rate. `move_spheres` used to
call `forceRenderAllViews()` instead — a synchronous render of every 2D and 3D view, on every
`PointModifiedEvent`, an event that also fires for the preview point tracking the cursor
during place mode. That put the cost of a full render of the layout on every mouse move and
bypassed the throttling that exists to prevent exactly this.

`draw_spheres` returns early when there is nothing to draw *and* no model node yet, so an
annotation with no whole pair in it does not leave an empty model in the scene. A model that
already exists is still emptied — those spheres have to stop being drawn.

The model node is created once and updated in place. Removing it by name and calling
`AddModel` again on every point event — which is what the original did — churned the subject
hierarchy and reset the display properties on every drag.

### Observers

Four events on each owned markups node reach the widget, listed once in
`pointsNodeObservations()`: `PointPositionDefinedEvent` and `PointRemovedEvent` →
`draw_spheres`, `PointModifiedEvent` and `TransformModifiedEvent` → `move_spheres`. The
transform one is there because the points are read in *world* coordinates: a transform
applied to the node moves every point at once without firing a single point event.

Two events on the scene reach it as well: `EndCloseEvent` → `onSceneEndClose`, and
`NodeRemovedEvent` → `onNodeRemoved`, which redraws when one of the owned points nodes has
left. `currentPointsNodes()` prunes the reference on its own, but nothing was asking it to,
so a node deleted from the Data module kept its spheres on screen until an unrelated point
event forced a redraw. `onNodeRemoved` returns immediately during batch processing — a scene
close or an import removes nodes wholesale, and `onSceneEndClose` picks that state up
afterwards.

`adoptPointsNode` attaches them through `VTKObservationMixin.addObserver`, behind a
`hasObserver` guard. Both halves matter. The original called `node.AddObserver` directly, so
the mixin never knew about them and `removeObservers()` could not release them; and it did so
for every fiducial node in the scene on **every** Create and Load click, so the observers
accumulated without bound and one drag ran the handler once per accumulated copy.

### Teardown

Three paths, with different obligations:

| | |
| --- | --- |
| `reset()` (the **Clean** button) | forgets the volume, points and model this module owns, then removes them |
| `onSceneEndClose` | the nodes are already gone; only `releasePointsNodes()` + `forgetSceneState()` |
| `cleanup()` (reload / Slicer exit) | observers first, then the **model node only** |

`forgetSceneState()` is the half of `reset()` that touches nothing in the scene. The split
matters because the callers have opposite obligations: **Clean** must remove the nodes itself,
while after a scene close there is nothing left to remove and reaching for those nodes is what
would go wrong.

**`reset()` forgets before it removes**, and the order is load-bearing now that
`NodeRemovedEvent` is observed: removing the first points node fires the handler, which would
redraw and rebuild the model node the previous iteration had just removed. With the
references already dropped there is nothing left for it to redraw.

Removing the volume also means removing the nodes that were created *for* it —
`removeVolumeRenderingNodes` takes the volume rendering display node, the volume property
node and the ROI, none of which `RemoveNode` on the volume takes with it.

`cleanup()` drops the observers first, so a handler cannot run against a widget being
destroyed. It removes the model node because a reload builds a new widget that would otherwise
add a second one and orphan this. **It deliberately leaves the points.** They are the
annotator's work and, unlike the model, cannot be rebuilt from anything — losing them to a
`Ctrl+R` would be unforgivable. The cost is that after a reload the module no longer knows
about them; **Create** starts a new node, and the old one is loaded back or saved as it stands.

## Slicer and Qt conventions

- Widgets come from the `.ui` file through `slicer.util.childWidgetVariables()`, so
  `self.ui.<objectName>` mirrors the Qt Designer object names exactly. Renaming a widget in
  Designer breaks the Python side silently — grep for the old name.
- This is PythonQt, not PyQt: `.checked`, `.value`, `.minimum`/`.maximum` are assignable
  properties, not methods. Assigning `.value` emits `valueChanged`, which is how
  `load_volume` gets the opacity ramp applied without calling for it.
- Both signal styles appear (`x.clicked.connect(f)` and `x.connect('clicked(bool)', f)`);
  both work. Match whichever is adjacent.
- Handlers connected to a signal take the signal's argument with a default, so they can also
  be called directly with none.
- Positions are RAS world coordinates; use `GetNthControlPointPositionWorld` with a
  pre-allocated `np.empty(3)` out-parameter. The original used
  `GetNthControlPointPosition`, which is the node's own frame and differs from world as soon
  as a transform is applied to the markups node.
- Filesystem paths are `pathlib.Path`. Qt hands over plain strings, so convert at the
  boundary and convert back with `str()` only where Qt needs it again —
  `slicer.util.loadVolume` passes the name straight to Qt, which cannot convert a `Path`.
