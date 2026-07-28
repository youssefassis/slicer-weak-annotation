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

> **The pinned Slicer version is 5.12.** That is what the README advertises as supported and
> what development runs against — 5.12.3 specifically. Earlier 5.x releases are untested
> rather than excluded; Slicer 4 is excluded, because the module calls
> `slicer.util.loadMarkups` and `SetVisibility2D`, which are Slicer 5 API. When the
> commented `slicer-tests` jobs in the CI files are enabled, pin their image to 5.12 so the
> pipeline and the README cannot drift apart.

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
| drop the `lower >= upper` guard in `rendering.scalar_opacity_points` | `test_a_constant_volume_still_gives_two_distinct_scalars` |
| that, *and* clamp the lower node into `[min, upper]` | four cases in `TestScalarOpacityPoints` |
| take `rendering.ramp_margin` from the maximum instead of the span | `TestRampMargin`, `test_a_negative_range_still_ascends` |
| put `rendering.default_threshold` back to `(min + max) / 3` | `test_it_stays_inside_the_range` |
| halve the opacity on the way through the ramp | `test_opacity_is_passed_through_untouched` |

Note the second row needs *both* halves. Reintroducing the clamp on its own leaves the suite
green, because the guard below it catches the collision the clamp causes — the two are
belt and braces on the same invariant, and only removing both exposes it. Worth knowing
before concluding that the clamp is harmless.

The middle three rows are the ones that used to pass. `sorted()` accepts a tie, and `low <= x`
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

## Settled

Recorded here because the reasoning is not visible in the result, and because each of these
was an open question long enough to be worth closing explicitly.

- **The name is `SphereAnnotation`**, at both levels: the extension and its one module share
  it, so the Extensions Manager, Slicer's module list and this tree all say the same word.
  The aneurysm framing lives in `EXTENSION_CATEGORY`, not in the name — the module measures
  any ball-shaped object. Renaming the module would have meant renaming its file, its class,
  its directory and its `.ui` file together, since Slicer requires those to match; renaming
  the CMake project meant one line.
- **Supported Slicer is 5.12 or later**, the tested floor rather than a promise about the
  whole 5.x line. See the note at the top of this page.
- **The copyright holder is Youssef Assis**, stated in every source header and in the README.
  `LICENSE` stays byte-identical to canonical Apache-2.0: its appendix is instructions for
  writing a header, not a form, and editing it makes the file stop matching what licence
  scanners look for.

## Open decisions

These block a first tagged release and are the lab's calls, not something to fill in while
working on the code.

- **A real icon for the extension.** `docs/extension-icon.png` is still the extension
  wizard's placeholder, not a picture of the module. `docs/module-panel.jpg` is a real
  screenshot and could be the basis for one. `EXTENSION_ICONURL` already points at the
  placeholder's path, so replacing the file is enough — no URL changes.
- **Making the GitHub repository public.** All three URLs in `EXTENSION_HOMEPAGE`,
  `EXTENSION_ICONURL` and `EXTENSION_SCREENSHOTURLS` resolve only once it is. Until then the
  Extensions Manager entry would show a dead link and two blank images — and nothing fails at
  build time to tell you so.
- **Renaming the two repositories** to match the name above, if the hosted names should agree
  with it: GitHub is `slicer-weak-annotation` and GitLab is `slicer-sphere-annotation`. This
  is a host-side action, not a code change, but the three URLs in `CMakeLists.txt` and the
  clone URL in the README hard-code the GitHub one and have to be re-pointed with it. GitHub
  redirects renamed repositories, so nothing breaks the moment it happens; the redirect is
  not something to rely on permanently.
