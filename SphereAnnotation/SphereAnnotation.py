import logging
import os

import vtk, qt
import numpy as np

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

class SphereAnnotation(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Spheres Annotation"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Aneurysms"]
        self.parent.dependencies = []
        self.parent.contributors = ["Youssef Assis (Loria lab.)"]
        self.parent.acknowledgementText = "This module was developed by Youssef Assis"


class SphereAnnotationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation

        slicer.app.pythonConsole().clear()
        self.cleanup()

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/SphereAnnotation.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        #self.logic = SphereAnnotationLogic()

        # Buttons
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

        self.markups = None
        self.spheres = None
        self.appender = None

    # def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

    def onVolumeThresholdChanged(self, value):
        volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        if volNode:
            displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
            volumePropertyNode = displayNode.GetVolumePropertyNode()

            # get the scalar opacity transfer function
            scalarOpacity = volumePropertyNode.GetVolumeProperty().GetScalarOpacity()

            # get the range of the scalar volume
            rang = volNode[0].GetImageData().GetScalarRange()
            
            # set the threshold
            margin = rang[1]/10
            upperThreshold = value
            scalarOpacity.RemoveAllPoints()
            scalarOpacity.AddPoint(upperThreshold, self.ui.volumeOpacity.value)
            scalarOpacity.AddPoint(max(rang[0], upperThreshold-margin), 0.0)

    def saveButton(self):
        slicer.util.openSaveDataDialog()

    def clearButton(self):
        self.cleanup()

    # Annotations = Spheres
    def create_point(self):
        slicer.modules.markups.logic().StartPlaceMode(0)
        if self.markups is None and slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            self.markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")[0]
            self.markups.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.updateSpheres, 2)
            self.markups.AddObserver((slicer.vtkMRMLMarkupsNode).PointRemovedEvent, self.updateSpheres, 2)
            self.markups.AddObserver((slicer.vtkMRMLMarkupsNode).PointModifiedEvent, self.MoveSpheres, 2)

    def remove_point(self):
        markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        for markup in markups:
            if markup.GetNumberOfControlPoints() > 0:
                markup.RemoveNthControlPoint(markup.GetNumberOfControlPoints() - 1)

    def getSphereCenterAndRadius(self, markup, startPointIndex):
        A, B = np.zeros(3), np.zeros(3)
        markup.GetNthControlPointPosition(startPointIndex, A)
        markup.GetNthControlPointPosition(startPointIndex+1, B)
        s = (A + B) / 2
        R = np.linalg.norm(A - B)/2
        return s, R

    def remove_nodes_by_name(self, name):
        nodes = slicer.mrmlScene.GetNodesByName(name)
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)

    def load_annotations_from_file (self):
        dialog = qt.QFileDialog()
        dialog.setNameFilters(['Markups (*.Fcsv)'])
        if dialog.exec_() == qt.QDialog.Accepted:
            file_path = dialog.selectedFiles()[0]

            # try:
            slicer.util.loadMarkupsFiducialList(file_path)
            #if self.markups is None:
            self.markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")[0]
            self.markups.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.updateSpheres, 2)
            self.markups.AddObserver((slicer.vtkMRMLMarkupsNode).PointRemovedEvent, self.updateSpheres, 2)
            self.markups.AddObserver((slicer.vtkMRMLMarkupsNode).PointModifiedEvent, self.MoveSpheres, 2)
            # except:
            #     slicer.util.errorDisplay('Please choose markups file with the right format.')

            self.draw_spheres()
            self.set_annotations_color()
            self.set_annotations_opacity()
    
    def draw_spheres(self, opacity=None, color=None):
        # if self.markups is None:
        #     self.markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")[0]

        nb_spheres = self.markups.GetNumberOfControlPoints()//2
        if nb_spheres > 0:
            spheres = [vtk.vtkSphereSource() for i in range(0, nb_spheres)]
            self.appender = vtk.vtkAppendPolyData() if self.appender is None else self.appender
            
            for idx, sphere in enumerate(spheres):
                center, radius = self.getSphereCenterAndRadius(self.markups, idx*2)
                
                sphere.SetCenter(center)
                sphere.SetRadius(radius)
                sphere.SetPhiResolution(30)
                sphere.SetThetaResolution(30)
                sphere.Update()
                self.appender.AddInputConnection(sphere.GetOutputPort()) 
            self.appender.Update()
            self.create_model(self.appender)

    def updateSpheres(self, caller = None, event = None ):
        print("Update spheres")
        self.remove_nodes_by_name("Annotations")

        nb_spheres = self.markups.GetNumberOfControlPoints()//2
        if nb_spheres >= 1:
            self.spheres = [vtk.vtkSphereSource() for i in range(0, nb_spheres)]
            self.appender = vtk.vtkAppendPolyData()
            
            for idx, sphere in enumerate(self.spheres):
                center, radius = self.getSphereCenterAndRadius (self.markups, idx*2)

                sphere.SetCenter(center)
                sphere.SetRadius(radius)
                sphere.SetPhiResolution(30)
                sphere.SetThetaResolution(30)
                sphere.Update()
                self.appender.AddInputConnection(sphere.GetOutputPort()) 
            self.appender.Update()

            model = self.create_model(self.appender)
            
    def MoveSpheres(self, caller = None, event = None):
        print("Move spheres")
        if self.spheres and self.appender:
            for idx, sphere in enumerate(self.spheres):
                center, radius = self.getSphereCenterAndRadius(self.markups, idx*2)
                sphere.SetCenter(center)
                sphere.SetRadius(radius)
                sphere.Update()
            self.appender.Update()
            slicer.util.forceRenderAllViews()

    def set_annotations_visibility(self):
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        for node in nodes:
            node.GetDisplayNode().SetVisibility(self.ui.annotationsVisibility.checked)

    def set_annotations_color(self, color=None):
        color = (color.red()/255, color.green()/255, color.blue()/255) if color is not None else (self.ui.ColorPickerButton.color.red()/255, self.ui.ColorPickerButton.color.green()/255, self.ui.ColorPickerButton.color.blue()/255)
        #color = tuple(int(str(self.ui.ColorPickerButton.color)[1:][i:i+2], 16) for i in (0, 2, 4))
        # update sphere color
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        for node in nodes:
            node.GetDisplayNode().SetColor(color)


    def set_annotations_opacity(self):
        # update spheres opacity
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        for node in nodes:
            node.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value/4)


    def create_model(self, model):
        self.remove_nodes_by_name("Annotations")

        modelNode = slicer.modules.models.logic().AddModel(model.GetOutput())
        modelNode.SetName("Annotations")
        modelNode.GetDisplayNode().SetVisibility2D(True)
        modelNode.GetDisplayNode().SetSliceIntersectionThickness(3)
        modelNode.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value/10)
        
        color = (self.ui.ColorPickerButton.color.red()/255, self.ui.ColorPickerButton.color.green()/255, self.ui.ColorPickerButton.color.blue()/255)
        modelNode.GetDisplayNode().SetColor(color)

        self.ui.annotationsVisibility.checked = 1

        return modelNode


    def remove_nodes_by_type(self, node_type_name):
        volumeNodes = slicer.util.getNodesByClass(node_type_name)
        for node in volumeNodes:
            slicer.mrmlScene.RemoveNode(node)

    ############################################ Volume ############################################
    def load_volume (self): 
        dialog = qt.QFileDialog()
        dialog.setNameFilters(['Nifty (*.nii.gz *.nii)'])

        if dialog.exec_() == qt.QDialog.Accepted:
            file_path = dialog.selectedFiles()[0]
            self.remove_existing_volumes()
            slicer.util.loadVolume(file_path)

            volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")[0]
            # volume renderings view
            volRenLogic = slicer.modules.volumerendering.logic()
            displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volNode)
            if not displayNode: displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volNode)
            volRenLogic.UpdateDisplayNodeFromVolumeNode(displayNode, volNode)

            voxels = slicer.util.arrayFromVolume(volNode)
            self.ui.volumeThreshold.maximum = np.max(voxels)
            self.ui.volumeThreshold.minimum = np.min(voxels)
            self.ui.volumeThreshold.value = (self.ui.volumeThreshold.minimum+self.ui.volumeThreshold.maximum)/2

            self.ui.vol_visibility.checked = 1

    def set_volume_visibility(self):
        volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        if volNode:
            volRenLogic = slicer.modules.volumerendering.logic()
            displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volNode[0])
            if displayNode:
                displayNode.SetVisibility(self.ui.vol_visibility.checked)

    def remove_existing_volumes(self):
        self.remove_nodes_by_type("vtkMRMLScalarVolumeNode") # remove existing volume
        self.remove_nodes_by_type("vtkMRMLMarkupsROINode") # remove existing volume

    # def onVolumeThresholdChanged(self):
    #     volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
    #     if volNode:
    #         displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
    #         func = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
    #         p1, p2, p3 = [0]*4, [0]*4, [0]*4 # points
    #         func.GetNodeValue(1, p1)
    #         func.GetNodeValue(2, p2)
    #         func.GetNodeValue(3, p3)
    #         d = self.ui.volumeThreshold.value - p2[0]
    #         p1[0] += d
    #         p2[0] += d
    #         p3[0] += d

    #         p1[1], p2[1], p3[1] = 0, self.ui.volumeOpacity.value, 0
    #         func.SetNodeValue(1,p1)
    #         func.SetNodeValue(2,p2)
    #         func.SetNodeValue(3,p3)

    def onVolumeOpacityChanged(self):
        volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        if volNode:
            displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
            scalarOpacity = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
            p = [0]*4
            scalarOpacity.GetNodeValue(1, p)
            p[1] = self.ui.volumeOpacity.value
            scalarOpacity.SetNodeValue(1, p)

    # def onVolumeOpacityChanged(self):
    #     volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
    #     if volNode:
    #         displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
    #         func = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
    #         p = [0]*4
    #         func.GetNodeValue(2, p)
    #         p[1] = self.ui.volumeOpacity.value
    #         func.SetNodeValue(2, p)
    ##############################################################################################################
    

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        slicer.mrmlScene.Clear(0)
        self.removeObservers()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        return
        # self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        return
        # self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        # if self.parent.isEntered:
        #     self.initializeParameterNode()
        return

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.
        return

        #self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        # if not self._parameterNode.GetNodeReference("InputVolume"):
        #     firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
        #     if firstVolumeNode:
        #         self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    # def setParameterNode(self, inputParameterNode):
    #     """
    #     Set and observe parameter node.
    #     Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    #     """

    #     if inputParameterNode:
    #         self.logic.setDefaultParameters(inputParameterNode)

    #     # Unobserve previously selected parameter node and add an observer to the newly selected.
    #     # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    #     # those are reflected immediately in the GUI.
    #     if self._parameterNode is not None:
    #         self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    #     self._parameterNode = inputParameterNode
    #     if self._parameterNode is not None:
    #         self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    #     # Initial GUI update
    #     self.updateGUIFromParameterNode()

    # def updateGUIFromParameterNode(self, caller=None, event=None):
    #     """
    #     This method is called whenever parameter node is changed.
    #     The module GUI is updated to show the current state of the parameter node.
    #     """

    #     if self._parameterNode is None or self._updatingGUIFromParameterNode:
    #         return

    #     # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    #     self._updatingGUIFromParameterNode = True

    #     # Update node selectors and sliders
    #     self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputVolume"))
    #     self.ui.outputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputVolume"))
    #     self.ui.invertedOutputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputVolumeInverse"))
    #     self.ui.imageThresholdSliderWidget.value = float(self._parameterNode.GetParameter("Threshold"))
    #     self.ui.invertOutputCheckBox.checked = (self._parameterNode.GetParameter("Invert") == "true")

    #     # Update buttons states and tooltips
    #     if self._parameterNode.GetNodeReference("InputVolume") and self._parameterNode.GetNodeReference("OutputVolume"):
    #         self.ui.applyButton.toolTip = "Compute output volume"
    #         self.ui.applyButton.enabled = True
    #     else:
    #         self.ui.applyButton.toolTip = "Select input and output volume nodes"
    #         self.ui.applyButton.enabled = False

    #     # All the GUI updates are done
    #     self._updatingGUIFromParameterNode = False

    # def updateParameterNodeFromGUI(self, caller=None, event=None):
    #     """
    #     This method is called when the user makes any change in the GUI.
    #     The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    #     """

    #     if self._parameterNode is None or self._updatingGUIFromParameterNode:
    #         return

    #     wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    #     self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputSelector.currentNodeID)
    #     self._parameterNode.SetNodeReferenceID("OutputVolume", self.ui.outputSelector.currentNodeID)
    #     self._parameterNode.SetParameter("Threshold", str(self.ui.imageThresholdSliderWidget.value))
    #     self._parameterNode.SetParameter("Invert", "true" if self.ui.invertOutputCheckBox.checked else "false")
    #     self._parameterNode.SetNodeReferenceID("OutputVolumeInverse", self.ui.invertedOutputSelector.currentNodeID)

    #     self._parameterNode.EndModify(wasModified)