# Aneurysm Annotation Module
The Aneurysm Annotation Module is a Slicer 3D extension that simplifies the process of annotating aneurysms (or any ball-shaped objects) using spheres in a 3D view. This module provides an intuitive interface that makes it easy for users to annotate aneurysms and save their annotations as Fcsv file.

# Main Module View
<img width=100% src="Images/sample.gif" alt="Main module view">

# Getting Started
## Prerequisites
-  [3D Slicer](https://download.slicer.org/) version 4.11 or later

> The module is developed and tested against **Slicer 5.12.3**, and now calls Slicer 5 API
> (`slicer.util.loadMarkups`, `SetVisibility2D`), so the 4.11 floor above is almost certainly
> no longer accurate. Which version the project commits to supporting is listed as an open
> decision in [`docs/development.md`](docs/development.md).

## Installation
To use this  Annotation module, you will need to have 3D Slicer version 4.11 or later installed on your machine. You can download the latest version of 3D Slicer from the [official website](https://download.slicer.org/).

To install this Aneurysm Annotation module, follow these steps:


1. Download the module from the official repository:
    ```
    git clone https://gitlab.inria.fr/yassis/slicer-sphere-annotation.git
    ```
2. Open 3D Slicer.
3. Go to the Application Settings (in the "Edit" menu).
4. Go to the "Module" tab.
5. Add the module path in the "Additional module paths".
6. Press OK. Slicer will need to be restarted.

## Usage
To use the Aneurysm Annotation module, follow these steps:

- Open the Aneurysm Annotation module from the Extension Manager (under the "View" menu) by searching for "Aneurysm Annotation".
- Load the volume into Slicer. The volume will automatically appear in the 3D view. You can adjust its visibility, thresholding, and opacity.
- Load, create, or delete the points/markups (F1, F2, etc.) that define the spheres.
- The spheres will automatically be drawn in the 3D view. Each pair of points defines a sphere. The size and position of the spheres can be easily adjusted by modifying the position of the points from the 3D view ou from the 2D canonical cut planes.
- Adjust the size, position, and color of the sphere as needed.
- After annotating, save the annotation using the "Save" button. The annotaions (i.e. fiducial points) can be saved as FCSV file.
- To load a previously saved annotation, click the "Load" button and select the annotation file.

## Features
The Slicer Aneurysm Annotation Module includes the following features:
- Intuitive user interface for easy annotation of aneurysms.
- Ability to adjust the size, position, and color of spheres to highlight the location of the aneurysm.
- Ability to save and load annotations for later use.
- Ability to compare multiple annotations at the same time.

## Documentation

Everything is under [`docs/`](docs/README.md), which starts with an orientation page and the
constraints worth knowing before changing anything.

| | |
| --- | --- |
| [user guide](docs/user-guide.md) | what every control does, in the annotator's terms |
| [annotation format](docs/annotation-format.md) | the point-pairing contract — read this if you consume the files |
| [architecture](docs/architecture.md) | how the code is split, node ownership, the sphere maths |
| [development](docs/development.md) | the two Python environments, test loop, open decisions |

## Develop

The sphere maths and the display maths live in `SphereAnnotation/SphereAnnotationLib/`, which
is kept free of `slicer`/`vtk`/`qt`/`ctk` so it can be tested without launching Slicer:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest     # 39 tests, well under a second
ruff check .         # lint, and the import boundary above
```

Both checks run on every push, on GitHub and GitLab alike. Anything touching widgets or MRML
nodes needs Slicer — see [`docs/development.md`](docs/development.md).

## Citation
If you find this repository useful for your work, please consider citing our paper: 
```
Assis et al. Aneurysm Pose Estimation with Deep Learning, In: International Conference on Medical Image Computing and Computer-Assisted Intervention, Springer (2023)

```

## Contact
If you have any questions or feedback about this module, please contact me by email (youssef.assis@loria.fr).

## License
This project is licensed under the MIT License. This license allows for free use, modification, and distribution of the code, as long as the original license and copyright notice are included in any copies or derivatives.

For more information, see the [LICENSE](LICENSE.md) file.



