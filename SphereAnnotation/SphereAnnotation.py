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
        self.parent.title = "Sphere Annotation"
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
#        self.cleanup()
        self.cleanButton()

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

    def onVolumeThresholdChanged(self, value):
        """
        This method is an event handler that is triggered when the volume threshold is changed. The input parameter "value" represents the new threshold value set by the user.
        The method first retrieves the volume node from the scene by using the getNodesByClass method of the slicer.util module. It then gets the volume rendering display node and the volume property node of the first volume in the scene by using the GetFirstVolumeRenderingDisplayNode and GetVolumePropertyNode methods of the slicer.modules.volumerendering.logic() module.
        Next, it retrieves the scalar opacity transfer function from the volume property node and the scalar range of the volume from the volume node. It then sets the threshold by adding two points to the scalar opacity transfer function: one with the new upper threshold value and the opacity value set by the user, and another with the value of the threshold minus a margin, and an opacity of 0.0. The margin is calculated as 10% of the scalar range upper bound.
        """
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
        """
        This method is associated with a "Save" button and is used to open the "Save Data" dialog box in 3D Slicer.
        """
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
        color = (self.ui.ColorPickerButton.color.red()/255, 
                 self.ui.ColorPickerButton.color.green()/255, 
                 self.ui.ColorPickerButton.color.blue()/255)
        # update sphere color
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        for node in nodes:
            node.GetDisplayNode().SetColor(color)


    def set_annotations_opacity(self):
        # update spheres opacity
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        for node in nodes:
            node.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value/2)

    def create_model(self, model):
        self.remove_nodes_by_name("Annotations")

        modelNode = slicer.modules.models.logic().AddModel(model.GetOutput())
        modelNode.SetName("Annotations")
        modelNode.GetDisplayNode().SetVisibility2D(True)
        modelNode.GetDisplayNode().SetSliceIntersectionThickness(3)
        modelNode.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value/2)
        
        color = (self.ui.ColorPickerButton.color.red()/255, 
                self.ui.ColorPickerButton.color.green()/255, 
                self.ui.ColorPickerButton.color.blue()/255)
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

            min_val, max_val = volNode.GetImageData().GetScalarRange()
            self.ui.volumeThreshold.maximum = max_val
            self.ui.volumeThreshold.minimum = min_val
            self.ui.volumeThreshold.value = (max_val+min_val)/3

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

    def onVolumeOpacityChanged(self):
        volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        if volNode:
            displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
            scalarOpacity = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()
            p = [0]*4
            scalarOpacity.GetNodeValue(1, p)
            p[1] = self.ui.volumeOpacity.value
            scalarOpacity.SetNodeValue(1, p)

    def cleanup(self):
        slicer.mrmlScene.Clear(0)
        self.removeObservers()

    def enter(self):
        self.initializeParameterNode()

    def exit(self):
        return

    def onSceneStartClose(self, caller, event):
        return

    def onSceneEndClose(self, caller, event):
        return

    def initializeParameterNode(self):
        return
