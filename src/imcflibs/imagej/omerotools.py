"""Functions allowing to interact with an OMERO server.

Contains helpers to parse URLs and / or OMERO image IDs, connect to OMERO and
fetch images from the server.
"""

# ImageJ Import
from ij import IJ

# Bioformats imports
from loci.formats import FormatTools, ImageTools
from loci.common import DataTools
from loci.plugins import LociExporter
from loci.plugins.in import ImporterOptions
from loci.plugins.out import Exporter

# Omero Dependencies
from omero.gateway import Gateway
from omero.gateway import LoginCredentials
from omero.gateway import SecurityContext
from omero.gateway.facility import BrowseFacility
from omero.gateway.facility import DataManagerFacility
from omero.gateway.model import DatasetData, MapAnnotationData
from omero.log import SimpleLogger
from omero.sys import ParametersI

from ome.formats.importer import ImportConfig
from ome.formats.importer import OMEROWrapper
from ome.formats.importer import ImportLibrary
from ome.formats.importer import ImportCandidates
from ome.formats.importer.cli import ErrorHandler
from ome.formats.importer.cli import LoggingImportMonitor
import loci.common
from loci.formats.in import DefaultMetadataOptions
from loci.formats.in import MetadataLevel

def parse_image_ids(input_string):
    """Parse an OMERO URL or a string with image IDs into a list.

    Parameters
    ----------
    input_string : str
        String which is either the direct image link (URL) from OMERO.web
        (which may contain multiple images selected) or a sequence of OMERO
        image IDs separated by commas.

    Returns
    -------
    str[]
        List of all the image IDs parsed from the input string.
    """
    if input_string.startswith("https"):
        image_ids = input_string.split("image-")
        image_ids.pop(0)
        image_ids = [s.split("%")[0].replace("|", "") for s in image_ids]
    else:
        image_ids = input_string.split(",")
    return image_ids


def connect(host, port, username, password):
    """Connect to OMERO using the credentials provided.

    Parameters
    ----------
    host : str
        The address (FQDN or IP) of the OMERO server.
    port : int
        The port number for the OMERO server.
    username : str
        The username for authentication.
    password : str
        The password for authentication.

    Returns
    -------
    omero.gateway.Gateway
        A Gateway object representing the connection to the OMERO server.
    """
    # Omero Connect with credentials and simpleLogger
    cred = LoginCredentials()
    cred.getServer().setHostname(host)
    cred.getServer().setPort(port)
    cred.getUser().setUsername(username.strip())
    cred.getUser().setPassword(password.strip())
    simple_logger = SimpleLogger()
    gateway = Gateway(simple_logger)
    gateway.connect(cred)
    return gateway


def fetch_image(host, username, password, image_id, group_id=-1):
    """Fetch an image from an OMERO server and open it as an ImagePlus.

    NOTE: the function does **NOT** return the ImagePlus (nor its ID) as this
    information is not provided by the underlying `loci.plugins.LociImporter`
    call - it simply opens it in the running ImageJ instance.

    Parameters
    ----------
    host : str
        The address (FQDN or IP) of the OMERO server.
    username : str
        The username for authentication.
    password : str
        The password for authentication.
    image_id: int
        ID of the image to fetch.
    group_id : int, optional
        The OMERO group ID, by default -1 meaning the user's default group.
    """
    stackview = "viewhyperstack=true stackorder=XYCZT "
    dataset_org = " ".join(
        [
            "groupfiles=false",
            "swapdimensions=false",
            "openallseries=false",
            "concatenate=false",
            "stitchtiles=false",
        ]
    )
    color_opt = "colormode=Default autoscale=true"
    metadata_view = " ".join(
        [
            "showmetadata=false",
            "showomexml=false",
            "showrois=true",
            "setroismode=roimanager",
        ]
    )
    memory_manage = "virtual=false specifyranges=false setcrop=false"
    split = "splitchannels=false splitfocalplanes=false splittimepoints=false"
    other = "windowless=true"
    open_options = "\n".join(
        [
            "open=[omero:server=" + host,
            "user=" + username,
            "pass=" + password,
            "groupID=" + group_id,
            "iid=" + image_id + "]",
        ]
    )
    options = " ".join(
        [
            "location=[OMERO]",
            open_options,
            stackview,
            dataset_org,
            color_opt,
            metadata_view,
            memory_manage,
            split,
            other,
        ]
    )
    IJ.runPlugIn("loci.plugins.LociImporter", options)


def upload_image(path, gateway, dataset_id):
    """Upload the image back to OMERO

    Parameters
    ----------
    path : str
        Path of the file to upload back to OMERO
    gateway : omero.gateway.Gateway
        Gateway to the OMERO server

    Returns
    -------
    list[int]
        List of IDs of the imported images
    """

    user = gateway.getLoggedInUser()
    ctx = SecurityContext(user.getGroupId())
    sessionKey = gateway.getSessionId(user)

    config = ImportConfig()

    config.email.set("")
    config.sendFiles.set("true")
    config.sendReport.set("false")
    config.contOnError.set("false")
    config.debug.set("false")
    config.hostname.set(HOST)
    config.sessionKey.set(sessionKey)
    dataset = find_dataset(gateway, dataset_id)

    loci.common.DebugTools.enableLogging("DEBUG")

    store = config.createStore()
    reader = OMEROWrapper(config)

    library = ImportLibrary(store, reader)
    errorHandler = ErrorHandler(config)

    library.addObserver(LoggingImportMonitor())
    str2d = java.lang.reflect.Array.newInstance(java.lang.String, [1])
    str2d[0] = path

    candidates = ImportCandidates(reader, str2d, errorHandler)

    reader.setMetadataOptions(DefaultMetadataOptions(MetadataLevel.ALL))

    container_list = candidates.getContainers()
    num_done = 0
    ids_list = []
    for i in range(len(container_list)):
        container = container_list[i]
        container.setTarget(dataset)
        pixels = library.importImage(container, i, num_done, len(container_list))
        ids_list.append(pixels[0].getImage().getId().getValue())
        num_done += 1

    return ids_list

def upload_kv(gateway, dict, header, image_id):
    """Add annotation to OMERO object

    Parameters
    ----------
    gateway : omero.gateway.Gateway
        Gateway to the OMERO server
    dict : dict
        Dictionary with the annotation to add
    header : str
        Name for the annotation header
    image_id : int
        Image ID on the OMERO server
    """
    browse = gateway.getFacility(BrowseFacility)
    user = gateway.getLoggedInUser()
    ctx = SecurityContext(user.getGroupId())
    image = browse.getImage(ctx, long(image_id))

    data = MapAnnotationData()
    data.setContent(dict)
    data.setDescription(header)
    data.setNameSpace(MapAnnotationData.NS_CLIENT_CREATED)

    fac = gateway.getFacility(DataManagerFacility)
    fac.attachAnnotation(ctx, data, image)

def find_dataset(gateway, dataset_id):
    """Returns the dataset object associated with the given dataset ID

    Parameters
    ----------
    gateway : omero.gateway.Gateway
        Gateway to the OMERO server
    dataset_id : int
        Image ID of the dataset

    Returns
    -------
    omero.model.Dataset
        Dataset object corresponding to the ID

    """
    browse = gateway.getFacility(BrowseFacility)
    user = gateway.getLoggedInUser()
    ctx = SecurityContext(user.getGroupId())
    return browse.findIObject(ctx, "omero.model.Dataset", dataset_id)