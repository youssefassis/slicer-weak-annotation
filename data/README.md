# Sample data

A case to try the module on, so that placing a first sphere does not depend on having a real
angiogram to hand.

```
sample_case/
  angio.nii.gz        the volume     (136 x 120 x 100 at 0.5 mm, ~100 KiB)
  aneurysms.mrk.json  a finished annotation of it (3 spheres, 6 control points)
```

**It is synthetic.** No patient data is involved: the volume is a phantom drawn by
[`tools/make_sample_data.py`](../tools/make_sample_data.py) — bright vessels on a dark
background, the way a subtracted or MR angiogram looks — shaped into a crude circle of Willis.
It is enough to exercise the workflow and to see the spheres behave. It is **not** a substitute
for real anatomy when judging how the module reads clinically, and the sacs are literally
spheres, so nothing about their shape is realistic.

The volume is the same phantom the sibling ReformatViz extension ships, drawn from the same
constants, so one case serves both. Only the NIfTI `descrip` string differs.

## Open it

1. Launch Slicer with the module (see the [README](../README.md)) and go to
   *Aneurysms → Sphere Annotation*.
2. Under *Volume*, click **Load** and pick `data/sample_case/angio.nii.gz`. The vessel tree
   appears in the 3D view.
3. Either annotate it yourself — **Create**, click one edge of a sac, **Create**, click the
   opposite edge — or click **Load** under *Annotations* and pick
   `data/sample_case/aneurysms.mrk.json` to get all three spheres at once.

Turn the *Volume* **Opacity** down if you want to see a sphere against the sac it covers; at
full opacity the sac hides it, because the sphere is exactly the same size.

## What is in it

Three aneurysms, and one thing that is not an aneurysm.

| Sphere | Diameter | What it is |
| --- | --- | --- |
| 0 | 5.5 mm | Right MCA bifurcation — the unmistakable one |
| 1 | 5.0 mm | Anterior communicating artery, pointing anterosuperiorly |
| 2 | 2.8 mm | Left ICA terminus — small enough to be a genuine judgement call |
| — | 3.0 mm | An isolated blob, connected to no artery. Deliberately **not** annotated |

Each drawn sac **is** the sphere the module derives from its pair of control points, so the
overlay lands on the sac rather than near it. That join is checked by
[`tests/test_sample_data.py`](../tests/test_sample_data.py), so the annotation cannot drift
away from the image it describes.

The annotation is written in RAS, and says so. Slicer's own **Save** writes LPS by default —
see [`docs/annotation-format.md`](../docs/annotation-format.md), which is also where the
two-points-per-sphere contract is written down.

## Regenerate it

Both files come out of the constants at the top of `tools/make_sample_data.py`:

```bash
python tools/make_sample_data.py
```

The output is deterministic — regenerating without changing the constants leaves `git status`
clean.
