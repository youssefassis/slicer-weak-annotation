#-----------------------------------------------------------------------------
set(MODULE_NAME SphereAnnotation)

#-----------------------------------------------------------------------------
# SphereAnnotationLib is installed next to the module. Slicer puts the scripted-modules
# directory on sys.path, so `from SphereAnnotationLib import spheres` resolves at runtime.
# ADD NEW LIBRARY MODULES HERE — a file that is not listed still works from
# --additional-module-paths during development and is then missing from the packaged
# extension, which is a nasty way to find out.
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  SphereAnnotationLib/__init__.py
  SphereAnnotationLib/export.py
  SphereAnnotationLib/mesh.py
  SphereAnnotationLib/rendering.py
  SphereAnnotationLib/spheres.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/${MODULE_NAME}.png
  Resources/UI/${MODULE_NAME}.ui
  )

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)

  # Register the unittest subclass in the main script as a ctest.
  # Note that the test will also be available at runtime.
  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)

  # Additional build-time testing
  add_subdirectory(Testing)
endif()
