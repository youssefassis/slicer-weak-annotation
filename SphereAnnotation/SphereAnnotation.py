# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
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
from SphereAnnotationLib import export, rendering, spheres

#: Name of the model node holding the drawn spheres. A display name only — the module finds
#: the node through ``self.modelNode``, never by searching the scene for this string.
ANNOTATIONS_MODEL_NAME = "Annotations"

#: Name given to a markups node this module creates. Same caveat: a label, not a lookup key.
POINTS_NODE_NAME = "Sphere annotation points"

#: Facets per sphere, both directions. Enough that a sphere reads as a sphere at the zoom an
#: object is annotated at, without making the append pipeline the bottleneck while dragging.
SPHERE_RESOLUTION = 30

#: Width of the sphere outlines drawn on the 2D slice views, in screen pixels.
SLICE_INTERSECTION_THICKNESS = 3

#: Slicer's file filter for the markups formats this module can read back. ``.mrk.json`` is
#: what Slicer 5 saves markups as by default and therefore what **Save** most often produces;
#: ``.fcsv`` is the legacy format earlier annotations were stored in. The filter used to name
#: only ``*.Fcsv``, which matches neither on a case-sensitive filesystem.
MARKUPS_FILE_FILTER = "Markups (*.mrk.json *.fcsv)"

#: File filter for the sphere table **Export CSV** writes.
CSV_FILE_FILTER = "CSV (*.csv)"

#: Slicer's file filter for the volumes this module loads: the single-file formats Slicer's
#: volume reader handles. DICOM is not here on purpose — a series is loaded through Slicer's
#: DICOM module and then picked from the volume selector. "All files" is the escape hatch for
#: anything else ``loadVolume`` can read.
VOLUME_FILE_FILTER = (
    "Volumes (*.nrrd *.nhdr *.nii *.nii.gz *.mha *.mhd *.hdr *.img *.tif *.tiff);;All files (*)"
)


class SphereAnnotation(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Sphere Annotation"
        self.parent.categories = ["Annotation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Youssef Assis (Loria lab.)"]
        self.parent.helpText = (
            "Annotate any ball-shaped object — aneurysms, nodules, lesions, cells — with "
            "spheres. Each consecutive pair of markup points defines one sphere, placed at their "
            "midpoint with a radius of half their separation, so a sphere is resized by dragging "
            "either point in any view. See docs/user-guide.md."
        )
        self.parent.acknowledgementText = "This module was developed by Youssef Assis."


class SphereAnnotationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """The module panel, and the owner of every node the module puts in the scene.

    **The module owns the nodes it created, and nothing else.** It never empties the scene
    and never looks a node up by class or by name: ``self.volNode`` is what
    ``slicer.util.loadVolume`` returned or the volume the annotator picked in the selector,
    ``self.pointsNodes`` are the markups nodes it created
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
        # A volume picked in the selector is borrowed, not owned: it was in the scene before
        # the module saw it, so Clean and a replacement leave it there. The same goes for its
        # volume rendering nodes when they already existed.
        self.ownsVolume = False
        self.ownsRenderingNodes = False
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
        self.ui.volumeSelector.setMRMLScene(slicer.mrmlScene)
        self.ui.volumeSelector.currentNodeChanged.connect(self.onVolumeSelected)
        self.ui.load_volume_button.connect('clicked(bool)', self.load_volume)
        self.ui.vol_visibility.stateChanged.connect(self.set_volume_visibility)
        self.ui.volumeOpacity.valueChanged.connect(self.applyOpacityRamp)
        self.ui.volumeThreshold.valueChanged.connect(self.applyOpacityRamp)

        #### Annotations
        self.ui.load_annotations_button.connect('clicked(bool)', self.load_annotations_from_file)
        self.ui.annotationsVisibility.stateChanged.connect(self.set_annotations_visibility)
        self.ui.annotationsOpacity.valueChanged.connect(self.set_annotations_opacity)
        self.ui.ColorPickerButton.colorChanged.connect(self.set_annotations_color)

        self.ui.addButton.connect('clicked(bool)', self.create_point)
        self.ui.deleteButton.connect('clicked(bool)', self.remove_point)

        self.ui.saveButton.connect('clicked(bool)', self.saveButton)
        self.ui.exportButton.connect('clicked(bool)', self.export_spheres)
        self.ui.cleanButton.connect('clicked(bool)', self.clearButton)

        # A scene closed from the File menu while the module is open would otherwise leave
        # every reference below pointing at a removed node.
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        # And a single node deleted from the Data module has to stop being drawn.
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeRemovedEvent, self.onNodeRemoved)

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

    def annotationsDisplayNode(self):
        """The display node of the spheres model, or ``None``.

        A model node can outlive its display node — deleting one from the Data module is a
        click — and all three appearance controls would otherwise raise on ``None`` every
        time the annotator moved a slider.
        """
        model = self.currentModelNode()
        if model is None:
            return None
        return model.GetDisplayNode()

    def pointsNodeObservations(self):
        """The events on a markups node that have to reach this widget, with their handlers."""
        return (
            (slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.draw_spheres),
            (slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.draw_spheres),
            (slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.move_spheres),
            # The points are read in world coordinates, so a transform applied to the node
            # moves every one of them without a single point event being fired.
            (slicer.vtkMRMLTransformableNode.TransformModifiedEvent, self.move_spheres),
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
        self.ownsVolume = False
        self.ownsRenderingNodes = False
        self.pointsNodes = []
        self.modelNode = None
        self.spheres = []
        self.appender = None

    def reset(self):
        """Remove what this module put in the scene, and nothing else."""
        self.releasePointsNodes()
        self.releaseVolumeNode()
        self.ui.volumeSelector.setCurrentNode(None)
        nodes = [self.currentModelNode(), *self.currentPointsNodes()]
        # Forget first, then remove. Removing a node fires NodeRemovedEvent, and the handler
        # for it redraws when one of the points nodes has gone — which, halfway through this
        # loop, would put back the model node the first iteration just removed. With the
        # references already dropped there is nothing left for it to redraw.
        self.forgetSceneState()
        for node in nodes:
            if node is not None:
                slicer.mrmlScene.RemoveNode(node)

    def onSceneEndClose(self, caller=None, event=None):
        """The scene was closed from the File menu: the nodes are already gone."""
        self.releasePointsNodes()
        self.forgetSceneState()

    def onNodeRemoved(self, caller=None, event=None):
        """A node left the scene. If it was one of ours, stop drawing its spheres.

        :meth:`currentPointsNodes` drops the reference on its own, but nothing was asking it
        to: a node deleted from the Data module left its spheres on screen until the next
        point event on some other node happened to trigger a redraw.
        """
        if slicer.mrmlScene.IsBatchProcessing():
            # A close or an import removes nodes wholesale. `onSceneEndClose` picks the state
            # up afterwards; rebuilding the model here would put a node back into a scene
            # that is in the middle of being emptied.
            return
        owned = len(self.pointsNodes)
        if len(self.currentPointsNodes()) != owned:
            self.draw_spheres()

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

    ############################################ Files ############################################

    def promptForFile(self, caption, fileFilter):
        """Ask the annotator to pick an existing file. ``None`` if they cancelled.

        Through ``getOpenFileName`` rather than a bare ``QFileDialog``: that gives the
        platform's own dialog, parents it to the main window so it cannot end up stranded
        behind it, and lets Qt reopen it where the last one left off instead of in whatever
        directory Slicer's process happens to have been started from.
        """
        path = qt.QFileDialog.getOpenFileName(slicer.util.mainWindow(), caption, "", fileFilter)
        return Path(path) if path else None

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

    def isAlreadyLoaded(self, path):
        """Whether one of the annotations this module owns was read from ``path``.

        Asked rather than enforced. Re-reading a file that has been edited on disk is a real
        thing to want, and refusing it outright would be worse than the duplicate — but the
        usual reason to pick the same file twice is not noticing it is open, and the result
        is two identical sets of spheres drawn through each other with nothing to tell them
        apart.
        """
        for node in self.currentPointsNodes():
            storageNode = node.GetStorageNode()
            if storageNode is None:
                continue
            fileName = storageNode.GetFileName()
            if fileName and Path(fileName).resolve() == path.resolve():
                return True
        return False

    def load_annotations_from_file(self):
        """Load a markups file and adopt it as one of this module's annotations.

        Loading a second file does not replace the first: both are drawn, which is what makes
        two annotations of the same volume comparable side by side.
        """
        path = self.promptForFile("Load annotations", MARKUPS_FILE_FILTER)
        if path is None:
            return

        if self.isAlreadyLoaded(path) and not slicer.util.confirmYesNoDisplay(
                f"{path.name} is already loaded.\n\nLoad a second copy of it?",
                windowTitle="Sphere Annotation"):
            return

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

        if not self.spheres and self.currentModelNode() is None:
            # Nothing to draw, and nothing already drawn that needs clearing. Loading a
            # markups file with no whole pair in it should not leave an empty "Annotations"
            # model in the scene and tick a visibility box over it.
            return

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
            # This is the only thing the redraw needs. Updating the appender modifies the
            # polydata the model node was given in `draw_spheres`, the model node is
            # observing it, and the displayable managers turn that into a render request
            # that Slicer schedules at the view's own update rate.
            #
            # Which is why there is no `forceRenderAllViews()` here any more. It rendered
            # every 2D and 3D view synchronously on every PointModifiedEvent — an event that
            # also fires for the preview point tracking the cursor during place mode — so
            # the drag ran at whatever a full render of the whole layout costs, with Slicer's
            # own render throttling bypassed rather than used.
            self.appender.Update()

    def applySphere(self, source, node, index):
        """Point ``source`` at the sphere that control points ``2*index`` and ``2*index+1`` define."""
        first, second = spheres.point_indices(index)
        # Zeroed, not `np.empty`. GetNthControlPointPositionWorld logs and returns without
        # writing when it does not like the index, and uninitialised memory then reaches
        # vtkSphereSource as a centre — a sphere somewhere arbitrary, or a NaN radius that
        # takes the whole append pipeline with it, instead of one visibly at the origin.
        a, b = np.zeros(3), np.zeros(3)
        node.GetNthControlPointPositionWorld(first, a)
        node.GetNthControlPointPositionWorld(second, b)
        center, radius = spheres.center_and_radius(a, b)
        source.SetCenter(*center)
        source.SetRadius(radius)
        # No `source.Update()`: the appender pulls the whole pipeline, and executing each
        # source by hand first only re-tessellates them one at a time ahead of it.

    def set_annotations_visibility(self, state=None):
        displayNode = self.annotationsDisplayNode()
        if displayNode is not None:
            displayNode.SetVisibility(self.ui.annotationsVisibility.checked)

    def set_annotations_color(self, color=None):
        displayNode = self.annotationsDisplayNode()
        if displayNode is not None:
            displayNode.SetColor(*rendering.to_rgb(self.ui.ColorPickerButton.color))

    def set_annotations_opacity(self, value=None):
        displayNode = self.annotationsDisplayNode()
        if displayNode is not None:
            # The slider value, not half of it. It used to be halved on the way through, so
            # the annotator could never get past 50% opacity however far right they dragged.
            displayNode.SetOpacity(self.ui.annotationsOpacity.value)

    ############################################ Volume ############################################

    def load_volume(self):
        """Load a volume from a file the annotator picks, and show it."""
        path = self.promptForFile("Load volume", VOLUME_FILE_FILTER)
        if path is None:
            return

        # The selector would otherwise see the new node arrive and report it as picked,
        # adopting it as borrowed before it can be adopted here as owned.
        wasBlocked = self.ui.volumeSelector.blockSignals(True)
        try:
            # loadVolume hands the name straight to Qt, which cannot convert a Path.
            volNode = slicer.util.loadVolume(str(path))
        except (RuntimeError, OSError) as error:
            logging.exception("Could not load volume from %s", path)
            slicer.util.errorDisplay(f"Could not load the volume.\n\n{path.name}\n\n{error}")
            return
        else:
            self.adoptVolumeNode(volNode, owned=True)
        finally:
            self.ui.volumeSelector.blockSignals(wasBlocked)

    def onVolumeSelected(self, volNode):
        """The annotator picked a volume that is already in the scene, or none."""
        if volNode is self.currentVolumeNode():
            return
        if volNode is None:
            self.releaseVolumeNode()
            return
        self.adoptVolumeNode(volNode, owned=False)
        slicer.util.setSliceViewerLayers(background=volNode)

    def adoptVolumeNode(self, volNode, owned):
        """Make ``volNode`` the volume this module shows, set up its 3D rendering, and show it.

        ``owned`` says whether the module brought it into the scene (**Load**) or borrowed it
        (the selector). Only an owned volume is removed when it is replaced or cleaned; a
        borrowed one is only hidden. The previous version removed *every* scalar volume and
        every ROI node — including the crop ROI belonging to whatever else the annotator had
        open.
        """
        if volNode is self.currentVolumeNode():
            return
        self.releaseVolumeNode()
        self.volNode = volNode
        self.ownsVolume = owned

        volRenLogic = slicer.modules.volumerendering.logic()
        displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volNode)
        self.ownsRenderingNodes = not displayNode
        if not displayNode:
            displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volNode)
        volRenLogic.UpdateDisplayNodeFromVolumeNode(displayNode, volNode)
        self.ui.volumeSelector.setCurrentNode(volNode)

        min_value, max_value = volNode.GetImageData().GetScalarRange()
        # Widen, then narrow. Assigning one end past the other drags that other end along and
        # the value with it — setting `minimum = 2000` on a (0, 100) slider leaves it at
        # (2000, 2000) with the value on top — so the pair must never be crossed, and
        # ctkSliderWidget's atomic `setRange` is not exposed on the Python side.
        slider = self.ui.volumeThreshold
        slider.minimum = min(min_value, slider.minimum)
        slider.maximum = max_value
        slider.minimum = min_value
        slider.value = rendering.default_threshold(min_value, max_value)
        self.ui.vol_visibility.checked = True

        # Applied here rather than left to the assignments above, which only emit when the
        # value actually *changes*. A second volume with the same scalar range as the first —
        # the same protocol, the next patient — does not change the threshold, so nothing was
        # emitted and the new display node kept the preset `UpdateDisplayNodeFromVolumeNode`
        # gave it. Measured in Slicer 5.12.3: a five-node default ramp, while the two sliders
        # went on claiming a threshold of 333 at full opacity. The controls described a volume
        # that was not the one on screen.
        #
        # The visibility call is belt and braces rather than a fix: a rendering display node
        # is created visible, so the box only has to be able to turn it *off*. Keeping the
        # checkbox authoritative here costs nothing and means one less thing to re-derive.
        self.applyOpacityRamp()
        self.set_volume_visibility()

    def releaseVolumeNode(self):
        """Stop showing the current volume, removing only what this module put in the scene.

        Forgets first, then removes, for the same reason :meth:`reset` does: removing a node
        reaches the selector, which reports the change back here.
        """
        volNode = self.currentVolumeNode()
        if volNode is None:
            return
        ownsVolume, ownsRenderingNodes = self.ownsVolume, self.ownsRenderingNodes
        self.volNode = None
        self.ownsVolume = False
        self.ownsRenderingNodes = False

        if ownsRenderingNodes:
            self.removeVolumeRenderingNodes(volNode)
        else:
            displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode)
            if displayNode is not None:
                displayNode.SetVisibility(False)
        if ownsVolume:
            slicer.mrmlScene.RemoveNode(volNode)

    def removeVolumeRenderingNodes(self, volNode):
        """Remove the rendering nodes that were created for ``volNode``.

        ``RemoveNode`` on the volume does not take them with it. Without this, every volume
        after the first left behind a display node, a volume property node and an ROI — in
        the scene, in the subject hierarchy, and in the Save dialog the annotator then has to
        read to find their own annotation.
        """
        displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode)
        if not displayNode:
            return
        for node in (displayNode.GetVolumePropertyNode(), displayNode.GetROINode(), displayNode):
            if node is not None:
                slicer.mrmlScene.RemoveNode(node)

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

    def applyOpacityRamp(self, value=None):
        """Rewrite the scalar opacity ramp from the two sliders.

        Both sliders rebuild the whole ramp, and both are connected straight to this — the
        ``value`` Qt hands over is read back off the widgets instead. The opacity slider used
        to patch control point number 1 in place, which only worked for as long as the
        threshold slider happened to leave the upper point at that index.
        """
        displayNode = self.volumeRenderingDisplayNode()
        if displayNode is None:
            return
        scalarOpacity = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
        min_value, max_value = self.currentVolumeNode().GetImageData().GetScalarRange()
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

    def export_spheres(self):
        """Write every sphere this module draws to a CSV file the annotator picks.

        One annotation per points node, labelled with the node's name. A trailing unpaired
        point is not a sphere and is left out — said out loud, since a missing row is
        otherwise easy to mistake for a missing annotation.
        """
        nodes = self.currentPointsNodes()
        if not nodes:
            slicer.util.infoDisplay("There are no annotations to export yet.", windowTitle="Sphere Annotation")
            return
        path = qt.QFileDialog.getSaveFileName(slicer.util.mainWindow(), "Export spheres", "", CSV_FILE_FILTER)
        if not path:
            return
        path = Path(path)

        annotations = [(node.GetName(), self.pointPositions(node)) for node in nodes]
        try:
            export.write_csv(path, export.sphere_rows(annotations))
        except OSError as error:
            logging.exception("Could not write spheres to %s", path)
            slicer.util.errorDisplay(f"Could not export the spheres.\n\n{path.name}\n\n{error}")
            return

        unpaired = [name for name, positions in annotations if spheres.has_unpaired_point(len(positions))]
        if unpaired:
            slicer.util.warningDisplay(
                "The last point of these annotations has no partner and was not exported:\n\n"
                + "\n".join(unpaired), windowTitle="Sphere Annotation")

    def pointPositions(self, node):
        """The world positions of every control point of ``node``, in order."""
        positions = []
        for index in range(node.GetNumberOfControlPoints()):
            position = np.zeros(3)
            node.GetNthControlPointPositionWorld(index, position)
            positions.append(position)
        return positions

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
        self.setUp()
        self.test_a_second_volume_is_shown_like_the_first()
        self.setUp()
        self.test_deleting_a_points_node_stops_drawing_its_spheres()
        self.setUp()
        self.test_clean_leaves_a_picked_volume_in_the_scene()
        self.setUp()
        self.test_picking_a_volume_replaces_a_loaded_one()
        self.setUp()
        self.test_exported_rows_match_the_drawn_spheres()

    def widget(self):
        slicer.util.selectModule("SphereAnnotation")
        return slicer.modules.SphereAnnotationWidget

    def placePoints(self, node, *positions):
        for position in positions:
            node.AddControlPoint(vtk.vtkVector3d(*position))

    def syntheticVolume(self, name):
        """A tiny volume with a scalar range of exactly (0, 1000).

        Two of these are indistinguishable to the threshold slider, which is the whole point:
        it is the volume whose default threshold matches the one already on the slider that
        exposes a control relying on a Qt signal it will not get.
        """
        volNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", name)
        image = vtk.vtkImageData()
        image.SetDimensions(4, 4, 4)
        image.AllocateScalars(vtk.VTK_SHORT, 1)
        volNode.SetAndObserveImageData(image)
        array = slicer.util.arrayFromVolume(volNode)
        array[:] = 0
        array[2:, 2:, 2:] = 1000
        slicer.util.arrayFromVolumeModified(volNode)
        volNode.CreateDefaultDisplayNodes()
        return volNode

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
        # And nothing was added to the scene to hold it. An empty model node reads as an
        # annotation that exists and is invisible, which is not the state the annotator is in.
        self.assertIsNone(widget.currentModelNode())

        # Once a sphere has existed the model stays, and is emptied rather than removed.
        self.placePoints(node, (10, 0, 0))
        widget.draw_spheres()
        node.RemoveNthControlPoint(1)
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

        # And the geometry the *model node* holds moved with it. Nothing forces a render any
        # more, so this is the chain the whole redraw rests on: the appender updates, the
        # polydata the model observes is modified, and the displayable managers ask for a
        # render. A sphere source that moved while the model's polydata did not would leave
        # the annotator dragging a point that nothing follows.
        bounds = [0.0] * 6
        widget.currentModelNode().GetPolyData().GetBounds(bounds)
        # Not 20.0 exactly — a 30-facet hull falls just inside its own radius.
        self.assertAlmostEqual(bounds[1], 20.0, delta=0.1)

    def test_clean_removes_only_this_modules_nodes(self):
        self.delayDisplay("Clean removes only this module's nodes")
        widget = self.widget()

        foreignVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "Someone else's volume")
        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0), (10, 0, 0))
        widget.draw_spheres()
        model = widget.currentModelNode()
        widget.adoptVolumeNode(self.syntheticVolume("Ours"), owned=True)
        displayNode = widget.volumeRenderingDisplayNode()
        propertyNode = displayNode.GetVolumePropertyNode()

        widget.clearButton()

        self.assertTrue(slicer.mrmlScene.IsNodePresent(foreignVolume))
        self.assertFalse(slicer.mrmlScene.IsNodePresent(node))
        self.assertFalse(slicer.mrmlScene.IsNodePresent(model))
        self.assertEqual(widget.currentPointsNodes(), [])
        # Including the rendering nodes, which RemoveNode on the volume does not take with it.
        self.assertFalse(slicer.mrmlScene.IsNodePresent(displayNode))
        self.assertFalse(slicer.mrmlScene.IsNodePresent(propertyNode))

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

    def test_deleting_a_points_node_stops_drawing_its_spheres(self):
        """Deleting the points from the Data module has to take their spheres with them."""
        self.delayDisplay("Deleting a points node stops drawing its spheres")
        widget = self.widget()

        kept = widget.ensurePointsNode()
        self.placePoints(kept, (0, 0, 0), (10, 0, 0))
        deleted = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Second annotation")
        widget.adoptPointsNode(deleted)
        self.placePoints(deleted, (50, 0, 0), (60, 0, 0))
        self.assertEqual(len(widget.spheres), 2)

        slicer.mrmlScene.RemoveNode(deleted)

        self.assertEqual(len(widget.spheres), 1)
        self.assertEqual(widget.currentPointsNodes(), [kept])
        self.assertAlmostEqual(widget.spheres[0].GetCenter()[0], 5.0)

    def test_a_second_volume_is_shown_like_the_first(self):
        """The ramp may not depend on a widget value happening to change.

        Both volumes here have the same scalar range, and **the sliders are not touched
        between the two loads** — which is the whole scenario. The second volume's default
        threshold is the value the slider already holds, so `valueChanged` never fires. The
        module used to rely on that signal to reach the display node, and without it the new
        volume kept the five-node preset `UpdateDisplayNodeFromVolumeNode` gave it while the
        sliders went on describing the ramp the *first* volume got.
        """
        self.delayDisplay("A second volume is shown like the first")
        widget = self.widget()

        widget.adoptVolumeNode(self.syntheticVolume("First"), owned=True)
        widget.adoptVolumeNode(self.syntheticVolume("Second"), owned=True)

        displayNode = widget.volumeRenderingDisplayNode()
        self.assertIsNotNone(displayNode)
        self.assertTrue(displayNode.GetVisibility())

        # The ramp is this module's — two nodes, the upper one where the sliders say.
        scalarOpacity = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
        self.assertEqual(scalarOpacity.GetSize(), rendering.SCALAR_OPACITY_POINT_COUNT)
        upper = [0.0] * 4
        scalarOpacity.GetNodeValue(rendering.SCALAR_OPACITY_POINT_COUNT - 1, upper)
        self.assertAlmostEqual(upper[0], widget.ui.volumeThreshold.value)
        self.assertAlmostEqual(upper[1], widget.ui.volumeOpacity.value)

    def test_clean_leaves_a_picked_volume_in_the_scene(self):
        """A volume picked in the selector was the annotator's before it was the module's."""
        self.delayDisplay("Clean leaves a picked volume in the scene")
        widget = self.widget()

        picked = self.syntheticVolume("Picked")
        widget.ui.volumeSelector.setCurrentNode(picked)
        self.assertIs(widget.currentVolumeNode(), picked)
        displayNode = widget.volumeRenderingDisplayNode()
        self.assertIsNotNone(displayNode)

        widget.clearButton()

        self.assertTrue(slicer.mrmlScene.IsNodePresent(picked))
        # The rendering nodes did not exist before the module made them, so they go.
        self.assertFalse(slicer.mrmlScene.IsNodePresent(displayNode))
        self.assertIsNone(widget.currentVolumeNode())
        self.assertIsNone(widget.ui.volumeSelector.currentNode())

    def test_picking_a_volume_replaces_a_loaded_one(self):
        """The module still shows one volume at a time; only the one it loaded is removed."""
        self.delayDisplay("Picking a volume replaces a loaded one")
        widget = self.widget()

        loaded = self.syntheticVolume("Loaded")
        widget.adoptVolumeNode(loaded, owned=True)
        picked = self.syntheticVolume("Picked")
        widget.ui.volumeSelector.setCurrentNode(picked)

        self.assertFalse(slicer.mrmlScene.IsNodePresent(loaded))
        self.assertIs(widget.currentVolumeNode(), picked)

        # Picking a different one hands the first back, minus the rendering nodes made for it.
        other = self.syntheticVolume("Other")
        firstDisplayNode = widget.volumeRenderingDisplayNode()
        widget.ui.volumeSelector.setCurrentNode(other)

        self.assertTrue(slicer.mrmlScene.IsNodePresent(picked))
        self.assertIs(widget.currentVolumeNode(), other)
        self.assertFalse(slicer.mrmlScene.IsNodePresent(firstDisplayNode))

    def test_exported_rows_match_the_drawn_spheres(self):
        """Export reads the same world positions the spheres are drawn from."""
        self.delayDisplay("Exported rows match the drawn spheres")
        widget = self.widget()

        node = widget.ensurePointsNode()
        self.placePoints(node, (0, 0, 0), (10, 0, 0), (40, 0, 0))
        widget.draw_spheres()

        rows = export.sphere_rows([(node.GetName(), widget.pointPositions(node))])

        self.assertEqual(len(rows), len(widget.spheres))
        self.assertEqual(rows[0]["label"], node.GetName())
        self.assertAlmostEqual(rows[0]["radius"], widget.spheres[0].GetRadius())
        self.assertEqual([rows[0]["center_r"], rows[0]["center_a"], rows[0]["center_s"]],
                         list(widget.spheres[0].GetCenter()))
