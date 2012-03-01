TODO
- Instructions for downloading a dataset
- Run tests
- Run the experiment (experiments/make_output.py)
- Run the output comparison (experiments/exp_gterr.py)
- Generate the report (makewww/make_grid)

This is the open-source project that goes along with the IEEE VR2012 paper "Interactive Model Acquisition and Tracking for Building Block Structures".


Building
========
The blockplayer project is intended to be run from a command line in the current working directory. The following command builds the necessary cython files in place:

    python setup.py build_ext --inplace

It is also possible to build the normal way and install it as a library:

    python setup.py install


Running the experiment
=======================
To run our experiment, you will need to download (at least some of) the dataset. The dataset is available as a list of <code>tar.gz</code> files 


Running in live real-time mode
==============================
The system will first need to be calibrated. Place the Kinect sensor on a stand about a half meter above the table surface, facing down at around 45 degrees. Check that your desired work area is within the field of view of the camera. The minimum distance the sensor perceives is about half a meter. From the IPython shell, use the following commands.

        [1] from blockplayer.table_calibration import run_calib
        [2] run_calib()

The system will take a snapshot of the table surface, which should be clear of any objects. Click four points (clockwise) to define a quadrilateral work area. Calibration results are saved in <code>data/newest_calibration</code>. Next, run the demo with the following commands:

        [3] run -i demos/demo_grid.py
        [4] go(forreal=True)


Dependencies
============
Blockplayer has several library dependencies that may be difficult to satisfy on your system. The script <code>vmdist/install_vm.sh</code> is the best reference for how to set it up. In some cases the script refers to the most recent version of a project, therefore the script may not be 'future-proofed'. The virtual machine image available at http://isue-server.eecs.ucf.edu/amillervr2012/ is preinstalled with a working combination of all dependencies.





Reproducibility Kit
=================================

In addition to a source code distribution, BlockPlayer comes with a VirtualBox machine image (*.vdi) which has all necessary dependencies pre-installed. The machine image has been tested with VirtualBox OSE. The scripts in the <code>vmdist</code> directory do most of the work, but some undocumented manual configuration is needed to build the virtual machine image.



Running BlockPlayer on a headless machine
=========================================

To run the experiment and display the results on a headless machine, you should start an X virtual server with

    Xvfb

If a graphics card isn't available, then you should specify the mesa (rather than nvidia) OpenGL drivers.

    LD_PRELOAD=/usr/lib/mesa/libGL.so xvfb-run bash