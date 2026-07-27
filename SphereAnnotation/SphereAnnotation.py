# Copyright the SphereAnnotation authors. Licensed under the MIT License.
"""Slicer and Qt glue for the Sphere Annotation module.

Everything here needs an MRML node, a Qt widget or a VTK pipeline. The maths does not, so it
lives in :mod:`SphereAnnotationLib`, which the linter keeps free of ``slicer``/``vtk``/``qt``
so it can be tested without launching Slicer. The pattern is: read plain values out of the
widgets and nodes, compute in ``SphereAnnotationLib``, write the result back into nodes.

See ``docs/architecture.md`` for how the pieces fit and which of the constraints below are
load-bearing.
"""

import logging
from pathlib import Path

import numpy as np
import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from SphereAnnotationLib import rendering, spheres

#: Name of the model node holding the drawn spheres. A display name only — the module finds
#: the node through ``self.modelNode``, never by searching the scene for this string.
ANNOTATIONS_MODEL_NAME = "Annotations"

#: Name given to a markups node this module creates. Same caveat: a label, not a lookup key.
POINTS_NODE_NAME = "Sphere annotation points"

#: Facets per sphere, both directions. Enough that a sphere reads as a sphere at the zoom an
#: aneurysm is annotated at, without making the append pipeline the bottleneck while dragging.
SPHERE_RESOLUTION = 30

#: Width of the sphere outlines drawn on the 2D slice views, in screen pixels.
SLICE_INTERSECTION_THICKNESS = 3

#: Slicer's file filter for the markups formats this module can read back. ``.mrk.json`` is
#: what Slicer 5 saves markups as by default and therefore what **Save** most often produces;
#: ``.fcsv`` is the legacy format earlier annotations were stored in. The filter used to name
#: only ``*.Fcsv``, which matches neither on a case-sensitive filesystem.
MARKUPS_FILE_FILTER = "Markups (*.mrk.json *.fcsv)"

#: Slicer's file filter for the volumes this module loads.
VOLUME_FILE_FILTER = "NIfTI (*.nii.gz *.nii)"


class SphereAnnotation(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Sphere Annotation"
        self.parent.categories = ["Aneurysms"]
        self.parent.dependencies = []
        self.parent.contributors = ["Youssef Assis (Loria lab.)"]
        self.parent.helpText = (
            "Annotate aneurysms — or any ball-shaped object — with spheres. Each consecutive "
            "pair of markup points defines one sphere, placed at their midpoint with a radius "
            "of half their separation, so a sphere is resized by dragging either point in any "
            "view. See docs/user-guide.md."
        )
        self.parent.acknowledgementText = "This module was developed by Youssef Assis."


class SphereAnnotationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """The module panel, and the owner of every node the module puts in the scene.

    **The module owns the nodes it created, and nothing else.** It never empties the scene
    and never looks a node up by class or by name: ``self.volNode`` is what
    ``slicer.util.loadVolume`` returned, ``self.pointsNodes`` are the markups nodes it created
    or loaded, and ``self.modelNode`` is the model it made from them. All three used to be
    ``getNodesByClass``/``GetNodesByName`` searches, and the widget cleared the whole scene on
    open, so opening the module destroyed whatever the annotator already had loaded.

    Keep it that way: a ``getNodesByClass`` in this file is a bug waiting for someone who had
    their own volume open. ``test_opening_the_module_leaves_the_rest_of_the_scene_alone`` is
    the guard.
    """

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation

        # Deliberately empty of side effects. This used to clear the Python console and call
        # `slicer.mrmlScene.Clear(0)`, so merely opening the module threw away the console
        # history and every node in the scene.
        self.volNode = None
        self.pointsNodes = []
        self.modelNode = None
        self.spheres = []
        self.appender = None

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer). `self.ui.<name>` mirrors the Qt
        # Designer object names exactly, so renaming a widget there breaks this side silently.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/SphereAnnotation.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        #### Volume
        self.ui.load_volume_button.connect('clicked(bool)', self.load_volume)
        self.ui.vol_visibility.stateChanged.connect(self.set_volume_visibility)
        self.ui.volumeOpacity.valueChanged.connect(self.onVolumeOpacityChanged)
        self.ui.volumeThreshold.valueChanged.connect(self.onVolumeThresholdChanged)

        #### Annotations
        self.ui.load_annotations_button.connect('clicked(bool)', self.load_annotations_from_file)
        self.ui.annotationsVisibility.stateChanged.connect(self.set_annotations_visibility)
        self.ui.annotationsOpacity.valueChanged.connect(self.set_annotations_opacity)
        self.ui.ColorPickerButton.colorChanged.connect(self.set_annotations_color)

        self.ui.addButton.connect('clicked(bool)', self.create_point)
        self.ui.deleteButton.connect('clicked(bool)', self.remove_point)

        self.ui.saveButton.connect('clicked(bool)', self.saveButton)
        self.ui.cleanButton.connect('clicked(bool)', self.clearButton)

        # A scene closed from the File menu while the module is open would otherwise leave
        # every reference below pointing at a removed node.
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    ############################################ Node ownership ############################################

    def currentVolumeNode(self):
        """The volume this module loaded, or ``None`` once it has left the scene."""
        if self.volNode is not None and not slicer.mrmlScene.IsNodePresent(self.volNode):
            self.volNode = None
        return self.volNode

    def currentPointsNodes(self):
        """The markups nodes this module owns that are still in the scene.

        Prunes as it goes, so a node deleted from the Data module stops being drawn instead
        of being reached for after the scene has let go of it.
        """
        self.pointsNodes = [node for node in self.pointsNodes if slicer.mrmlScene.IsNodePresent(node)]
        return self.pointsNodes

    def currentModelNode(self):
        """The model node holding the drawn spheres, or ``None`` if there is not one yet."""
        if self.modelNode is not None and not slicer.mrmlScene.IsNodePresent(self.modelNode):
            self.modelNode = None
        return self.modelNode

    def ensurePointsNode(self):
        """The node new points go into: the most recent one this module owns, or a new one."""
        nodes = self.currentPointsNodes()
        if nodes:
            return nodes[-1]
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", POINTS_NODE_NAME)
        self.adoptPointsNode(node)
        return node

    def ensureModelNode(self):
        """The model node the spheres are drawn into, created on first use.

        Created once and updated in place afterwards. Rebuilding it per point event — which
        is what removing it by name and calling ``AddModel`` again amounted to — churned the
        subject hierarchy and reset the display properties on every drag.
        """
        node = self.currentModelNode()
        if node is not None:
            return node
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", ANNOTATIONS_MODEL_NAME)
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        display.SetVisibility2D(True)
        display.SetSliceIntersectionThickness(SLICE_INTERSECTION_THICKNESS)
        self.modelNode = node
        # The annotator just produced their first sphere; leaving the box unticked would show
        # them nothing and read as the module having failed.
        self.ui.annotationsVisibility.checked = True
        return node

    def pointsNodeObservations(self):
        """The events on a markups node that have to reach this widget, with their handlers."""
        return (
            (slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.draw_spheres),
            (slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.draw_spheres),
            (slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.move_spheres),
        )

    def adoptPointsNode(self, node):
        """Take ownership of ``node`` and observe it.

        The ``hasObserver`` guard is the point: this runs on every **Create** and every
        **Load**, and the previous version attached three fresh observers to every fiducial
        node in the scene each time, through ``node.AddObserver`` rather than the mixin — so
        they accumulated without bound and ``removeObservers()`` never released them.
        """
        if node not in self.pointsNodes:
            self.pointsNodes.append(node)
        for event, handler in self.pointsNodeObservations():
            if not self.hasObserver(node, event, handler):
                self.addObserver(node, event, handler)

    def releasePointsNodes(self):
        """Stop observing the markups nodes, leaving them in the scene."""
        for node in self.pointsNodes:
            for event, handler in self.pointsNodeObservations():
                if self.hasObserver(node, event, handler):
                    self.removeObserver(node, event, handler)

    def forgetSceneState(self):
        """Drop every reference to a scene node without touching the scene.

        The half of :meth:`reset` that is safe once the scene has already been closed — at
        which point the nodes are gone and reaching for them is exactly what would go wrong.
        """
        self.volNode = None
        self.pointsNodes = []
        self.modelNode = None
        self.spheres = []
        self.appender = None

    def reset(self):
        """Remove what this module put in the scene, and nothing else."""
        self.releasePointsNodes()
        for node in [self.currentModelNode(), self.currentVolumeNode(), *self.currentPointsNodes()]:
            if node is not None:
                slicer.mrmlScene.RemoveNode(node)
        self.forgetSceneState()

    def onSceneEndClose(self, caller=None, event=None):
        """The scene was closed from the File menu: the nodes are already gone."""
        self.releasePointsNodes()
        self.forgetSceneState()

    def cleanup(self):
        """Called when the widget is destroyed — a module reload, or Slicer closing.

        Observers go first, so a handler cannot run against a widget that is being torn down.
        The model node goes with them: a reload builds a new widget which would otherwise add
        a second one and orphan this. The points stay. They are the annotator's work, and
        unlike the model they cannot be rebuilt from anything.
        """
        self.releasePointsNodes()
        self.removeObservers()
        model = self.currentModelNode()
        if model is not None:
            slicer.mrmlScene.RemoveNode(model)
        self.forgetSceneState()

    ############################################ Annotations ############################################

    def create_point(self):
        """Place the next point, into a node this module owns.

        Pointing place mode at that node first is what makes the ownership hold. The previous
        version called ``StartPlaceMode`` and then observed whatever fiducial nodes happened
        to already be in the scene — which meant the annotator's own nodes were taken over,
        and the very first point, placed into a node Slicer created on the click, was observed
        by nothing at all.
        """
        node = self.ensurePointsNode()
        markupsLogic = slicer.modules.markups.logic()
        markupsLogic.SetActiveListID(node)
        markupsLogic.StartPlaceMode(0)

    def remove_point(self):
        """Remove the last point placed.

        One point, from the most recent node that has any — the previous version took one off
        the end of *every* fiducial node in the scene, which quietly damaged the other
        annotations whenever more than one was loaded for comparison.
        """
        for node in reversed(self.currentPointsNodes()):
            count = node.GetNumberOfControlPoints()
            if count:
                node.RemoveNthControlPoint(count - 1)
                return

    def load_annotations_from_file(self):
        """Load a markups file and adopt it as one of this module's annotations.

        Loading a second file does not replace the first: both are drawn, which is what makes
        two annotations of the same volume comparable side by side.
        """
        dialog = qt.QFileDialog()
        dialog.setNameFilters([MARKUPS_FILE_FILTER])
        if dialog.exec_() != qt.QDialog.Accepted:
            return

        path = Path(dialog.selectedFiles()[0])
        try:
            node = slicer.util.loadMarkups(str(path))
        except (RuntimeError, OSError) as error:
            # Not swallowed: the annotator is told which file failed and why, and the console
            # keeps the traceback. Anything that is not a load failure is left to propagate.
            logging.exception("Could not load markups from %s", path)
            slicer.util.errorDisplay(f"Could not load the annotation file.\n\n{path.name}\n\n{error}")
            return

        self.adoptPointsNode(node)
        self.draw_spheres()

    def draw_spheres(self, caller=None, event=None):
        """Rebuild every sphere from the points, and put the result in the model node.

        Called when the set of points changes. :meth:`move_spheres` is the cheaper path for a
        point that merely moved.
        """
        self.spheres = []
        self.appender = vtk.vtkAppendPolyData()

        for node in self.currentPointsNodes():
            for index in range(spheres.sphere_count(node.GetNumberOfControlPoints())):
                source = vtk.vtkSphereSource()
                source.SetPhiResolution(SPHERE_RESOLUTION)
                source.SetThetaResolution(SPHERE_RESOLUTION)
                self.applySphere(source, node, index)
                self.spheres.append(source)
                self.appender.AddInputConnection(source.GetOutputPort())

        model = self.ensureModelNode()
        if self.spheres:
            self.appender.Update()
            # The model observes the appender's output, so `move_spheres` can update the
            # sphere sources in place and have the model follow without touching it again.
            model.SetAndObservePolyData(self.appender.GetOutput())
        else:
            # vtkAppendPolyData with no inputs has no output to observe.
            model.SetAndObservePolyData(vtk.vtkPolyData())

        self.set_annotations_color()
        self.set_annotations_opacity()
        self.set_annotations_visibility()

    def move_spheres(self, caller=None, event=None):
        """Follow a point that was dragged, without rebuilding the pipeline.

        ``PointModifiedEvent`` also fires while points are being added and removed, so the
        sphere count is checked first: writing into ``self.spheres`` when it no longer lines
        up with the points would move the wrong sphere, or index past the end.
        """
        nodes = self.currentPointsNodes()
        counts = [spheres.sphere_count(node.GetNumberOfControlPoints()) for node in nodes]
        if sum(counts) != len(self.spheres):
            self.draw_spheres()
            return

        source = iter(self.spheres)
        for node, count in zip(nodes, counts, strict=True):
            for index in range(count):
                self.applySphere(next(source), node, index)

        if self.appender is not None:
            self.appender.Update()
        # Once per event, not once per sphere: the previous version re-rendered every view
        # inside the loop, so a drag with ten spheres on screen paid for ten full renders.
        slicer.util.forceRenderAllViews()

    def applySphere(self, source, node, index):
        """Point ``source`` at the sphere that control points ``2*index`` and ``2*index+1`` define."""
        first, second = spheres.point_indices(index)
        a, b = np.empty(3), np.empty(3)
        node.GetNthControlPointPositionWorld(first, a)
        node.GetNthControlPointPositionWorld(second, b)
        center, radius = spheres.center_and_radius(a, b)
        source.SetCenter(*center)
        source.SetRadius(radius)
        source.Update()

    def set_annotations_visibility(self, state=None):
        model = self.currentModelNode()
        if model is not None:
            model.GetDisplayNode().SetVisibility(self.ui.annotationsVisibility.checked)

    def set_annotations_color(self, color=None):
        model = self.currentModelNode()
        if model is not None:
            model.GetDisplayNode().SetColor(*rendering.to_rgb(self.ui.ColorPickerButton.color))

    def set_annotations_opacity(self, value=None):
        model = self.currentModelNode()
        if model is not None:
            # The slider value, not half of it. It used to be halved on the way through, so
            # the annotator could never get past 50% opacity however far right they dragged.
            model.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value)

    ############################################ Volume ############################################

    def load_volume(self):
        """Load a volume and set up its 3D rendering.

        The volume this module loaded previously is removed to make room; anything else in
        the scene is left alone. The previous version removed *every* scalar volume and every
        ROI node — including the crop ROI belonging to whatever else the annotator had open.
        """
        dialog = qt.QFileDialog()
        dialog.setNameFilters([VOLUME_FILE_FILTER])
        if dialog.exec_() != qt.QDialog.Accepted:
            return

        path = Path(dialog.selectedFiles()[0])
        previous = self.currentVolumeNode()
        try:
            # loadVolume hands the name straight to Qt, which cannot convert a Path.
            volNode = slicer.util.loadVolume(str(path))
        except (RuntimeError, OSError) as error:
            logging.exception("Could not load volume from %s", path)
            slicer.util.errorDisplay(f"Could not load the volume.\n\n{path.name}\n\n{error}")
            return

        if previous is not None:
            slicer.mrmlScene.RemoveNode(previous)
        self.volNode = volNode

        volRenLogic = slicer.modules.volumerendering.logic()
        displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volNode)
        if not displayNode:
            displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volNode)
        volRenLogic.UpdateDisplayNodeFromVolumeNode(displayNode, volNode)

        min_value, max_value = volNode.GetImageData().GetScalarRange()
        self.ui.volumeThreshold.minimum = min_value
        self.ui.volumeThreshold.maximum = max_value
        # Assigning `.value` emits valueChanged, which applies the ramp for us.
        self.ui.volumeThreshold.value = rendering.default_threshold(min_value, max_value)
        self.ui.vol_visibility.checked = True

    def volumeRenderingDisplayNode(self):
        """The rendering display node for the volume this module loaded, or ``None``.

        Every volume control goes through this, which is what makes each of them a no-op
        rather than a crash when no volume is open.
        """
        volNode = self.currentVolumeNode()
        if volNode is None:
            return None
        return slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode)

    def set_volume_visibility(self, state=None):
        displayNode = self.volumeRenderingDisplayNode()
        if displayNode is not None:
            displayNode.SetVisibility(self.ui.vol_visibility.checked)

    def onVolumeThresholdChanged(self, value=None):
        self.applyOpacityRamp()

    def onVolumeOpacityChanged(self, value=None):
        self.applyOpacityRamp()

    def applyOpacityRamp(self):
        """Rewrite the scalar opacity ramp from the two sliders.

        Both sliders rebuild the whole ramp. The opacity slider used to patch control point
        number 1 in place, which only worked for as long as the threshold slider happened to
        leave the upper point at that index.
        """
        displayNode = self.volumeRenderingDisplayNode()
        if displayNode is None:
            return
        scalarOpacity = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
        min_value, max_value = self.volNode.GetImageData().GetScalarRange()
        points = rendering.scalar_opacity_points(min_value, max_value,
                                                 self.ui.volumeThreshold.value,
                                                 self.ui.volumeOpacity.value)
        scalarOpacity.RemoveAllPoints()
        for x, y, midpoint, sharpness in points:
            scalarOpacity.AddPoint(x, y, midpoint, sharpness)

    ############################################ Buttons ############################################

    def saveButton(self):
        """Open Slicer's Save Data dialog, from which the markups nodes are written out."""
        slicer.util.openSaveDataDialog()

    def clearButton(self):
        """The Clean button: remove this module's volume, points and spheres from the scene.

        It used to call ``slicer.mrmlScene.Clear(0)``, which emptied the scene of everything
        including nodes the module had never touched.
        """
        self.reset()


class SphereAnnotationTest(ScriptedLoadableModuleTest):
    """The cases that genuinely need MRML nodes and a widget.

    Everything that is a function over numbers is covered by ``tests/`` instead, which runs
    without Slicer in a fraction of a second. Keep this file thin — a case belongs here only
    if it needs a scene.
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_opening_the_module_leaves_the_rest_of_the_scene_alone()
        self.setUp()
        self.test_two_points_become_one_sphere()
        self.setUp()
        self.test_an_unpaired_point_draws_nothing()
        self.setUp()
        self.test_dragging_a_point_moves_its_sphere()
        self.setUp()
        self.test_clean_removes_only_this_modules_nodes()
        self.setUp()
        self.test_closing_the_scene_leaves_no_stale_references()

    def widget(self):
        slicer.util.selectModule("SphereAnnotation")
        return slicer.modules.SphereAnnotationWidget

    def placePoints(self, node, *positions):
        for position in positions:
            node.AddControlPoint(vtk.vtkVector3d(*position))

    def test_opening_the_module_leaves_the_rest_of_the_scene_alone(self):
        """The regression that matters most: the module used to clear the scene on open."""
        self.delayDisplay("Opening the module leaves the rest of the scene alone")

        foreignVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "Someone else's volume")
        foreignPoints = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Someone else's points")
        self.placePoints(foreignPoints, (0, 0, 0), (5, 0, 0))

        widget = self.widget()

        self.assertTrue(slicer.mrmlScene.IsNodePresent(foreignVolume))
        self.assertTrue(slicer.mrmlScene.IsNodePresent(foreignPoints))
        # And it did not adopt them either — the spheres are drawn from its own nodes only.
        self.assertNotIn(foreignPoints, widget.currentPointsNodes())

    def test_two_points_become_one_sphere(self):
        self.delayDisplay("Two points become one sphere")
        widget = self.widget()

        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0), (10, 0, 0))
        widget.draw_spheres()

        self.assertEqual(len(widget.spheres), 1)
        self.assertAlmostEqual(widget.spheres[0].GetRadius(), 5.0)
        self.assertEqual(list(widget.spheres[0].GetCenter()), [5.0, 0.0, 0.0])

        model = widget.currentModelNode()
        self.assertIsNotNone(model)
        self.assertGreater(model.GetPolyData().GetNumberOfPoints(), 0)

    def test_an_unpaired_point_draws_nothing(self):
        """A half-placed pair defines no sphere, and must not be guessed at."""
        self.delayDisplay("An unpaired point draws nothing")
        widget = self.widget()

        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0))
        widget.draw_spheres()

        self.assertEqual(len(widget.spheres), 0)
        self.assertEqual(widget.currentModelNode().GetPolyData().GetNumberOfPoints(), 0)

    def test_dragging_a_point_moves_its_sphere(self):
        """The observers are wired, and the cheap path keeps the sphere on the points."""
        self.delayDisplay("Dragging a point moves its sphere")
        widget = self.widget()

        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0), (10, 0, 0))
        widget.draw_spheres()

        node.SetNthControlPointPositionWorld(1, 20.0, 0.0, 0.0)

        self.assertEqual(len(widget.spheres), 1)
        self.assertAlmostEqual(widget.spheres[0].GetRadius(), 10.0)
        self.assertEqual(list(widget.spheres[0].GetCenter()), [10.0, 0.0, 0.0])

    def test_clean_removes_only_this_modules_nodes(self):
        self.delayDisplay("Clean removes only this module's nodes")
        widget = self.widget()

        foreignVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "Someone else's volume")
        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0), (10, 0, 0))
        widget.draw_spheres()
        model = widget.currentModelNode()

        widget.clearButton()

        self.assertTrue(slicer.mrmlScene.IsNodePresent(foreignVolume))
        self.assertFalse(slicer.mrmlScene.IsNodePresent(node))
        self.assertFalse(slicer.mrmlScene.IsNodePresent(model))
        self.assertEqual(widget.currentPointsNodes(), [])

    def test_closing_the_scene_leaves_no_stale_references(self):
        self.delayDisplay("Closing the scene leaves no stale references")
        widget = self.widget()

        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0), (10, 0, 0))
        widget.draw_spheres()

        slicer.mrmlScene.Clear()

        self.assertIsNone(widget.volNode)
        self.assertIsNone(widget.modelNode)
        self.assertEqual(widget.pointsNodes, [])
        self.assertEqual(widget.spheres, [])
