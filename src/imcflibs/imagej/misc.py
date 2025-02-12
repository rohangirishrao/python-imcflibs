"""Miscellaneous ImageJ related functions, mostly convenience wrappers."""

import sys
import time
import os

from ij import IJ  # pylint: disable-msg=import-error
from ij.plugin import ImageCalculator, Concatenator
from ij.process import StackStatistics, ImageProcessor

from . import prefs
from ..log import LOG as log


def show_status(msg):
    """Update the ImageJ status bar and issue a log message.

    Parameters
    ----------
    msg : str
        The message to display in the ImageJ status bar and log.
    """
    log.info(msg)
    IJ.showStatus(msg)


def show_progress(cur, final):
    """Update the ImageJ progress bar and log the current progress.

    Parameters
    ----------
    cur : int
        Current progress value.
    final : int
        Total value representing 100% completion.

    Notes
    -----
    `ij.IJ.showProgress` internally increments the given `cur` value by 1
    """
    log.info("Progress: %s / %s (%s)", cur + 1, final, (1.0 + cur) / final)
    IJ.showProgress(cur, final)


def error_exit(msg):
    """Log an error message and exit.

    Parameters
    ----------
    msg : str
        The error message to log.
    """
    log.error(msg)
    sys.exit(msg)


def elapsed_time_since(start, end=None):
    """Generate a string with the time elapsed between two timepoints.

    Parameters
    ----------
    start : float
        The start time, typically obtained via `time.time()`.
    end : float, optional
        The end time. If not given, the current time is used.

    Returns
    -------
    str
        The elapsed time formatted as `HH:MM:SS.ss`.

    """
    if not end:
        end = time.time()

    hours, rem = divmod(end - start, 3600)
    minutes, seconds = divmod(rem, 60)
    return "{:0>2}:{:0>2}:{:05.2f}".format(int(hours), int(minutes), seconds)


def percentage(part, whole):
    """Calculate the percentage of a value based on total.

    Parameters
    ----------
    part : float
        The portion value of a total.
    whole : float
        The total value.

    Returns
    -------
    float
        The percentage value.
    """
    return 100 * float(part) / float(whole)


def calculate_mean_and_stdv(float_values):
    """Calculate mean and standard deviation from a list of floats.

    Parameters
    ----------
    float_values : list of float
        List containing float numbers.

    Returns
    -------
    tuple of (float, float)
        Mean and standard deviation of the input list.
    """
    mean = sum(float_values) / len(float_values)
    tot = 0.0
    for x in float_values:
        tot = tot + (x - mean) ** 2
    return [mean, (tot / (len(float_values))) ** 0.5]


def find_focus(imp):
    """Find the slice of a stack that is the best focused one.

    This function calculates the variance of the pixel values in each slice.
    The slice with the highest variance is considered the best focused
    because a higher variance typically indicates more contrast and sharpness.

    Parameters
    ----------
    imp : ij.ImagePlus
        A single-channel ImagePlus stack.

    Returns
    -------
    int
        The slice number of the best focused slice.

    Raises
    ------
    SystemExit
        If the image has more than one channel.

    Notes
    -----
    Currently only single-channel stacks are supported.
    """

    imp_dimensions = imp.getDimensions()

    # Check if more than 1 channel
    # FUTURE Could be improved for multi channel
    if imp_dimensions[2] != 1:
        sys.exit("Image has more than one channel, please reduce dimensionality")

    # Loop through each time point
    for plane in range(1, imp_dimensions[4] + 1):
        focused_slice = 0
        norm_var = 0
        imp.setT(plane)
        # Loop through each z plane
        for current_z in range(1, imp_dimensions[3] + 1):
            imp.setZ(current_z)
            pix_array = imp.getProcessor().getPixels()
            mean = (sum(pix_array)) / len(pix_array)
            pix_array = [(x - mean) * (x - mean) for x in pix_array]
            # pix_array = pix_array*pix_array

            sumpix_array = sum(pix_array)
            var = sumpix_array / (imp_dimensions[0] * imp_dimensions[1] * mean)

            if var > norm_var:
                norm_var = var
                focused_slice = current_z

    return focused_slice


def progressbar(progress, total, line_number, prefix=""):
    """Progress bar for the IJ log window.

    Show a progress bar in the log window of Fiji at a specific line independent
    of the main Fiji progress bar.

    Parameters
    ----------
    progress : int
        Current step of the loop.
    total : int
        Total number of steps for the loop.
    line_number : int
        Number of the line to be updated.
    prefix : str, optional
        Text to use before the progress bar, by default ''.
    """

    size = 20
    x = int(size * progress / total)
    IJ.log(
        "\\Update%i:%s[%s%s] %i/%i\r"
        % (
            line_number,
            timed_log(prefix, True),
            "#" * x,
            "." * (size - x),
            progress,
            total,
        )
    )


def timed_log(message, as_string=False):
    """Print a message to the ImageJ log window with a timestamp added.

    Parameters
    ----------
    message : str
        Message to print
    """
    if as_string:
        return time.strftime("%H:%M:%S", time.localtime()) + ": " + message + " "
    IJ.log(time.strftime("%H:%M:%S", time.localtime()) + ": " + message + " ")


def get_free_memory():
    """Get the free memory that is available to ImageJ.

    Returns
    -------
    free_memory : int
        The free memory in bytes.
    """
    max_memory = int(IJ.maxMemory())
    used_memory = int(IJ.currentMemory())
    free_memory = max_memory - used_memory

    return free_memory


def setup_clean_ij_environment(rm=None, rt=None):  # pylint: disable-msg=unused-argument
    """Set up a clean and defined ImageJ environment.

    This funtion clears the active results table, the ROI manager, and the log.
    Additionally, it closes all open images and resets the ImageJ options, performing a "Fresh Start".

    Parameters
    ----------
    rm : RoiManager, optional
        Will be ignored (kept for keeping API compatibility).
    rt : ResultsTable, optional
        Will be ignored (kept for keeping API compatibility).

    Notes
    -----
    "Fresh Start" is described in the ImageJ release notes [1] following a
    suggestion by Robert Haase in the Image.sc Forum [2].

    [1]: https://imagej.nih.gov/ij/notes.html
    [2]: https://forum.image.sc/t/fresh-start-macro-command-in-imagej-fiji/43102
    """

    IJ.run("Fresh Start", "")
    IJ.log("\\Clear")

    prefs.fix_ij_options()


def sanitize_image_title(imp):
    """Remove special characters and various suffixes from the title of an open ImagePlus.

    Parameters
    ----------
    imp : ImagePlus
        The ImagePlus to be renamed.

    Notes
    -----
    - The function removes the full path of the image file (if present), retaining only
      the base filename using `os.path.basename()`.
    """
    # sometimes (unclear when) the title contains the full path, therefore we
    # simply call `os.path.basename()` on it to remove all up to the last "/":
    image_title = os.path.basename(imp.getTitle())
    image_title = image_title.replace(".czi", "")
    image_title = image_title.replace(" ", "_")
    image_title = image_title.replace("_-_", "")
    image_title = image_title.replace("__", "_")
    image_title = image_title.replace("#", "Series")

    imp.setTitle(image_title)


def subtract_images(imp1, imp2):
    """Subtract one image from the other (imp1 - imp2)

    Parameters
    ----------
    imp1: ij.ImagePlus
        The ImagePlus that is to be subtracted from
    imp2: ij.ImagePlus
        The ImagePlus that is to be subtracted

    Returns
    ---------
    subtracted: ij.ImagePlus
        The resulting ImagePlus from the subtraction
    """
    ic = ImageCalculator()
    subtracted = ic.run("Subtract create", imp1, imp2)

    return subtracted


def close_images(list_of_imps):
    """Closes all open image plus objects given in a list

    Parameters
    ----------
    list_of_imps : list of ij.ImagePlus
        A list of open ImagePlus objects

    """
    for imp in list_of_imps:
        imp.changes = False
        imp.close()


def get_threshold_value_from_method(imp, method, ops):
    """Returns the threshold value of chosen IJ AutoThreshold method from an ImagePlus stack.

    Parameters
    ----------
    imp : ij.ImagePlus
        The image from which to get the threshold value.
    method : string
        The AutoThreshold method to use.
        Only the ones listed in the IJ AutoThreshold plugin are supported:
        'huang', 'ij1', 'intermodes', 'isoData', 'li', 'maxEntropy', 'maxLikelihood', 'mean', 'minError',
        'minimum', 'moments', 'otsu', 'percentile', 'renyiEntropy', 'rosin', 'shanbhag', 'triangle', 'yen'.
    ops: ops.OpService
        The ImageJ Ops service, defined as script parameter at the top of the script, as follows:
        #@ OpService ops

    Returns
    -------
    threshold_value: int
        The threshold value.
    """
    histogram = ops.run("image.histogram", imp)
    threshold_value = ops.run("threshold.%s" % method, histogram)
    threshold_value = int(round(threshold_value.get()))

    return threshold_value
