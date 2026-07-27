# Development

## The two environments

This is the thing to internalise before anything else.

|  | Slicer's Python | Your dev Python |
| --- | --- | --- |
| Runs | the module, in the GUI | `pytest`, `ruff` |
| Provides | numpy, VTK, Qt, CTK, `slicer` | whatever `requirements-dev.txt` pins |
| Managed by | the Slicer installer | you |
| Targeted at | Slicer 5.12.3 | 3.11, numpy 2.4.6 |

Slicer's interpreter is typically **newer** than a dev machine's, not older. Check what your
install actually ships from Slicer's own Python console (*View → Python Console*):

```python
import sys, numpy, vtk
print(sys.version, numpy.__version__, vtk.vtkVersion.GetVTKVersion())
```

`requirements-dev.txt` pins numpy to the version recorded for Slicer 5.12.3, so the tests
exercise the array behaviour the module will actually meet. **Re-check it against your own
install with the snippet above** before trusting the pin — and update the pin, not the code,
if the supported Slicer version moves.

You do **not** pip-install into Slicer. Extensions are loaded from disk, and Slicer supplies
their dependencies. That is why `pyproject.toml` declares no runtime dependencies and no
build backend — a pin there would describe nothing real. `requirements-dev.txt` is only for
running the tests and linter outside Slicer.

It also means **reproducibility comes from pinning the Slicer version**, not from pinning
Python packages.

> **Pin the Slicer version.** Development currently runs against **Slicer 5.12.3**. What is
> still a decision rather than a fact: whether that is the version the lab commits to
> supporting, and therefore what to pin in the commented `slicer-tests` jobs in the CI files.
> The README still advertises "4.11 or later", which is almost certainly no longer true — the
> module calls `slicer.util.loadMarkups` and `SetVisibility2D`, which are Slicer 5 API.

## The fast loop

Most work needs no Slicer at all:

```bash
python -m pip install -r requirements-dev.txt

python -m pytest                      # whole Slicer-free suite, well under a second
python -m pytest tests/test_spheres.py -q
python -m pytest -k "center_and_radius"
python -m pytest -k "ascend"          # the vtkPiecewiseFunction invariant
python -m pytest -x -vv               # stop at the first failure, verbose

ruff check .                          # lint + the import boundary
ruff check --fix .
```

`pytest` finds `SphereAnnotationLib` through `pythonpath = ["SphereAnnotation"]` in
`pyproject.toml`, which is the same layout Slicer sees — no install step.

### Are the tests actually testing anything?

A quick way to check a test has teeth: break the code on purpose and confirm the suite goes
red. These all do, and are worth re-running after touching either core module:

| break | what should fail |
| --- | --- |
| drop the `/ 2` from the radius in `spheres.center_and_radius` | `TestCenterAndRadius` |
| round `spheres.sphere_count` up instead of down | `test_a_trailing_point_is_not_counted` |
| clamp the lower node into the range in `rendering.scalar_opacity_points` | `test_the_scalars_ascend_strictly` |
| take `rendering.ramp_margin` from the maximum instead of the span | `TestRampMargin`, `test_a_negative_range_still_ascends` |
| put `rendering.default_threshold` back to `(min + max) / 3` | `test_it_stays_inside_the_range` |
| halve the opacity on the way through the ramp | `test_opacity_is_passed_through_untouched` |

The middle three are the ones that used to pass. `sorted()` accepts a tie, and `low <= x`
accepts a threshold pinned to the bottom of the range — so the assertions held while the
behaviour they were written for did not. Prefer the strict comparison when the boundary *is*
the bug.

Add `import slicer` to a `SphereAnnotationLib` module and `ruff check .` should fail on
TID251. If a change to real logic leaves both green, the test is decorative.

## The Slicer loop

For anything touching widgets, MRML nodes or the views:

```bash
# macOS; adjust for your install
/Applications/Slicer.app/Contents/MacOS/Slicer --additional-module-paths SphereAnnotation
```

Then iterate without restarting: open the module, use the **Reload** button in *Developer
Tools*, or `Ctrl+R` / `Cmd+R`. Reloading destroys the widget, so `cleanup()` removes the
spheres model this module put in the scene. **The points stay** — they are your annotation —
but the new widget does not know about them, so **Create** after a reload starts a fresh
node.

The Python console (*View → Python Console*) is the fastest way to poke at live state:

```python
w = slicer.modules.SphereAnnotationWidget
len(w.spheres), len(w.currentPointsNodes())
w.volNode, w.modelNode
```

### The in-Slicer test

`SphereAnnotationTest` in `SphereAnnotation.py` covers what genuinely needs MRML. Run it from
the module's **Reload and Test** button, or from the command line the same way `ctest` does —
`slicer.testing.runUnitTest`, which runs each `test_*` method with a cleared scene:

```bash
MOD="$PWD/SphereAnnotation"
/Applications/Slicer.app/Contents/MacOS/Slicer --no-splash --testing \
  --additional-module-paths "$MOD" --python-code \
  "import slicer.testing; slicer.testing.runUnitTest(['$MOD'], 'SphereAnnotation.SphereAnnotationTest'); slicer.util.exit(0)"
```

The process exits non-zero if a test fails, so this is usable as a gate. Note `--testing`:
without it `errorDisplay`/`warningDisplay` open modal dialogs and the run blocks forever.

The cases cover the scene-ownership guarantee (opening the module leaves other nodes alone,
**Clean** removes only this module's), two points becoming one sphere, an unpaired point
drawing nothing, a dragged point moving its sphere, and the widget forgetting its nodes when
the scene is closed.

Keep it thin — new cases belong in `tests/` unless they need a scene.

## Building the packaged extension

Only needed to distribute the extension; not for development.

```bash
cmake -S . -B ../build -DSlicer_DIR=/path/to/Slicer-build/Slicer-build
cmake --build ../build
ctest --test-dir ../build -R SphereAnnotation     # runs SphereAnnotationTest inside Slicer
```

`SphereAnnotationLib`'s files are listed individually in `SphereAnnotation/CMakeLists.txt`
under `MODULE_PYTHON_SCRIPTS` so they are installed next to the module. **Add new library
modules to that list** — a file that is not listed will work from `--additional-module-paths`
during development and then be missing from the packaged extension, which is a nasty way to
find out.

## CI

Both remotes run the same two checks, so a push cannot be green on one and red on the other:

| | |
| --- | --- |
| [`.github/workflows/checks.yml`](../.github/workflows/checks.yml) | GitHub Actions |
| [`.gitlab-ci.yml`](../.gitlab-ci.yml) | GitLab |

Each runs `ruff check .` and `python -m pytest` on Python 3.11, and nothing else. The
in-Slicer test is wired up on neither: booting Slicer takes minutes and a container image, and
gating every commit on that is how CI ends up switched off. Both files carry a commented
`slicer-tests` job recording what enabling it would take. **Change one file, change the
other** — the point of them is that they agree.

## Conventions

- One logical change per commit; `[TAG] imperative summary` with TAG one of `[FEAT] [FIX]
  [REFACTOR] [CHORE] [DOCS] [TEST] [PERF]`. Explain *why* in the body.
- Branch per task from `main`, prefixed `feat/ fix/ refactor/ chore/ docs/ test/`.
- `ruff check .` and `pytest` must pass before committing. Do not add lint exemptions
  without a comment giving the reason — the existing ones in `pyproject.toml` all have one.
- Behaviour change → update `CHANGELOG.md`. A change to the point-pairing rule → also
  `docs/annotation-format.md`, and treat it as breaking for every annotation ever saved.
- `SphereAnnotationLib` is snake_case (plain Python); the widget keeps Qt's camelCase for
  slots and for the node-ownership accessors. Follow whichever side of the boundary you are on.
- Filesystem paths are `pathlib.Path`, not `os.path` strings. Convert at the Qt boundary.

## Open decisions

These block a first tagged release and are the lab's calls, not something to fill in while
working on the code.

- **The extension metadata** in the top-level `CMakeLists.txt`, which still carries the
  wizard's `John Doe (AnyWare Corp.)` contributor, `example.com` URLs and "This is an example
  of a simple extension" as its description.
- **The extension name**, which is currently four different things: the GitHub repository is
  `slicer-weak-annotation`, the GitLab one `slicer-sphere-annotation`, the top-level CMake
  project `AneurysmAnnotation`, and the module `SphereAnnotation`. The README and the docs use
  the module's name because that is what a user sees in Slicer. Pick one and rename the rest —
  note that renaming the module means renaming its file, its class, its directory and its
  `.ui` file together, since Slicer requires them to match.
- **The supported Slicer version.** Developed against 5.12.3. The README now says "Slicer 5"
  rather than the old, untrue "4.11 or later", but that is a description of what is tested,
  not a commitment. Confirm what the lab reviews with, then pin it in CI and say so.
- **The copyright holder.** `LICENSE`'s appendix is unfilled and the source headers say "the
  SphereAnnotation authors"; the MIT licence this replaced named "Assis Youssef". Loria is a
  joint unit, so the holder may need to be Inria, CNRS and/or Université de Lorraine — confirm
  with the lab, then set it consistently across the headers.
- **A real icon for the extension.** `docs/extension-icon.png` is still the extension
  wizard's placeholder, not a picture of the module. `docs/module-panel.jpg` is a real
  screenshot and could be the basis for one.
