#Copyright (c) 2011 Walter Bender

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA

import os
import subprocess
from StringIO import StringIO
try:
    OLD_SUGAR_SYSTEM = False
    import json
    json.dumps
    from json import load as jload
    from json import dump as jdump
except (ImportError, AttributeError):
    try:
        import simplejson as json
        from simplejson import load as jload
        from simplejson import dump as jdump
    except:
        OLD_SUGAR_SYSTEM = True


XO1 = 'xo1'
XO15 = 'xo1.5'
XO175 = 'xo1.75'
UNKNOWN = 'unknown'


def get_hardware():
    """ Determine whether we are using XO 1.0, 1.5, or "unknown" hardware """
    product = _get_dmi('product_name')
    if product is None:
        if os.path.exists('/sys/devices/platform/lis3lv02d/position'):
            return XO175  # FIXME: temporary check for XO 1.75
        elif os.path.exists('/etc/olpc-release') or \
           os.path.exists('/sys/power/olpc-pm'):
            return XO1
        else:
            return UNKNOWN
    if product != 'XO':
        return UNKNOWN
    version = _get_dmi('product_version')
    if version == '1':
        return XO1
    elif version == '1.5':
        return XO15
    else:
        return XO175


def _get_dmi(node):
    ''' The desktop management interface should be a reliable source
    for product and version information. '''
    path = os.path.join('/sys/class/dmi/id', node)
    try:
        return open(path).readline().strip()
    except:
        return None


def json_load(text):
    """ Load JSON data using what ever resources are available. """
    if OLD_SUGAR_SYSTEM is True:
        listdata = json.read(text)
    else:
        # strip out leading and trailing whitespace, nulls, and newlines
        io = StringIO(text)
        try:
            listdata = jload(io)
        except ValueError:
            # assume that text is ascii list
            listdata = text.split()
            for i, value in enumerate(listdata):
                listdata[i] = int(value)
    return listdata


def json_dump(data):
    """ Save data using available JSON tools. """
    if OLD_SUGAR_SYSTEM is True:
        return json.write(data)
    else:
        _io = StringIO()
        jdump(data, _io)
        return _io.getvalue()


def file_to_base64(activity, path):
    base64 = os.path.join(get_path(activity, 'instance'), 'base64tmp')
    cmd = 'base64 <' + path + ' >' + base64
    subprocess.check_call(cmd, shell=True)
    file_handle = open(base64, 'r')
    data = file_handle.read()
    file_handle.close()
    os.remove(base64)
    return data


def pixbuf_to_base64(activity, pixbuf):
    ''' Convert pixbuf to base64-encoded data '''
    png_file = os.path.join(get_path(activity, 'instance'), 'imagetmp.png')
    if pixbuf != None:
        pixbuf.save(png_file, "png")
    data = file_to_base64(activity, png_file)
    os.remove(png_file)
    return data


def base64_to_file(activity, data, path):
    base64 = os.path.join(get_path(activity, 'instance'), 'base64tmp')
    file_handle = open(base64, 'w')
    file_handle.write(data)
    file_handle.close()
    cmd = 'base64 -d <' + base64 + '>' + path
    subprocess.check_call(cmd, shell=True)
    os.remove(base64)


def base64_to_pixbuf(activity, data, width=55, height=55):
    ''' Convert base64-encoded data to a pixbuf '''
    png_file = os.path.join(get_path(activity, 'instance'), 'imagetmp.png')
    base64_to_file(activity, data, png_file)
    pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(png_file, width, height)
    os.remove(png_file)
    return pixbuf
