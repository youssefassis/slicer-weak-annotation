# User guide

The module appears in Slicer as **Sphere Annotation**, under the *Aneurysms* category.

It annotates aneurysms — or any ball-shaped object — with spheres. You place **two points per
sphere**, at opposite ends of a diameter; the sphere appears between them and follows either
point as you drag it. That is the whole interaction, and the whole file format
([annotation format](annotation-format.md)).

## Before anything else

**Opening this module does not touch what you already have loaded**, and neither does
**Clean**. Earlier versions cleared the entire scene on open — if you are used to that, you no
longer need to work around it.

## Volume

| control | what it does |
| --- | --- |
| **Load** | Opens a file dialog for a NIfTI volume (`.nii`, `.nii.gz`) and sets up its 3D rendering. Replaces the volume *this module* loaded last time; leaves everything else alone. |
| **Visibility** | Shows or hides the 3D rendering. Not the slice views — those are Slicer's own. |
| **Threshold** | Everything below it is transparent, so this is what turns the volume into a vessel tree. Starts a third of the way up the volume's intensity range; the slider's ends are that range. |
| **Opacity** | How solid the vessels above the threshold appear. |

Both sliders are no-ops until a volume is loaded through **Load**.

## Annotations

| control | what it does |
| --- | --- |
| **Load** | Opens a markups file (`.mrk.json` or `.fcsv`) and draws its points as spheres. Loading a second file **adds** it rather than replacing the first — that is how you compare two annotations of the same volume. |
| **Create** | Enters place mode for one point. Click in any view to place it. |
| **Remove** | Deletes the last point placed. |
| **Visibility** | Shows or hides the spheres. Ticks itself when the first sphere appears. |
| **Opacity** | How solid the spheres are, from transparent to fully opaque. |
| colour swatch | The colour of every sphere. There is one colour for all of them. |

### Placing a sphere

1. **Create**, then click one edge of the aneurysm.
2. **Create** again, then click the opposite edge.

The sphere appears as soon as the second point lands. Nothing is drawn after the first click —
one point does not define a sphere, and the module will not guess the second.

To adjust it, drag either point in the 3D view or in any of the 2D slice views; the sphere
resizes and re-centres as you drag. Getting a sphere right usually means nudging both points
across two or three slice views, which is why they are ordinary Slicer markups rather than
anything custom.

Repeat for each aneurysm. Every pair of points is a new sphere.

### Removing

**Remove** takes off the **last point placed**, so clicking it twice removes the last sphere.
It cannot remove a sphere from the middle of the list.

If you need to, you can delete any point from Slicer's **Markups** module — but be aware that
the spheres are defined by *consecutive pairs*, so deleting an interior point re-pairs every
sphere after it and the rest of the annotation will visibly change. Deleting two adjacent
points that form a pair is safe.

## Save and Clean

| button | what it does |
| --- | --- |
| **Save** | Opens Slicer's Save Data dialog. Your annotation is the markups node — save that. Slicer 5 writes `.mrk.json` by default; `.fcsv` is offered for the legacy format. |
| **Clean** | Removes the volume, the points and the spheres **this module** put in the scene. Anything else stays. |

**Clean discards unsaved points without asking.** Save first.

## Things worth knowing

- **An odd number of points means one sphere is half-placed** and nothing is drawn for it.
  If a sphere you expected is missing, that is the first thing to check.
- **Reloading the module** (*Developer Tools → Reload*) removes the drawn spheres but keeps
  your points. The module loses track of them, so **Create** afterwards starts a new list —
  save before reloading if you want one file.
- **Closing the scene** from the File menu takes everything with it, as it does for any module.
- The spheres are also drawn as outlines on the 2D slice views, which is usually the easier
  place to judge whether one actually covers the aneurysm.
