#-----------------------------------------------------------------------------
# Copyright (c) 2012 - 2019, Anaconda, Inc., and Bokeh Contributors.
# All rights reserved.
#
# The full license is in the file LICENSE.txt, distributed with this software.
#-----------------------------------------------------------------------------
'''

'''

#-----------------------------------------------------------------------------
# Boilerplate
#-----------------------------------------------------------------------------
import logging # isort:skip
log = logging.getLogger(__name__)

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Standard library imports
import io
import os
import warnings
from os.path import abspath
from tempfile import mkstemp

# External imports
from PIL import Image

# Bokeh imports
from ..embed import file_html
from ..resources import INLINE
from .util import default_filename
from .webdriver import WebDriver, webdriver_control

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

__all__ = (
    'export_png',
    'export_svgs',
    'get_layout_html',
    'get_screenshot_as_png',
    'get_svgs',
)

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------

def export_png(obj, filename=None, height=None, width=None, webdriver=None, timeout=5):
    ''' Export the ``LayoutDOM`` object or document as a PNG.

    If the filename is not given, it is derived from the script name (e.g.
    ``/foo/myplot.py`` will create ``/foo/myplot.png``)

    Args:
        obj (LayoutDOM or Document) : a Layout (Row/Column), Plot or Widget
            object or Document to export.

        filename (str, optional) : filename to save document under (default: None)
            If None, infer from the filename.

        height (int) : the desired height of the exported layout obj only if
            it's a Plot instance. Otherwise the height kwarg is ignored.

        width (int) : the desired width of the exported layout obj only if
            it's a Plot instance. Otherwise the width kwarg is ignored.

        webdriver (selenium.webdriver) : a selenium webdriver instance to use
            to export the image.

        timeout (int) : the maximum amount of time (in seconds) to wait for
            Bokeh to initialize (default: 5) (Added in 1.1.1).

    Returns:
        filename (str) : the filename where the static file is saved.

    If you would like to access an Image object directly, rather than save a
    file to disk, use the lower-level :func:`~bokeh.io.export.get_screenshot_as_png`
    function.

    .. warning::
        Responsive sizing_modes may generate layouts with unexpected size and
        aspect ratios. It is recommended to use the default ``fixed`` sizing mode.

    '''

    image = get_screenshot_as_png(obj, height=height, width=width, driver=webdriver, timeout=timeout)

    if filename is None:
        filename = default_filename("png")

    if image.width == 0 or image.height == 0:
        raise ValueError("unable to save an empty image")

    image.save(filename)

    return abspath(filename)

def export_svgs(obj, filename=None, height=None, width=None, webdriver=None, timeout=5):
    ''' Export the SVG-enabled plots within a layout. Each plot will result
    in a distinct SVG file.

    If the filename is not given, it is derived from the script name
    (e.g. ``/foo/myplot.py`` will create ``/foo/myplot.svg``)

    Args:
        obj (LayoutDOM object) : a Layout (Row/Column), Plot or Widget object to display

        filename (str, optional) : filename to save document under (default: None)
            If None, infer from the filename.

        height (int) : the desired height of the exported layout obj only if
            it's a Plot instance. Otherwise the height kwarg is ignored.

        width (int) : the desired width of the exported layout obj only if
            it's a Plot instance. Otherwise the width kwarg is ignored.

        webdriver (selenium.webdriver) : a selenium webdriver instance to use
            to export the image.

        timeout (int) : the maximum amount of time (in seconds) to wait for
            Bokeh to initialize (default: 5) (Added in 1.1.1).

    Returns:
        filenames (list(str)) : the list of filenames where the SVGs files are
        saved.

    .. warning::
        Responsive sizing_modes may generate layouts with unexpected size and
        aspect ratios. It is recommended to use the default ``fixed`` sizing mode.

    '''
    svgs = get_svgs(obj, height=height, width=width, driver=webdriver, timeout=timeout)

    if len(svgs) == 0:
        log.warning("No SVG Plots were found.")
        return

    if filename is None:
        filename = default_filename("svg")

    filenames = []

    for i, svg in enumerate(svgs):
        if i == 0:
            filename = filename
        else:
            idx = filename.find(".svg")
            filename = filename[:idx] + "_{}".format(i) + filename[idx:]

        with io.open(filename, mode="w", encoding="utf-8") as f:
            f.write(svg)

        filenames.append(filename)

    return filenames

#-----------------------------------------------------------------------------
# Dev API
#-----------------------------------------------------------------------------

def get_screenshot_as_png(obj, driver=None, timeout=5, **kwargs):
    ''' Get a screenshot of a ``LayoutDOM`` object.

    Args:
        obj (LayoutDOM or Document) : a Layout (Row/Column), Plot or Widget
            object or Document to export.

        driver (selenium.webdriver) : a selenium webdriver instance to use
            to export the image.

        timeout (int) : the maximum amount of time to wait for initialization.
            It will be used as a timeout for loading Bokeh, then when waiting for
            the layout to be rendered.

    Returns:
        image (PIL.Image.Image) : a pillow image loaded from PNG.

    .. warning::
        Responsive sizing_modes may generate layouts with unexpected size and
        aspect ratios. It is recommended to use the default ``fixed`` sizing mode.

    '''
    with _tmp_html() as tmp:
        html = get_layout_html(obj, **kwargs)
        with io.open(tmp.path, mode="w", encoding="utf-8") as file:
            file.write(html)

        web_driver = driver if driver is not None else webdriver_control.get()
        web_driver.maximize_window()
        web_driver.get("file:///" + tmp.path)
        wait_until_render_complete(web_driver, timeout)
        _maximize_viewport(web_driver)
        png = web_driver.get_screenshot_as_png()

    return Image.open(io.BytesIO(png)).convert("RGBA")

def get_svgs(obj, driver=None, timeout=5, **kwargs):
    '''

    '''
    with _tmp_html() as tmp:
        html = get_layout_html(obj, **kwargs)
        with io.open(tmp.path, mode="w", encoding="utf-8") as file:
            file.write(html)

        web_driver = driver if driver is not None else webdriver_control.get()
        web_driver.get("file:///" + tmp.path)
        wait_until_render_complete(web_driver, timeout)
        svgs = web_driver.execute_script(_SVG_SCRIPT)

    return svgs

def get_layout_html(obj, resources=INLINE, **kwargs):
    '''

    '''
    resize = False
    if kwargs.get('height') is not None or kwargs.get('width') is not None:
        # Defer this import, it is expensive
        from ..models.plots import Plot
        if not isinstance(obj, Plot):
            warnings.warn("Export method called with height or width kwargs on a non-Plot layout. The size values will be ignored.")
        else:
            resize = True
            old_height = obj.plot_height
            old_width = obj.plot_width
            obj.plot_height = kwargs.get('height', old_height)
            obj.plot_width = kwargs.get('width', old_width)

    template = r"""\
    {% block preamble %}
    <style>
        html, body {
            margin: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
        }
    </style>
    {% endblock %}
    """

    try:
        html = file_html(obj, resources, title="", template=template, suppress_callback_warning=True, _always_new=True)
    finally:
        if resize:
            obj.plot_height = old_height
            obj.plot_width = old_width

    return html

def wait_until_render_complete(driver, timeout):
    '''

    '''
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException

    def is_bokeh_loaded(driver):
        return driver.execute_script('''
            return typeof Bokeh !== "undefined" && Bokeh.documents != null && Bokeh.documents.length != 0
        ''')

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.1).until(is_bokeh_loaded)
    except TimeoutException as e:
        _log_console(driver)
        raise RuntimeError('Bokeh was not loaded in time. Something may have gone wrong.') from e

    driver.execute_script(_WAIT_SCRIPT)

    def is_bokeh_render_complete(driver):
        return driver.execute_script('return window._bokeh_render_complete;')

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.1).until(is_bokeh_render_complete)
    except TimeoutException:
        log.warning("The webdriver raised a TimeoutException while waiting for "
                    "a 'bokeh:idle' event to signify that the layout has rendered. "
                    "Something may have gone wrong.")
    finally:
        _log_console(driver)

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------

def _log_console(driver):
    levels = {'WARNING', 'ERROR', 'SEVERE'}
    logs = driver.get_log('browser')
    messages = [ log.get("message") for log in logs if log.get('level') in levels ]
    if len(messages) > 0:
        log.warning("There were browser warnings and/or errors that may have affected your export")
        for message in messages:
            log.warning(message)

def _maximize_viewport(web_driver: WebDriver) -> None:
    calculate_window_size = """\
        const root = document.getElementsByClassName("bk-root")[0]
        const {width, height} = root.children[0].getBoundingClientRect()
        return [
            window.outerWidth - window.innerWidth + width,
            window.outerHeight - window.innerHeight + height,
        ]
    """
    [width, height] = web_driver.execute_script(calculate_window_size)
    web_driver.set_window_size(width, height)

_SVG_SCRIPT = """
var serialized_svgs = [];
var svgs = document.getElementsByClassName('bk-root')[0].getElementsByTagName("svg");
for (var i = 0; i < svgs.length; i++) {
    var source = (new XMLSerializer()).serializeToString(svgs[i]);
    serialized_svgs.push(source);
};
return serialized_svgs
"""

_WAIT_SCRIPT = """
// add private window prop to check that render is complete
window._bokeh_render_complete = false;
function done() {
  window._bokeh_render_complete = true;
}

var doc = window.Bokeh.documents[0];

if (doc.is_idle)
  done();
else
  doc.idle.connect(done);
"""

class _TempFile(object):

    _closed = False

    def __init__(self, prefix="tmp", suffix=""):
        self.fd, self.path = mkstemp(prefix=prefix, suffix=suffix)

    def __enter__(self):
        return self

    def __exit__(self, exc, value, tb):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        if self._closed:
            return

        try:
            os.close(self.fd)
        except (OSError, IOError):
            pass
        finally:
            self.fd = None

        try:
            os.unlink(self.path)
        except (OSError, IOError):
            pass
        finally:
            self.path = None

        self._closed = True

def _tmp_html():
    return _TempFile(prefix="bokeh", suffix=".html")

#-----------------------------------------------------------------------------
# Code
#-----------------------------------------------------------------------------
