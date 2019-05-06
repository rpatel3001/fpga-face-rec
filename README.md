# **F**PGA **A**ccelerated **C**ontrolled **E**ntry **S**ystem

This project was completed as my senior design project at Rutgers University for my degree in Electrical & Computer Engineering. 

A database table was created containing the name and access level of each authorized individual (in this case my group members). 
An OpenCV recognition model was trained using a set of images for each person and its state saved as a binary file to be loaded at runtime. 
I utilized OpenCV to perform facial detection followed by facial recognition on a video stream provided by a USB webcam. 
When a known face is recognized and has the appropriate access level, a pulse is sent to an electronic latch, opening a lockbox. 
All faces detected are logged in a database table containing a timestamp, the person's name if recognized, whether or not they were allowed access, and a filesystem path to a captured image of their face. 

Once the base system was working, it was profiled using the Python cProfile module and the Linux `perf` tool to find hotspots. 
The major hotspot was identified, unsurprisingly, as the OpenCV `detectMultiScale()` function responsible for detecting faces in a frame. 
After digging in the OpenCV source code, I deemed it too complex to accelerate this particular portion of code within the requisite timeframe.
This is due to its utilization of Intel Threading Building Blocks, which allows for simple parallelization of for loops with a certain structure.
The next highest time utilization, though significantly less than `detectMultiScale()` was by the `resize()` and `cvtColor()` functions performed prior to processing an image. 
These were much simpler functions and so suitable as a first try for FPGA acceleration. 

In order to implement custom IP, it must be integrated into the Vivado block diagram.
I obtained the source files for the PYNQ base overlay and ensured that I could build it on my machine. 
After doing so, I modified it to make manipulating the provided external GPIO pins easier, removed unneccesary portions, and ensured that the modified overlay still functioned properly. 
To accelerate the `resize()` and `cvtColor()` functions, I built custom IP in Vivado HLS based on the HLS Video Library provided by Xilinx. This library provides many functions analogous to OpenCV functions written entirely as synthesizable and pipelineable C++ code. 
Integrating the resulting IP into the overlay block diagram and modifying some Python code allowed access to the IP in Python using the PYNQ libraries. 

Using the IP proved the most difficult part of the project. In the end, I was able to resize images in the logic fabric. Converting the colorspace did not work either in isolation or before/after the resize operation. 
When trying to use any IP using the HLS `cvtColor()` analog the DMA stream for receiving data back from the IP never returned to the idle state. 
My best guess before the project ended was that the AXI stream was never indicating the end of a frame despite trying many permutations of AXI and DMA settings. 

As it stands, the Python code offloads only the resizing operation to the FPGA. because it is such a simple operation, the DMA transfer overhead is too high to see any gains in performance. In fact, the time to perform resizing in Python and the overall time to perform resizing in the FPGA plus the time sent streaming data was equal to the precision of the cProfile module. 
Implementing any further operations in the custom IP would have started to see immediate performance gains. 
The inherent parallelism of the OpenCV `detectMultiScale()` implementation would likely lend itself to straightforward acceleration, but doing so would require a much deeper understanding of the internal implementation than time allowed. 

Additionally, the accuracy of the facial detection and recognition is lacking due to the limited amount of time spent tuning them.
In particular, the detection routine has several parameters which can be tuned to reduce false negatives, and the recognition model could use more samples to refine the training and reduce both false negatives and false positives.
