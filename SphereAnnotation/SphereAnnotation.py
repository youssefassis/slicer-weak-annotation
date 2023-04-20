import logging, os, vtk, qt
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
        self.clearButton()

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

        self.spheres = []
        self.appender = None

    def onVolumeThresholdChanged(self, value):
        """
        This method is an event handler that is triggered when the volume threshold is changed. 
        The input parameter "value" represents the new threshold value set by the user.
        The method first retrieves the volume node from the scene by using the getNodesByClass 
        method of the slicer.util module. It then gets the volume rendering display node and 
        the volume property node of the first volume in the scene by using the 
        GetFirstVolumeRenderingDisplayNode and GetVolumePropertyNode methods of the 
        slicer.modules.volumerendering.logic() module.
        Next, it retrieves the scalar opacity transfer function from the volume property node
        and the scalar range of the volume from the volume node. It then sets the threshold 
        by adding two points to the scalar opacity transfer function: one with the new upper 
        threshold value and the opacity value set by the user, and another with the value of
        the threshold minus a margin, and an opacity of 0.0. The margin is calculated as 10%
        of the scalar range upper bound.
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

    def create_point(self):
        """
        Create a new point in the 3D Slicer scene. The function then adds three observer methods to
        the markups attribute, which listen for changes to the point in the Slicer scene and update
        the spheres according to the event.
        """
        slicer.modules.markups.logic().StartPlaceMode(0)
        fiducial_nodes = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        for fiducial_node in fiducial_nodes:
            fiducial_node.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.draw_spheres)
            fiducial_node.AddObserver((slicer.vtkMRMLMarkupsNode).PointRemovedEvent, self.draw_spheres)
            fiducial_node.AddObserver((slicer.vtkMRMLMarkupsNode).PointModifiedEvent, self.MoveSpheres)

    def remove_point(self):
        """
        The purpose of this function is to remove the last created point from a 
        vtkMRMLMarkupsFiducialNode in a 3D Slicer scene.
        """
        for markup in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if markup.GetNumberOfControlPoints() > 0:
                markup.RemoveNthControlPoint(markup.GetNumberOfControlPoints() - 1)

    def remove_nodes_by_name(self, name):
        # Get a list of all nodes in the Slicer scene with the specified name.
        nodes = slicer.mrmlScene.GetNodesByName(name)
        # Loop through each node with the specified name and remove it from the Slicer scene.
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)

    def load_annotations_from_file (self):
        # Create a file dialog for selecting the annotation file to load.
        dialog = qt.QFileDialog()
        dialog.setNameFilters(['Markups (*.Fcsv)'])
        # If the user selects a file, load it.
        if dialog.exec_() == qt.QDialog.Accepted:
            # Get the file path of the selected file.
            file_path = dialog.selectedFiles()[0]
            try:
                # Load the markups from the specified file and add them to the Slicer scene.
                slicer.util.loadMarkupsFiducialList(file_path)
            except:
                # Display an error message if there was an error loading the file.
                slicer.util.errorDisplay('Error when loading the Fidicual file.')
                return

            fiducial_nodes = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
            for fiducial_node in fiducial_nodes:
                fiducial_node.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.draw_spheres)
                fiducial_node.AddObserver((slicer.vtkMRMLMarkupsNode).PointRemovedEvent, self.draw_spheres)
                fiducial_node.AddObserver((slicer.vtkMRMLMarkupsNode).PointModifiedEvent, self.MoveSpheres)

            # Draw spheres at the locations of the points.
            self.draw_spheres()
    
    def draw_spheres(self, caller=None, event=None):
        # Remove any existing annotation nodes
        self.remove_nodes_by_name("Annotations")
        self.spheres, self.appender = [], None

        # Create a vtkAppendPolyData object to combine the spheres into a single model
        self.appender = vtk.vtkAppendPolyData() if self.appender is None else self.appender

        markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        for markup in markups:
            # Iterate over the spheres and add each one to the appender
            for idx in range(markup.GetNumberOfControlPoints()//2):
                sphere = vtk.vtkSphereSource()
                # Calculate the center and radius of the sphere using the getSphereCenterAndRadius method
                center, radius = self.getSphereCenterAndRadius(markup, idx*2)
                
                # Set the center and radius of the sphere
                sphere.SetCenter(center)
                sphere.SetRadius(radius)

                # Set the resolution of the sphere
                sphere.SetPhiResolution(30)
                sphere.SetThetaResolution(30)
                sphere.Update()
                
                self.spheres.append(sphere)
                # Add the sphere to the appender
                self.appender.AddInputConnection(sphere.GetOutputPort()) 
    
                # Update the appender
                self.appender.Update()

        # Create a model from the appended polydata
        self.create_model(self.appender)

        # Set the color of the annotations.
        self.set_annotations_color()
        # Set the opacity of the annotations.
        self.set_annotations_opacity()

    def MoveSpheres(self, caller=None, event=None):
        sphere_idx = 0
        markups = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        for markup in markups:
            # Iterate over the spheres and update the position of each one
            for idx in range(markup.GetNumberOfControlPoints()//2):
                if sphere_idx >= len(self.spheres) : return
                sphere = self.spheres[sphere_idx]
                center, radius = self.getSphereCenterAndRadius(markup, idx*2)
                
                # Set the center of the sphere to the new position
                sphere.SetCenter(center)
                sphere.SetRadius(radius)
                sphere.Update()

                # Update the appender
                self.appender.Update()
                # Force render all the views
                slicer.util.forceRenderAllViews()
                sphere_idx += 1


    def getSphereCenterAndRadius(self, markups, startPointIndex):
        # Create two empty numpy arrays of size 3 to hold the positions of the two points.
        A, B = np.zeros(3), np.zeros(3)
        # Get the position of the nth control point (startPointIndex) and store it in A.
        markups.GetNthControlPointPosition(startPointIndex, A)
        # Get the position of the (n+1)th control point and store it in B.
        markups.GetNthControlPointPosition(startPointIndex+1, B)
        # Calculate the midpoint between the two points.
        s = (A + B) / 2
        # Calculate the radius of the sphere using the distance between the two points.
        R = np.linalg.norm(A - B)/2
        # Return the center and radius of the sphere as a tuple.
        return s, R

    def set_annotations_visibility(self):
        # Get all nodes with the name "Annotations"
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        # Loop through each node and set its display visibility based on the state of the checkbox
        for node in nodes:
            node.GetDisplayNode().SetVisibility(self.ui.annotationsVisibility.checked)

    def set_annotations_color(self, color=None):
        color = (self.ui.ColorPickerButton.color.red()/255, 
                 self.ui.ColorPickerButton.color.green()/255, 
                 self.ui.ColorPickerButton.color.blue()/255)
        # Get all nodes with the name "Annotations"
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        # Loop through each node and set its display color
        for node in nodes:
            node.GetDisplayNode().SetColor(color)

    def set_annotations_opacity(self):
        # update spheres opacity
        nodes = slicer.mrmlScene.GetNodesByName("Annotations")
        # Loop through each node and set its display opacity
        for node in nodes:
            node.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value/2)

    def create_model(self, model):
        # Create a model node from the provided polydata
        modelNode = slicer.modules.models.logic().AddModel(model.GetOutput())
        modelNode.SetName("Annotations")
        modelNode.GetDisplayNode().SetVisibility2D(True)
        modelNode.GetDisplayNode().SetSliceIntersectionThickness(3)
        modelNode.GetDisplayNode().SetOpacity(self.ui.annotationsOpacity.value/2)
        
        # Set the visibility of the spheres node in the scene
        self.ui.annotationsVisibility.checked = 1
        return modelNode

    def remove_nodes_by_type(self, node_type_name):
        # Get node by type
        nodes = slicer.util.getNodesByClass(node_type_name)
        # Loop and remove nodes
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)

    ############################################ Volume ############################################
    def load_volume (self): 
        dialog = qt.QFileDialog()
        dialog.setNameFilters(['Nifty (*.nii.gz *.nii)'])

        # If the user selects a file and clicks OK, then proceed to load the volume
        if dialog.exec_() == qt.QDialog.Accepted:
            # Get the file path of the selected file.
            file_path = dialog.selectedFiles()[0]
            # Remove any existing volumes before loading a new one
            self.remove_existing_volumes()
            # Load the volume into Slicer
            slicer.util.loadVolume(file_path)

            # Get the volume node and create a default volume rendering if one does not already exist
            volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")[0]

            # Volume renderings view (3D)
            volRenLogic = slicer.modules.volumerendering.logic()
            displayNode = volRenLogic.GetFirstVolumeRenderingDisplayNode(volNode)
            if not displayNode: displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volNode)
            volRenLogic.UpdateDisplayNodeFromVolumeNode(displayNode, volNode)

            # Set the threshold values for the volume rendering
            min_val, max_val = volNode.GetImageData().GetScalarRange()
            self.ui.volumeThreshold.maximum = max_val
            self.ui.volumeThreshold.minimum = min_val
            self.ui.volumeThreshold.value = (max_val+min_val)/3

            # Set the visibility of the volume to be on
            self.ui.vol_visibility.checked = 1

    def set_volume_visibility(self):
        """
        If there is at least one volume node in the scene, set the visibility
        of the first volume node's display node
        """
        volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        if volNode:
            displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
            # If a display node exists for the volume node, then set the visibility of the display node to match the checkbox value
            if displayNode:
                displayNode.SetVisibility(self.ui.vol_visibility.checked)

    def remove_existing_volumes(self):
        self.remove_nodes_by_type("vtkMRMLScalarVolumeNode") # remove existing volume
        self.remove_nodes_by_type("vtkMRMLMarkupsROINode") # remove existing ROI

    def onVolumeOpacityChanged(self):
        """
        This function is called when the volume opacity slider is changed in the user interface.
        """
        # Get the first scalar volume node in the scene.
        volNode = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        # Check if there is at least one scalar volume node in the scene.
        if volNode:
            # Get the volume rendering display node of the first scalar volume node.
            displayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volNode[0])
            
            # Get the scalar opacity transfer function of the volume property node.
            scalarOpacity = displayNode.GetVolumePropertyNode().GetVolumeProperty().GetScalarOpacity()

            # Get the current opacity value for the second control point of the scalar opacity transfer function.
            # The second control point is the midpoint of the transfer function.    
            p = [0]*4
            scalarOpacity.GetNodeValue(1, p)

            # Update the opacity value for the second control point with the new value from the slider in the user interface.
            p[1] = self.ui.volumeOpacity.value
            scalarOpacity.SetNodeValue(1, p)

    def cleanup(self):
        # Clear the MRML scene, deleting all nodes and references.
        slicer.mrmlScene.Clear(0)
        # Remove any observers registered by this module instance.
        self.removeObservers()
