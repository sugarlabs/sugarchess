#Copyright (c) 2011 Walter Bender

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


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
