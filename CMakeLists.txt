cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

# The extension is named after its one module, so that the name in the Extensions Manager,
# the name in Slicer's module list and the name in this tree are the same word. The subject
# it is aimed at lives in EXTENSION_CATEGORY below, not in the name — the module works on any
# ball-shaped object.
project(SphereAnnotation)

#-----------------------------------------------------------------------------
# Extension meta-information
#
# This is what the Extensions Manager shows. The three URLs are fetched by whoever is
# browsing it, so they must be publicly reachable: they resolve only once
# github.com/youssefassis/slicer-weak-annotation is public, and they have to be re-pointed
# if that repository is ever renamed or moved. Nothing here is validated at build time — a
# dead URL shows up as a missing image in the Manager, not as a CMake error.
set(EXTENSION_HOMEPAGE "https://github.com/youssefassis/slicer-weak-annotation")
set(EXTENSION_CATEGORY "Aneurysms")
set(EXTENSION_CONTRIBUTORS "Youssef Assis (Loria lab.)")
set(EXTENSION_DESCRIPTION "Annotate aneurysms — or any ball-shaped object — with spheres. Placing two points at opposite ends of a diameter defines one sphere, which then follows either point as it is dragged, giving a location and a size without segmenting anything.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/youssefassis/slicer-weak-annotation/main/docs/extension-icon.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/youssefassis/slicer-weak-annotation/main/docs/module-panel.jpg")
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
