'''<b>Save Images </b> saves image or movie files.
<hr>
This version has been extended by VZ to save proper CXY images that are
correctly read by Ilastik.
Because CellProfiler usually performs many image analysis steps on many
groups of images, it does <i>not</i> save any of the resulting images to the
hard drive unless you specifically choose to do so with the <b>SaveImages</b>
module. You can save any of the
processed images created by CellProfiler during the analysis using this module.

<p>You can choose from many different image formats for saving your files. This
allows you to use the module as a file format converter, by loading files
in their original format and then saving them in an alternate format.</p>

<p>Note that saving images in 12-bit format is not supported, and 16-bit format
is supported for TIFF only.</p>

See also <b>NamesAndTypes</b>, <b>ConserveMemory</b>.
'''

import logging
import os
import re
import sys
import traceback

import matplotlib
import numpy as np
import scipy.io.matlab.mio

logger = logging.getLogger(__name__)

import cellprofiler.cpmodule as cpm
import cellprofiler.measurements as cpmeas
import cellprofiler.settings as cps
from cellprofiler.settings import YES, NO
import cellprofiler.preferences as cpp
from cellprofiler.gui.help import USING_METADATA_TAGS_REF, USING_METADATA_HELP_REF
from cellprofiler.preferences import \
     standardize_default_folder_names, DEFAULT_INPUT_FOLDER_NAME, \
     DEFAULT_OUTPUT_FOLDER_NAME, ABSOLUTE_FOLDER_NAME, \
     DEFAULT_INPUT_SUBFOLDER_NAME, DEFAULT_OUTPUT_SUBFOLDER_NAME, \
     IO_FOLDER_CHOICE_HELP_TEXT, IO_WITH_METADATA_HELP_TEXT, \
     get_default_image_directory
from cellprofiler.utilities.relpath import relpath
from cellprofiler.modules.loadimages import C_FILE_NAME, C_PATH_NAME, C_URL
from cellprofiler.modules.loadimages import \
     C_OBJECTS_FILE_NAME, C_OBJECTS_PATH_NAME, C_OBJECTS_URL
from cellprofiler.modules.loadimages import pathname2url
from centrosome.cpmorphology import distance_color_labels
from cellprofiler.utilities.version import get_version
from bioformats.formatwriter import write_image
import bioformats.omexml as ome

import h5py

IF_IMAGE       = "Image"
IF_MASK        = "Mask"
IF_CROPPING    = "Cropping"
IF_FIGURE      = "Module window"
IF_MOVIE       = "Movie"
IF_OBJECTS     = "Objects"
IF_ALL = [IF_IMAGE, IF_MASK, IF_CROPPING, IF_MOVIE, IF_OBJECTS]

OLD_BIT_DEPTH_8 = "8"
OLD_BIT_DEPTH_16 = "16"
BIT_DEPTH_8 = "8-bit integer"
BIT_DEPTH_16 = "16-bit integer"
BIT_DEPTH_FLOAT = "32-bit floating point"
BIT_DEPTH_32 = '32-bit integer'

FN_FROM_IMAGE  = "From image filename"
FN_SEQUENTIAL  = "Sequential numbers"
FN_SINGLE_NAME = "Single name"
SINGLE_NAME_TEXT = "Enter single file name"
FN_WITH_METADATA = "Name with metadata"
FN_IMAGE_FILENAME_WITH_METADATA = "Image filename with metadata"
METADATA_NAME_TEXT = ("""Enter file name with metadata""")
SEQUENTIAL_NUMBER_TEXT = "Enter file prefix"
FF_BMP         = "bmp"
FF_JPG         = "jpg"
FF_JPEG        = "jpeg"
FF_PBM         = "pbm"
FF_PCX         = "pcx"
FF_PGM         = "pgm"
FF_PNG         = "png"
FF_PNM         = "pnm"
FF_PPM         = "ppm"
FF_RAS         = "ras"
FF_TIF         = "tif"
FF_TIFF        = "tiff"
FF_XWD         = "xwd"
FF_AVI         = "avi"
FF_MAT         = "mat"
FF_MOV         = "mov"
FF_H5          = "h5"
FF_SUPPORTING_16_BIT = [FF_TIF, FF_TIFF, FF_H5]
PC_WITH_IMAGE  = "Same folder as image"
OLD_PC_WITH_IMAGE_VALUES = ["Same folder as image"]
PC_CUSTOM      = "Custom"
PC_WITH_METADATA = "Custom with metadata"
WS_EVERY_CYCLE = "Every cycle"
WS_FIRST_CYCLE = "First cycle"
WS_LAST_CYCLE  = "Last cycle"
CM_GRAY        = "gray"

GC_GRAYSCALE = "Grayscale"
GC_COLOR = "Color"

'''Offset to the directory path setting'''
OFFSET_DIRECTORY_PATH = 11

'''Offset to the bit depth setting in version 11'''
OFFSET_BIT_DEPTH_V11 = 12

H5_YXC_AXISTAG = '''{\n  "axes": [\n    {\n      "key": "y",\n      "typeFlags": 2,\n
"resolution": 0,\n      "description": ""\n    },\n    {\n
"key": "x",\n      "typeFlags": 2,\n      "resolution": 0,\n
"description": ""\n    },\n    {\n      "key": "c",\n
"typeFlags": 1,\n      "resolution": 0,\n
"description": ""\n    }\n  ]\n}'''

class SaveImagesH5(cpm.CPModule):
    module_name = "SaveImages H5"
    variable_revision_number = 1
    category = "File Processing"

    def create_settings(self):
        self.save_image_or_figure = cps.Choice(
            "Select the type of image to save",
            IF_ALL,
            IF_IMAGE, doc="""
            The following types of images can be saved as a file on the hard drive:
            <ul>
            <li><i>%(IF_IMAGE)s:</i> Any of the images produced upstream of <b>SaveImages</b> can be selected for saving.
            Outlines created by <b>Identify</b> modules can also be saved with this option, but you must
            select "Retain outlines..." of identified objects within the <b>Identify</b> module. You might
            also want to use the <b>OverlayOutlines</b> module prior to saving images.</li>
            <li><i>%(IF_MASK)s:</i> Relevant only if the <b>Crop</b> module is used. The <b>Crop</b> module
            creates a mask of the pixels of interest in the image. Saving the mask will produce a
            binary image in which the pixels of interest are set to 1; all other pixels are
            set to 0.</li>
            <li><i>%(IF_CROPPING)s:</i> Relevant only if the <b>Crop</b> module is used. The <b>Crop</b>
            module also creates a cropping image which is typically the same size as the original
            image. However, since the <b>Crop</b> permits removal of the rows and columns that are left
            blank, the cropping can be of a different size than the mask.</li>
            <li><i>%(IF_MOVIE)s:</i> A sequence of images can be saved as a movie file. Currently only AVIs can be written.
            Each image becomes a frame of the movie.</li>
            <li><i>%(IF_OBJECTS)s:</i> Objects can be saved as an image. The image
            is saved as grayscale unless you select a color map other than
            gray. Background pixels appear as black and
            each object is assigned an intensity level corresponding to
            its object number. The resulting image can be loaded as objects
            by the <b>NamesAndTypes</b> module. Objects are best saved as TIF
            files. <b>SaveImages</b> will use an 8-bit TIF file if there
            are fewer than 256 objects and will use a 16-bit TIF otherwise.
            Results may be unpredictable if you save using PNG and there
            are more than 255 objects or if you save using one of the other
            file formats.</li>
            </ul>"""%globals())

        self.image_name  = cps.ImageNameSubscriber(
            "Select the image to save",cps.NONE, doc = """
            <i>(Used only if "%(IF_IMAGE)s", "%(IF_MASK)s" or "%(IF_CROPPING)s" are selected to save)</i><br>
            Select the image you want to save."""%globals())

        self.objects_name = cps.ObjectNameSubscriber(
            "Select the objects to save", cps.NONE,doc = """
            <i>(Used only if saving "%(IF_OBJECTS)s")</i><br>
            Select the objects that you want to save."""%globals())

        self.figure_name = cps.FigureSubscriber(
            "Select the module display window to save",cps.NONE,doc="""
            <i>(Used only if saving "%(IF_FIGURE)s")</i><br>
            Enter the module number/name for which you want to
            save the module display window."""%globals())

        self.file_name_method = cps.Choice(
            "Select method for constructing file names",
            [FN_FROM_IMAGE, FN_SEQUENTIAL,
             FN_SINGLE_NAME],
             FN_FROM_IMAGE,doc="""
            <i>(Used only if saving non-movie files)</i><br>
            Several choices are available for constructing the image file name:
            <ul>
            <li><i>%(FN_FROM_IMAGE)s:</i> The filename will be constructed based
            on the original filename of an input image specified in <b>NamesAndTypes</b>.
            You will have the opportunity to prefix or append
            additional text.
            <p>If you have metadata associated with your images, you can append an text
            to the image filename using a metadata tag. This is especially useful if you
            want your output given a unique label according to the metadata corresponding
            to an image group. The name of the metadata to substitute can be provided for
            each image for each cycle using the <b>Metadata</b> module.
            %(USING_METADATA_TAGS_REF)s%(USING_METADATA_HELP_REF)s.</p></li>
            <li><i>%(FN_SEQUENTIAL)s:</i> Same as above, but in addition, each filename
            will have a number appended to the end that corresponds to
            the image cycle number (starting at 1).</li>
            <li><i>%(FN_SINGLE_NAME)s:</i> A single name will be given to the
            file. Since the filename is fixed, this file will be overwritten with each cycle.
            In this case, you would probably want to save the image on the last cycle
            (see the <i>Select how often to save</i> setting). The exception to this is to
            use a metadata tag to provide a unique label, as mentioned
            in the <i>%(FN_FROM_IMAGE)s</i> option.</li>
            </ul>"""%globals())

        self.file_image_name = cps.FileImageNameSubscriber(
            "Select image name for file prefix",
            cps.NONE,doc="""
            <i>(Used only when "%(FN_FROM_IMAGE)s" is selected for contructing the filename)</i><br>
            Select an image loaded using <b>NamesAndTypes</b>. The original filename will be
            used as the prefix for the output filename."""%globals())

        self.single_file_name = cps.Text(
            SINGLE_NAME_TEXT, "OrigBlue",
            metadata = True,  doc="""
            <i>(Used only when "%(FN_SEQUENTIAL)s" or "%(FN_SINGLE_NAME)s" are selected for contructing the filename)</i><br>
            Specify the filename text here. If you have metadata
            associated with your images, enter the filename text with the metadata tags. %(USING_METADATA_TAGS_REF)s<br>
            Do not enter the file extension in this setting; it will be appended automatically."""%globals())

        self.number_of_digits = cps.Integer(
            "Number of digits", 4, doc="""
            <i>(Used only when "%(FN_SEQUENTIAL)s" is selected for contructing the filename)</i><br>
            Specify the number of digits to be used for the sequential numbering. Zeros will be
            used to left-pad the digits. If the number specified here is less than that needed to
            contain the number of image sets, the latter will override the value entered."""%globals())

        self.wants_file_name_suffix = cps.Binary(
            "Append a suffix to the image file name?", False, doc = """
            Select <i>%(YES)s</i> to add a suffix to the image's file name.
            Select <i>%(NO)s</i> to use the image name as-is."""%globals())

        self.file_name_suffix = cps.Text(
            "Text to append to the image name",
            "", metadata = True, doc="""
            <i>(Used only when constructing the filename from the image filename)</i><br>
            Enter the text that should be appended to the filename specified above.""")

        self.file_format = cps.Choice(
            "Saved file format",
            [FF_H5],
            value = FF_TIFF, doc="""
            <i>(Used only when saving non-movie files)</i><br>
            Select the image or movie format to save the image(s). Most common
            image formats are available; MAT-files are readable by MATLAB.""")

        self.movie_format = cps.Choice(
            "Saved movie format",
            [FF_AVI, FF_TIF, FF_MOV],
            value = FF_AVI, doc="""
            <i>(Used only when saving movie files)</i><br>
            Select the movie format to use when saving movies. AVI and MOV
            store images from successive image sets as movie frames. TIF
            stores each image as an image plane in a TIF stack.
            """)

        self.pathname = SaveImagesDirectoryPath(
            "Output file location", self.file_image_name,doc = """
            <i>(Used only when saving non-movie files)</i><br>
            This setting lets you choose the folder for the output
            files. %(IO_FOLDER_CHOICE_HELP_TEXT)s
            <p>An additional option is the following:
            <ul>
            <li><i>Same folder as image</i>: Place the output file in the same folder
            that the source image is located.</li>
            </ul></p>
            <p>%(IO_WITH_METADATA_HELP_TEXT)s %(USING_METADATA_TAGS_REF)s.
            For instance, if you have a metadata tag named
            "Plate", you can create a per-plate folder by selecting one the subfolder options
            and then specifying the subfolder name as "\g&lt;Plate&gt;". The module will
            substitute the metadata values for the current image set for any metadata tags in the
            folder name.%(USING_METADATA_HELP_REF)s.</p>
            <p>If the subfolder does not exist when the pipeline is run, CellProfiler will
            create it.</p>
            <p>If you are creating nested subfolders using the sub-folder options, you can
            specify the additional folders separated with slashes. For example, "Outlines/Plate1" will create
            a "Plate1" folder in the "Outlines" folder, which in turn is under the Default
            Input/Output Folder. The use of a forward slash ("/") as a folder separator will
            avoid ambiguity between the various operating systems.</p>"""%globals())

        # TODO:
        self.bit_depth = cps.Choice(
            "Image bit depth",
            [BIT_DEPTH_8, BIT_DEPTH_16, BIT_DEPTH_FLOAT, BIT_DEPTH_32],doc="""
            <i>(Used only when saving files in a non-MAT format)</i><br>
            Select the bit-depth at which you want to save the images.
            <i>%(BIT_DEPTH_FLOAT)s</i> saves the image as floating-point decimals
            with 32-bit precision in its raw form, typically scaled between
            0 and 1.
            <b>%(BIT_DEPTH_16)s and %(BIT_DEPTH_FLOAT)s images are supported only
            for TIF formats. Currently, saving images in 12-bit is not supported.</b>""" %
            globals())

        self.overwrite = cps.Binary(
            "Overwrite existing files without warning?",False,doc="""
            Select <i>%(YES)s</i> to automatically overwrite a file if it already exists.
            Select <i>%(NO)s</i> to be prompted for confirmation first.
            <p>If you are running the pipeline on a computing cluster,
            select <i>%(YES)s</i> since you will not be able to intervene and answer the confirmation prompt.</p>"""%globals())

        self.when_to_save = cps.Choice(
            "When to save",
            [WS_EVERY_CYCLE,WS_FIRST_CYCLE,WS_LAST_CYCLE],
            WS_EVERY_CYCLE, doc="""<a name='when_to_save'>
            <i>(Used only when saving non-movie files)</i><br>
            Specify at what point during pipeline execution to save file(s). </a>
            <ul>
            <li><i>%(WS_EVERY_CYCLE)s:</i> Useful for when the image of interest is created every cycle and is
            not dependent on results from a prior cycle.</li>
            <li><i>%(WS_FIRST_CYCLE)s:</i> Useful for when you are saving an aggregate image created
            on the first cycle, e.g., <b>CorrectIlluminationCalculate</b> with the <i>All</i>
            setting used on images obtained directly from <b>NamesAndTypes</b>.</li>
            <li><i>%(WS_LAST_CYCLE)s</i> Useful for when you are saving an aggregate image completed
            on the last cycle, e.g., <b>CorrectIlluminationCalculate</b> with the <i>All</i>
            setting used on intermediate images generated during each cycle.</li>
            </ul> """%globals())

        self.rescale = cps.Binary(
            "Rescale the images? ",False,doc="""
            <i>(Used only when saving non-MAT file images)</i><br>
            Select <i>%(YES)s</i> if you want the image to occupy the full dynamic range of the bit
            depth you have chosen. For example, if you save an image to an 8-bit file, the
            smallest grayscale value will be mapped to 0 and the largest value will be mapped
            to 2<sup>8</sup>-1 = 255.
            <p>This will increase the contrast of the output image but will also effectively
            stretch the image data, which may not be desirable in some
            circumstances. See <b>RescaleIntensity</b> for other rescaling options.</p>"""%globals())

        self.gray_or_color = cps.Choice(
            "Save as grayscale or color image?",
            [GC_GRAYSCALE, GC_COLOR],doc = """
            <i>(Used only when saving "%(IF_OBJECTS)s")</i><br>
            You can save objects as a grayscale image or as a color image.
            <ul>
            <li><i>%(GC_GRAYSCALE)s: </i> Use the pixel's object number
            (label) for the grayscale intensity. Background pixels are
            colored black. Grayscale images are more
            suitable if you are going to load the image as objects using
            <b>NamesAndTypes</b> or some other program that will be used to
            relate object measurements to the pixels in the image.
            You should save grayscale images using the .TIF or .MAT formats
            if possible; otherwise you may have problems saving files
            with more than 255 objects.</li>
            <li><i>%(GC_COLOR)s:</i> Assigns different colors to different
            objects.</li>
            </ul>"""%globals())

        self.colormap = cps.Colormap(
            'Select colormap',
            value = CM_GRAY,doc= """
            <i>(Used only when saving non-MAT file images)</i><br>
            This affects how images color intensities are displayed. All available colormaps can be seen
            <a href="http://www.scipy.org/Cookbook/Matplotlib/Show_colormaps">here</a>.""")

        self.update_file_names = cps.Binary(
            "Record the file and path information to the saved image?",False,doc="""
            Select <i>%(YES)s</i> to store filename and pathname data for each of the new files created
            via this module as a per-image measurement.
            <p>Instances in which this information may be useful include:
            <ul>
            <li>Exporting measurements to a database, allowing
            access to the saved image. If you are using the machine-learning tools or image
            viewer in CellProfiler Analyst, for example, you will want to enable this setting if you want
            the saved images to be displayed along with the original images.</li>
            <li>Allowing downstream modules (e.g., <b>CreateWebPage</b>) to access
            the newly saved files.</li>
            </ul></p>"""%globals())

        self.create_subdirectories = cps.Binary(
            "Create subfolders in the output folder?",False,doc = """
            Select <i>%(YES)s</i> to create subfolders to match the input image folder structure."""%globals())

        self.root_dir = cps.DirectoryPath(
            "Base image folder", doc = """
            <i>Used only if creating subfolders in the output folder</i>
            In subfolder mode, <b>SaveImages</b> determines the folder for
            an image file by examining the path of the matching input file.
            The path that SaveImages uses is relative to the image folder
            chosen using this setting. As an example, input images might be stored
            in a folder structure of "images%(sep)s<i>experiment-name</i>%(sep)s
            <i>date</i>%(sep)s<i>plate-name</i>". If the image folder is
            "images", <b>SaveImages</b> will store images in the subfolder,
            "<i>experiment-name</i>%(sep)s<i>date</i>%(sep)s<i>plate-name</i>".
            If the image folder is "images%(sep)s<i>experiment-name</i>",
            <b>SaveImages</b> will store images in the subfolder,
            <i>date</i>%(sep)s<i>plate-name</i>".
            """ % dict(sep=os.path.sep))

    def settings(self):
        """Return the settings in the order to use when saving"""
        return [self.save_image_or_figure, self.image_name,
                self.objects_name, self.figure_name,
                self.file_name_method, self.file_image_name,
                self.single_file_name, self.number_of_digits,
                self.wants_file_name_suffix,
                self.file_name_suffix, self.file_format,
                self.pathname, self.bit_depth,
                self.overwrite, self.when_to_save,
                self.rescale, self.gray_or_color, self.colormap,
                self.update_file_names, self.create_subdirectories,
                self.root_dir, self.movie_format]

    def visible_settings(self):
        """Return only the settings that should be shown"""
        result = [self.save_image_or_figure]
        if self.save_image_or_figure == IF_FIGURE:
            result.append(self.figure_name)
        elif self.save_image_or_figure == IF_OBJECTS:
            result.append(self.objects_name)
        else:
            result.append(self.image_name)

        result.append(self.file_name_method)
        if self.file_name_method == FN_FROM_IMAGE:
            result += [self.file_image_name, self.wants_file_name_suffix]
            if self.wants_file_name_suffix:
                result.append(self.file_name_suffix)
        elif self.file_name_method == FN_SEQUENTIAL:
            self.single_file_name.text = SEQUENTIAL_NUMBER_TEXT
            # XXX - Change doc, as well!
            result.append(self.single_file_name)
            result.append(self.number_of_digits)
        elif self.file_name_method == FN_SINGLE_NAME:
            self.single_file_name.text = SINGLE_NAME_TEXT
            result.append(self.single_file_name)
        else:
            raise NotImplementedError("Unhandled file name method: %s"%(self.file_name_method))
        if self.save_image_or_figure == IF_MOVIE:
            result.append(self.movie_format)
        else:
            result.append(self.file_format)
        supports_16_bit = (self.file_format in FF_SUPPORTING_16_BIT and
                           self.save_image_or_figure == IF_IMAGE)
        if supports_16_bit:
            # TIFF supports 8 & 16-bit, all others are written 8-bit
            result.append(self.bit_depth)
        result.append(self.pathname)
        result.append(self.overwrite)
        if self.save_image_or_figure != IF_MOVIE:
            result.append(self.when_to_save)
        if (self.save_image_or_figure == IF_IMAGE and
            self.file_format != FF_MAT):
            result.append(self.rescale)
            if self.get_bit_depth() == "8":
                result.append(self.colormap)
        elif self.save_image_or_figure == IF_OBJECTS:
            result.append(self.gray_or_color)
            if self.gray_or_color == GC_COLOR:
                result.append(self.colormap)
        result.append(self.update_file_names)
        if self.file_name_method == FN_FROM_IMAGE:
            result.append(self.create_subdirectories)
            if self.create_subdirectories:
                result.append(self.root_dir)
        return result

    @property
    def module_key(self):
        return "%s_%d"%(self.module_name, self.module_num)

    def prepare_group(self, workspace, grouping, image_numbers):
        d = self.get_dictionary(workspace.image_set_list)
        if self.save_image_or_figure == IF_MOVIE:
            d['N_FRAMES'] = len(image_numbers)
            d['CURRENT_FRAME'] = 0
        return True

    def prepare_to_create_batch(self, workspace, fn_alter_path):
        self.pathname.alter_for_create_batch_files(fn_alter_path)
        if self.create_subdirectories:
            self.root_dir.alter_for_create_batch_files(fn_alter_path)

    def run(self,workspace):
        """Run the module

        pipeline     - instance of CellProfiler.Pipeline for this run
        workspace    - the workspace contains:
            image_set    - the images in the image set being processed
            object_set   - the objects (labeled masks) in this image set
            measurements - the measurements for this run
            frame        - display within this frame (or None to not display)
        """
        if self.save_image_or_figure.value in (IF_IMAGE, IF_MASK, IF_CROPPING):
            should_save = self.run_image(workspace)
        elif self.save_image_or_figure == IF_MOVIE:
            should_save = self.run_movie(workspace)
        elif self.save_image_or_figure == IF_OBJECTS:
            should_save = self.run_objects(workspace)
        else:
            raise NotImplementedError(("Saving a %s is not yet supported"%
                                       (self.save_image_or_figure)))
        workspace.display_data.filename = self.get_filename(
            workspace, make_dirs = False, check_overwrite = False)

    def is_aggregation_module(self):
        '''SaveImages is an aggregation module when it writes movies'''
        return self.save_image_or_figure == IF_MOVIE or \
               self.when_to_save == WS_LAST_CYCLE

    def display(self, workspace, figure):
        if self.show_window:
            if self.save_image_or_figure == IF_MOVIE:
                return
            figure.set_subplots((1, 1))
            outcome = ("Wrote %s" if workspace.display_data.wrote_image
                       else "Did not write %s")
            figure.subplot_table(0, 0, [[outcome %
                                         (workspace.display_data.filename)]])


    def run_image(self,workspace):
        """Handle saving an image"""
        #
        # First, check to see if we should save this image
        #
        if self.when_to_save == WS_FIRST_CYCLE:
            d = self.get_dictionary(workspace.image_set_list)
            if workspace.measurements[cpmeas.IMAGE, cpmeas.GROUP_INDEX] > 1:
                workspace.display_data.wrote_image = False
                self.save_filename_measurements(workspace)
                return
            d["FIRST_IMAGE"] = False

        elif self.when_to_save == WS_LAST_CYCLE:
            workspace.display_data.wrote_image = False
            self.save_filename_measurements( workspace)
            return
        self.save_image(workspace)
        return True


    def run_movie(self, workspace):
        out_file = self.get_filename(workspace, check_overwrite=False)
        # overwrite checks are made only for first frame.
        d = self.get_dictionary(workspace.image_set_list)
        if d["CURRENT_FRAME"] == 0 and os.path.exists(out_file):
            if not self.check_overwrite(out_file, workspace):
                d["CURRENT_FRAME"] = "Ignore"
                return
            else:
                # Have to delete the old movie before making the new one
                os.remove(out_file)
        elif d["CURRENT_FRAME"] == "Ignore":
            return

        image = workspace.image_set.get_image(self.image_name.value)
        pixels = image.pixel_data
        pixels = pixels * 255
        frames = d['N_FRAMES']
        current_frame = d["CURRENT_FRAME"]
        d["CURRENT_FRAME"] += 1
        self.do_save_image(workspace, out_file, pixels, ome.PT_UINT8,
                           t = current_frame, size_t = frames)

    def run_objects(self, workspace):
        #
        # First, check to see if we should save this image
        #
        if self.when_to_save == WS_FIRST_CYCLE:
            if workspace.measurements[cpmeas.IMAGE, cpmeas.GROUP_INDEX] > 1:
                workspace.display_data.wrote_image = False
                self.save_filename_measurements(workspace)
                return

        elif self.when_to_save == WS_LAST_CYCLE:
            workspace.display_data.wrote_image = False
            self.save_filename_measurements( workspace)
            return
        self.save_objects(workspace)

    def save_objects(self, workspace):
        objects_name = self.objects_name.value
        objects = workspace.object_set.get_objects(objects_name)
        filename = self.get_filename(workspace)
        if filename is None:  # failed overwrite check
            return

        labels = [l for l, c in objects.get_labels()]
        if self.get_file_format() == FF_MAT:
            pixels = objects.segmented
            scipy.io.matlab.mio.savemat(filename,{"Image":pixels},format='5')

        elif self.gray_or_color == GC_GRAYSCALE:
            if objects.count > 255:
                pixel_type = ome.PT_UINT32
            else:
                pixel_type = ome.PT_UINT8
            for i, l in enumerate(labels):
                self.do_save_image(
                    workspace, filename, l, pixel_type, t=i, size_t=len(labels))

        else:
            if self.colormap == cps.DEFAULT:
                colormap = cpp.get_default_colormap()
            else:
                colormap = self.colormap.value
            cm = matplotlib.cm.get_cmap(colormap)

            cpixels = np.zeros((labels[0].shape[0], labels[0].shape[1], 3))
            counts = np.zeros(labels[0].shape, int)
            mapper = matplotlib.cm.ScalarMappable(cmap=cm)
            for pixels in labels:
                cpixels[pixels != 0, :] += \
                    mapper.to_rgba(distance_color_labels(pixels),
                                   bytes=True)[pixels != 0, :3]
                counts[pixels != 0] += 1
            counts[counts == 0] = 1
            cpixels = cpixels / counts[:, :, np.newaxis]
            self.do_save_image(workspace, filename, cpixels, ome.PT_UINT8)
        self.save_filename_measurements(workspace)
        if self.show_window:
            workspace.display_data.wrote_image = True

    def post_group(self, workspace, *args):
        if (self.when_to_save == WS_LAST_CYCLE and
            self.save_image_or_figure != IF_MOVIE):
            if self.save_image_or_figure == IF_OBJECTS:
                self.save_objects(workspace)
            else:
                self.save_image(workspace)

    def do_save_image(self, workspace, filename, pixels, pixel_type,
                   c = 0, z = 0, t = 0,
                   size_c = 1, size_z = 1, size_t = 1,
                   channel_names = None):
        '''Save image using bioformats

        workspace - the current workspace

        filename - save to this filename

        pixels - the image to save

        pixel_type - save using this pixel type

        c - the image's channel index

        z - the image's z index

        t - the image's t index

        sizeC - # of channels in the stack

        sizeZ - # of z stacks

        sizeT - # of timepoints in the stack

        channel_names - names of the channels (make up names if not present
        '''
        write_image(filename, pixels, pixel_type,
                    c = c, z = z, t = t,
                    size_c = size_c, size_z = size_z, size_t = size_t,
                    channel_names = channel_names)

    def save_image(self, workspace):
        if self.show_window:
            workspace.display_data.wrote_image = False
        image = workspace.image_set.get_image(self.image_name.value)
        if self.save_image_or_figure == IF_IMAGE:
            pixels = image.pixel_data
            u16hack = (((self.get_bit_depth() == BIT_DEPTH_16) or (
                self.get_bit_depth() == BIT_DEPTH_32)) and
                       pixels.dtype.kind in ('u', 'i'))
            if self.file_format != FF_MAT:
                if self.rescale.value:
                    pixels = pixels.copy()
                    # Normalize intensities for each channel
                    if pixels.ndim == 3:
                        # RGB
                        for i in range(3):
                            img_min = np.min(pixels[:,:,i])
                            img_max = np.max(pixels[:,:,i])
                            if img_max > img_min:
                                pixels[:,:,i] = (pixels[:,:,i] - img_min) / (img_max - img_min)
                    else:
                        # Grayscale
                        img_min = np.min(pixels)
                        img_max = np.max(pixels)
                        if img_max > img_min:
                            pixels = (pixels - img_min) / (img_max - img_min)
                elif not (u16hack or self.get_bit_depth() == BIT_DEPTH_FLOAT):
                    # Clip at 0 and 1
                    if np.max(pixels) > 1 or np.min(pixels) < 0:
                        sys.stderr.write(
                            "Warning, clipping image %s before output. Some intensities are outside of range 0-1" %
                            self.image_name.value)
                        pixels = pixels.copy()
                        pixels[pixels < 0] = 0
                        pixels[pixels > 1] = 1

                if pixels.ndim == 2 and self.colormap != CM_GRAY and\
                   self.get_bit_depth() == BIT_DEPTH_8:
                    # Convert grayscale image to rgb for writing
                    if self.colormap == cps.DEFAULT:
                        colormap = cpp.get_default_colormap()
                    else:
                        colormap = self.colormap.value
                    cm = matplotlib.cm.get_cmap(colormap)

                    mapper = matplotlib.cm.ScalarMappable(cmap=cm)
                    pixels = mapper.to_rgba(pixels, bytes=True)
                    pixel_type = ome.PT_UINT8
                elif self.get_bit_depth() == BIT_DEPTH_8:
                    pixels = (pixels*255).astype(np.uint8)
                    pixel_type = ome.PT_UINT8
                elif self.get_bit_depth() == BIT_DEPTH_FLOAT:
                    pixel_type = ome.PT_FLOAT
                elif self.get_bit_depth() == BIT_DEPTH_32:
                    if not u16hack:
                        pixels = (pixels*(2**32-1))
                    pixel_type = ome.PT_UINT32
                else:
                    if not u16hack:
                        pixels = (pixels*65535)
                    pixel_type = ome.PT_UINT16

        elif self.save_image_or_figure == IF_MASK:
            pixels = image.mask.astype(np.uint8) * 255
            pixel_type = ome.PT_UINT8

        elif self.save_image_or_figure == IF_CROPPING:
            pixels = image.crop_mask.astype(np.uint8) * 255
            pixel_type = ome.PT_UINT8

        filename = self.get_filename(workspace)
        if filename is None:  # failed overwrite check
            return

        if self.get_file_format() == FF_MAT:
            scipy.io.matlab.mio.savemat(filename,{"Image":pixels},format='5')
        elif self.get_file_format() == FF_BMP:
            save_bmp(filename, pixels)

        elif self.get_file_format() == FF_H5:
            save_h5(filename, pixels, pixel_type)
        else:
            self.do_save_image(workspace, filename, pixels, pixel_type)
        if self.show_window:
            workspace.display_data.wrote_image = True
        if self.when_to_save != WS_LAST_CYCLE:
            self.save_filename_measurements(workspace)

    def check_overwrite(self, filename, workspace):
        '''Check to see if it's legal to overwrite a file

        Throws an exception if can't overwrite and no interaction available.
        Returns False if can't overwrite, otherwise True.
        '''
        if not self.overwrite.value and os.path.isfile(filename):
            try:
                return (workspace.interaction_request(self, workspace.measurements.image_set_number, filename) == "Yes")
            except workspace.NoInteractionException:
                raise ValueError('SaveImages: trying to overwrite %s in headless mode, but Overwrite files is set to "No"' % (filename))
        return True

    def handle_interaction(self, image_set_number, filename):
        '''handle an interaction request from check_overwrite()'''
        import wx
        dlg = wx.MessageDialog(wx.GetApp().TopWindow,
                               "%s #%d, set #%d - Do you want to overwrite %s?" % \
                                   (self.module_name, self.module_num, image_set_number, filename),
                               "Warning: overwriting file", wx.YES_NO | wx.ICON_QUESTION)
        result = dlg.ShowModal() == wx.ID_YES
        return "Yes" if result else "No"

    def save_filename_measurements(self, workspace):
        if self.update_file_names.value:
            filename = self.get_filename(workspace, make_dirs = False,
                                         check_overwrite = False)
            pn, fn = os.path.split(filename)
            url = pathname2url(filename)
            workspace.measurements.add_measurement(cpmeas.IMAGE,
                                                   self.file_name_feature,
                                                   fn,
                                                   can_overwrite=True)
            workspace.measurements.add_measurement(cpmeas.IMAGE,
                                                   self.path_name_feature,
                                                   pn,
                                                   can_overwrite=True)
            workspace.measurements.add_measurement(cpmeas.IMAGE,
                                                   self.url_feature,
                                                   url,
                                                   can_overwrite=True)

    @property
    def file_name_feature(self):
        '''The file name measurement for the output file'''
        if self.save_image_or_figure == IF_OBJECTS:
            return '_'.join((C_OBJECTS_FILE_NAME, self.objects_name.value))
        return '_'.join((C_FILE_NAME, self.image_name.value))

    @property
    def path_name_feature(self):
        '''The path name measurement for the output file'''
        if self.save_image_or_figure == IF_OBJECTS:
            return '_'.join((C_OBJECTS_PATH_NAME, self.objects_name.value))
        return '_'.join((C_PATH_NAME, self.image_name.value))

    @property
    def url_feature(self):
        '''The URL measurement for the output file'''
        if self.save_image_or_figure == IF_OBJECTS:
            return '_'.join((C_OBJECTS_URL, self.objects_name.value))
        return '_'.join((C_URL, self.image_name.value))

    @property
    def source_file_name_feature(self):
        '''The file name measurement for the exemplar disk image'''
        return '_'.join((C_FILE_NAME, self.file_image_name.value))

    def source_path(self, workspace):
        '''The path for the image data, or its first parent with a path'''
        if self.file_name_method.value == FN_FROM_IMAGE:
            path_feature = '%s_%s' % (C_PATH_NAME, self.file_image_name.value)
            assert workspace.measurements.has_feature(cpmeas.IMAGE, path_feature),\
                "Image %s does not have a path!" % (self.file_image_name.value)
            return workspace.measurements.get_current_image_measurement(path_feature)

        # ... otherwise, chase the cpimage hierarchy looking for an image with a path
        cur_image = workspace.image_set.get_image(self.image_name.value)
        while cur_image.path_name is None:
            cur_image = cur_image.parent_image
            assert cur_image is not None, "Could not determine source path for image %s' % (self.image_name.value)"
        return cur_image.path_name

    def get_measurement_columns(self, pipeline):
        if self.update_file_names.value:
            return [(cpmeas.IMAGE,
                     self.file_name_feature,
                     cpmeas.COLTYPE_VARCHAR_FILE_NAME),
                    (cpmeas.IMAGE,
                     self.path_name_feature,
                     cpmeas.COLTYPE_VARCHAR_PATH_NAME)]
        else:
            return []

    def get_filename(self, workspace, make_dirs=True, check_overwrite=True):
        "Concoct a filename for the current image based on the user settings"

        measurements=workspace.measurements
        if self.file_name_method == FN_SINGLE_NAME:
            filename = self.single_file_name.value
            filename = workspace.measurements.apply_metadata(filename)
        elif self.file_name_method == FN_SEQUENTIAL:
            filename = self.single_file_name.value
            filename = workspace.measurements.apply_metadata(filename)
            n_image_sets = workspace.measurements.image_set_count
            ndigits = int(np.ceil(np.log10(n_image_sets+1)))
            ndigits = max((ndigits,self.number_of_digits.value))
            padded_num_string = str(measurements.image_set_number).zfill(ndigits)
            filename = '%s%s'%(filename, padded_num_string)
        else:
            file_name_feature = self.source_file_name_feature
            filename = measurements.get_current_measurement('Image',
                                                            file_name_feature)
            filename = os.path.splitext(filename)[0]
            if self.wants_file_name_suffix:
                suffix = self.file_name_suffix.value
                suffix = workspace.measurements.apply_metadata(suffix)
                filename += suffix

        filename = "%s.%s"%(filename,self.get_file_format())
        pathname = self.pathname.get_absolute_path(measurements)
        if self.create_subdirectories:
            image_path = self.source_path(workspace)
            subdir = relpath(image_path, self.root_dir.get_absolute_path())
            pathname = os.path.join(pathname, subdir)
        if len(pathname) and not os.path.isdir(pathname) and make_dirs:
            try:
                os.makedirs(pathname)
            except:
                #
                # On cluster, this can fail if the path was created by
                # another process after this process found it did not exist.
                #
                if not os.path.isdir(pathname):
                    raise
        result = os.path.join(pathname, filename)
        if check_overwrite and not self.check_overwrite(result, workspace):
            return

        if check_overwrite and os.path.isfile(result):
            try:
                os.remove(result)
            except:
                import bioformats
                bioformats.clear_image_reader_cache()
                os.remove(result)
        return result

    def get_file_format(self):
        """Return the file format associated with the extension in self.file_format
        """
        if self.save_image_or_figure == IF_MOVIE:
            return self.movie_format.value
        return self.file_format.value

    def get_bit_depth(self):
        if (self.save_image_or_figure == IF_IMAGE and
            self.get_file_format() in FF_SUPPORTING_16_BIT):
            return self.bit_depth.value
        else:
            return BIT_DEPTH_8

    def upgrade_settings(self, setting_values, variable_revision_number,
                         module_name, from_matlab):
        """Adjust the setting values to be backwards-compatible with old versions

        """
        return setting_values, variable_revision_number, from_matlab

    def validate_module(self, pipeline):
        if (self.save_image_or_figure in (IF_IMAGE, IF_MASK, IF_CROPPING) and
            self.when_to_save in (WS_FIRST_CYCLE, WS_EVERY_CYCLE)):
            #
            # Make sure that the image name is available on every cycle
            #
            for setting in cps.get_name_providers(pipeline,
                                                  self.image_name):
                if setting.provided_attributes.get(cps.AVAILABLE_ON_LAST_ATTRIBUTE):
                    #
                    # If we fell through, then you can only save on the last cycle
                    #
                    raise cps.ValidationError("%s is only available after processing all images in an image group" %
                                              self.image_name.value,
                                              self.when_to_save)

        # XXX - should check that if file_name_method is
        # FN_FROM_IMAGE, that the named image actually has the
        # required path measurement

        # Make sure metadata tags exist
        if self.file_name_method == FN_SINGLE_NAME or \
                (self.file_name_method == FN_FROM_IMAGE and self.wants_file_name_suffix.value):
            text_str = self.single_file_name.value if self.file_name_method == FN_SINGLE_NAME else self.file_name_suffix.value
            undefined_tags = pipeline.get_undefined_metadata_tags(text_str)
            if len(undefined_tags) > 0:
                raise cps.ValidationError("%s is not a defined metadata tag. Check the metadata specifications in your load modules" %
                                     undefined_tags[0],
                                     self.single_file_name if self.file_name_method == FN_SINGLE_NAME else self.file_name_suffix)

class SaveImagesDirectoryPath(cps.DirectoryPath):
    '''A specialized version of DirectoryPath to handle saving in the image dir'''

    def __init__(self, text, file_image_name, doc):
        '''Constructor
        text - explanatory text to display
        file_image_name - the file_image_name setting so we can save in same dir
        doc - documentation for user
        '''
        super(SaveImagesDirectoryPath, self).__init__(
            text, dir_choices = [
                cps.DEFAULT_OUTPUT_FOLDER_NAME, cps.DEFAULT_INPUT_FOLDER_NAME,
                PC_WITH_IMAGE, cps.ABSOLUTE_FOLDER_NAME,
                cps.DEFAULT_OUTPUT_SUBFOLDER_NAME,
                cps.DEFAULT_INPUT_SUBFOLDER_NAME], doc=doc)
        self.file_image_name = file_image_name

    def get_absolute_path(self, measurements=None, image_set_index=None):
        if self.dir_choice == PC_WITH_IMAGE:
            path_name_feature = "PathName_%s" % self.file_image_name.value
            return measurements.get_current_image_measurement(path_name_feature)
        return super(SaveImagesDirectoryPath, self).get_absolute_path(
            measurements, image_set_index)

    def test_valid(self, pipeline):
        if self.dir_choice not in self.dir_choices:
            raise cps.ValidationError("%s is not a valid directory option" %
                                      self.dir_choice, self)

    @staticmethod
    def upgrade_setting(value):
        '''Upgrade setting from previous version'''
        dir_choice, custom_path = cps.DirectoryPath.split_string(value)
        if dir_choice in OLD_PC_WITH_IMAGE_VALUES:
            dir_choice = PC_WITH_IMAGE
        elif dir_choice in (PC_CUSTOM, PC_WITH_METADATA):
            if custom_path.startswith('.'):
                dir_choice = cps.DEFAULT_OUTPUT_SUBFOLDER_NAME
            elif custom_path.startswith('&'):
                dir_choice = cps.DEFAULT_INPUT_SUBFOLDER_NAME
                custom_path = '.' + custom_path[1:]
            else:
                dir_choice = cps.ABSOLUTE_FOLDER_NAME
        else:
            return cps.DirectoryPath.upgrade_setting(value)
        return cps.DirectoryPath.static_join_string(dir_choice, custom_path)

def save_h5(path, pixels, pixel_type):
    ''' Saves an image to an hdf5 with xyc axistag
    This format should be good for ilastik pixel classification for multiplexed images

    path - path to file image
    pixels - the pixel data
    pixel_dtype - the output pixel dtype
    '''
    if len(pixels.shape) == 2:
        pixels = pixels.reshape(list(pixels.shape)+[1])
    pixels = pixels.astype(pixel_type)

    with h5py.File(path, 'w') as f:
        dset = f.create_dataset('stacked_channels',
			shape=pixels.shape, dtype=pixels.dtype, chunks=True)
        dset.attrs['axistags'] = H5_YXC_AXISTAG
        dset[:,:,:] = pixels


def save_bmp(path, img):
    '''Save an image as a Microsoft .bmp file

    path - path to file to save

    img - either a 2d, uint8 image or a 2d + 3 plane uint8 RGB color image

    Saves file as an uncompressed 8-bit or 24-bit .bmp image
    '''
    #
    # Details from
    # http://en.wikipedia.org/wiki/BMP_file_format#cite_note-DIBHeaderTypes-3
    #
    # BITMAPFILEHEADER
    # http://msdn.microsoft.com/en-us/library/dd183374(v=vs.85).aspx
    #
    # BITMAPINFOHEADER
    # http://msdn.microsoft.com/en-us/library/dd183376(v=vs.85).aspx
    #
    BITMAPINFOHEADER_SIZE = 40
    img = img.astype(np.uint8)
    w = img.shape[1]
    h = img.shape[0]
    #
    # Convert RGB to interleaved
    #
    if img.ndim == 3:
        rgb = True
        #
        # Compute padded raster length
        #
        raster_length = (w * 3 + 3) & ~ 3
        tmp = np.zeros((h, raster_length), np.uint8)
        #
        # Do not understand why but RGB is BGR
        #
        tmp[:, 2:(w*3):3] = img[:, :, 0]
        tmp[:, 1:(w*3):3] = img[:, :, 1]
        tmp[:, 0:(w*3):3] = img[:, :, 2]
        img = tmp
    else:
        rgb = False
        if w % 4 != 0:
            raster_length = (w + 3) & ~ 3
            tmp = np.zeros((h, raster_length), np.uint8)
            tmp[:, :w] = img
            img = tmp
    #
    # The image is upside-down in .BMP
    #
    bmp = np.ascontiguousarray(np.flipud(img)).data
    with open(path, "wb") as fd:
        def write2(value):
            '''write a two-byte little-endian value to the file'''
            fd.write(np.array([value], "<u2").data[:2])
        def write4(value):
            '''write a four-byte little-endian value to the file'''
            fd.write(np.array([value], "<u4").data[:4])
        #
        # Bitmap file header (1st pass)
        # byte
        # 0-1 = "BM"
        # 2-5 = length of file
        # 6-9 = 0
        # 10-13 = offset from beginning of file to bitmap bits
        fd.write("BM")
        length = 14 # BITMAPFILEHEADER
        length += BITMAPINFOHEADER_SIZE
        if not rgb:
            length += 4 * 256         # 256 color table entries
        hdr_length = length
        length += len(bmp)
        write4(length)
        write4(0)
        write4(hdr_length)
        #
        # BITMAPINFOHEADER
        #
        write4(BITMAPINFOHEADER_SIZE) # biSize
        write4(w)                     # biWidth
        write4(h)                     # biHeight
        write2(1)                     # biPlanes = 1
        write2(24 if rgb else 8)      # biBitCount
        write4(0)                     # biCompression = BI_RGB
        write4(len(bmp))              # biSizeImage
        write4(7200)                  # biXPelsPerMeter
        write4(7200)                  # biYPelsPerMeter
        write4(0 if rgb else 256)     # biClrUsed (no palette)
        write4(0)                     # biClrImportant
        if not rgb:
            # The color table
            color_table = np.column_stack(
                [np.arange(256)]* 3 +
                [np.zeros(256, np.uint32)]).astype(np.uint8)
            fd.write(np.ascontiguousarray(color_table, np.uint8).data)
        fd.write(bmp)