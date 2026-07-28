cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

# The extension is named after its one module, so that the name in the Extensions Manager,
# the name in Slicer's module list and the name in this tree are the same word. The subject
# it is aimed at lives in EXTENSION_CATEGORY below, not in the name — the module works on any
# ball-shaped object.
project(SphereAnnotation)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/AneurysmAnnotation")
set(EXTENSION_CATEGORY "Aneurysms")
set(EXTENSION_CONTRIBUTORS "John Doe (AnyWare Corp.)")
set(EXTENSION_DESCRIPTION "This is an example of a simple extension")
set(EXTENSION_ICONURL "https://www.example.com/Slicer/Extensions/AneurysmAnnotation.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/AneurysmAnnotation/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(SphereAnnotation)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
