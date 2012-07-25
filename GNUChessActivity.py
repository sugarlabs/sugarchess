#Copyright (c) 2012 Walter Bender

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


import gtk
import gobject

from sugar.activity import activity
from sugar import profile
from sugar.graphics.toolbarbox import ToolbarBox
from sugar.activity.widgets import ActivityToolbarButton
from sugar.activity.widgets import StopButton
from sugar.graphics.toolbarbox import ToolbarButton
from sugar.graphics.objectchooser import ObjectChooser
from sugar.datastore import datastore
from sugar import mime
from sugar.graphics.alert import ConfirmationAlert, NotifyAlert

from toolbar_utils import button_factory, label_factory, separator_factory, \
    radio_factory, entry_factory
from utils import json_load, json_dump, get_hardware

import telepathy
import dbus
from dbus.service import signal
from dbus.gobject_service import ExportedGObject
from sugar.presence import presenceservice
from sugar.presence.tubeconn import TubeConnection

from gettext import gettext as _

from chess import Gnuchess

import logging
_logger = logging.getLogger('gnuchess-activity')


SERVICE = 'org.sugarlabs.GNUChessActivity'
IFACE = SERVICE
PATH = '/org/augarlabs/GNUChessActivity'


class GNUChessActivity(activity.Activity):
    ''' Gnuchess interface from Sugar '''

    def __init__(self, handle):
        ''' Initialize the toolbars and the gnuchess '''
        try:
            super(GNUChessActivity, self).__init__(handle)
        except dbus.exceptions.DBusException, e:
            _logger.error(str(e))

        self.game_data = None
        self.playing_white = True
        self.playing_mode = 'easy'
        self.playing_robot = True
        self.showing_game_history = False
        self._restoring = True

        self.nick = profile.get_nick_name()
        if profile.get_color() is not None:
            self.colors = profile.get_color().to_string().split(',')
        else:
            self.colors = ['#A0FFA0', '#FF8080']

        self.hardware = get_hardware()
        self._setup_toolbars()
        self._setup_dispatch_table()

        # Create a canvas
        canvas = gtk.DrawingArea()
        canvas.set_size_request(gtk.gdk.screen_width(), \
                                gtk.gdk.screen_height())
        self.set_canvas(canvas)
        canvas.show()
        self.show_all()

        if hasattr(self.get_window(), 'get_cursor'):
            self.old_cursor = self.get_window().get_cursor()
        else:
            self.old_cursor = None

        self._gnuchess = Gnuchess(canvas,
                                  parent=self,
                                  path=activity.get_bundle_path(),
                                  colors=self.colors)
        self._setup_presence_service()

        if self.game_data is not None:  # 'saved_game' in self.metadata:
            self._restore()
        else:
            self._gnuchess.new_game()
        self._restoring = False

    def restore_cursor(self):
        ''' No longer thinking, so restore standard cursor. '''
        if hasattr(self.get_window(), 'get_cursor'):
            self.get_window().set_cursor(self.old_cursor)
        else:
            self.get_window().set_cursor(gtk.gdk.Cursor(gtk.gdk.LEFT_PTR))

    def set_thinking_cursor(self):
        ''' Thinking, so set watch cursor. '''
        if hasattr(self.get_window(), 'get_cursor'):
            self.old_cursor = self.get_window().get_cursor()
        self.get_window().set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))

    def _setup_toolbars(self):
        ''' Setup the toolbars. '''

        self.max_participants = 1  # No sharing to begin with

        self.edit_toolbar = gtk.Toolbar()
        self.view_toolbar = gtk.Toolbar()
        self.adjust_toolbar = gtk.Toolbar()
        self.custom_toolbar = gtk.Toolbar()
        toolbox = ToolbarBox()

        activity_button = ActivityToolbarButton(self)
        toolbox.toolbar.insert(activity_button, 0)
        activity_button.show()

        edit_toolbar_button = ToolbarButton(label=_("Edit"),
                                            page=self.edit_toolbar,
                                            icon_name='toolbar-edit')
        self.edit_toolbar.show()
        toolbox.toolbar.insert(edit_toolbar_button, -1)
        edit_toolbar_button.show()

        view_toolbar_button = ToolbarButton(label=_("View"),
                                            page=self.view_toolbar,
                                            icon_name='toolbar-view')
        self.view_toolbar.show()
        toolbox.toolbar.insert(view_toolbar_button, -1)
        view_toolbar_button.show()
            
        adjust_toolbar_button = ToolbarButton(label=_('Adjust'),
                                              page=self.adjust_toolbar,
                                              icon_name='preferences-system')
        self.adjust_toolbar.show()
        toolbox.toolbar.insert(adjust_toolbar_button, -1)
        adjust_toolbar_button.show()

        custom_toolbar_button = ToolbarButton(label=_("Custom"),
                                              page=self.custom_toolbar,
                                              icon_name='view-source')
        self.custom_toolbar.show()
        toolbox.toolbar.insert(custom_toolbar_button, -1)
        custom_toolbar_button.show()

        self.set_toolbar_box(toolbox)
        toolbox.show()
        self.toolbar = toolbox.toolbar

        adjust_toolbar_button.set_expanded(True)

        button_factory('edit-copy',
                       self.edit_toolbar,
                       self._copy_cb,
                       tooltip=_('Copy'),
                       accelerator='<Ctrl>c')

        button_factory('edit-paste',
                       self.edit_toolbar,
                       self._paste_cb,
                       tooltip=_('Paste'),
                       accelerator='<Ctrl>v')

        button_factory('view-fullscreen',
                       self.view_toolbar,
                       self.do_fullscreen_cb,
                       tooltip=_('Fullscreen'),
                       accelerator='<Alt>Return')

        button_factory('media-playback-start',
                       self.view_toolbar,
                       self._play_history_cb,
                       tooltip=_('Play game history'))

        self.history_button = button_factory('list-numbered',
                                             self.view_toolbar,
                                             self._show_history_cb,
                                             tooltip=_('Show game history'))

        separator_factory(self.view_toolbar, False, True)

        label_factory(self.view_toolbar,
                      _('White: '))
        self.white_entry = entry_factory('',
                                         self.view_toolbar,
                                         tooltip=_("White's move"))

        separator_factory(self.view_toolbar, False, False)

        label_factory(self.view_toolbar,
                      _('Black: '))
        self.black_entry = entry_factory('',
                                         self.view_toolbar,
                                         tooltip=_("Black's move"))

        self.play_white_button = radio_factory('white-rook',
                                               self.adjust_toolbar,
                                               self._play_white_cb,
                                               group=None,
                                               tooltip=_('Play White'))

        self.play_black_button = radio_factory('black-rook',
                                               self.adjust_toolbar,
                                               self._play_black_cb,
                                               group=self.play_white_button,
                                               tooltip=_('Play Black'))

        self.play_white_button.set_active(True)

        separator_factory(self.adjust_toolbar, False, True)

        self.easy_button = radio_factory('beginner',
                                         self.adjust_toolbar,
                                         self._easy_cb,
                                         group=None,
                                         tooltip=_('Beginner'))

        self.hard_button = radio_factory('expert',
                                         self.adjust_toolbar,
                                         self._hard_cb,
                                         group=self.easy_button,
                                         tooltip=_('Expert'))

        self.easy_button.set_active(True)

        separator_factory(self.adjust_toolbar, False, True)

        self.robot_button = radio_factory('robot',
                                          self.adjust_toolbar,
                                          self._robot_cb,
                                          group=None,
                                          tooltip=_(
                'Play against the computer'))

        self.human_button = radio_factory('human',
                                          self.adjust_toolbar,
                                          self._human_cb,
                                          group=self.robot_button,
                                          tooltip=_('Play against a person'))

        self.robot_button.set_active(True)

        button_factory('new-game',
                       self.toolbar,
                       self._new_gnuchess_cb,
                       tooltip=_('New game'))

        button_factory('edit-undo',
                       self.toolbar,
                       self._undo_cb,
                       tooltip=_('Undo'))

        button_factory('hint',
                       self.toolbar,
                       self._hint_cb,
                       tooltip=_('Hint'))

        separator_factory(self.toolbar, False, False)
        self.status = label_factory(self.toolbar, '')
        self.status.set_label(_("It is White's move."))

        separator_factory(toolbox.toolbar, True, False)
        stop_button = StopButton(self)
        stop_button.props.accelerator = '<Ctrl>q'
        toolbox.toolbar.insert(stop_button, -1)
        stop_button.show()

        button_factory('white-pawn',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='white_pawn',
                       tooltip=_('White Pawn'))

        button_factory('black-pawn',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='black_pawn',
                       tooltip=_('Black Pawn'))

        button_factory('white-rook',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='white_rook',
                       tooltip=_('White Rook'))

        button_factory('black-rook',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='black_rook',
                       tooltip=_('Black Rook'))

        button_factory('white-knight',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='white_knight',
                       tooltip=_('White Knight'))

        button_factory('black-knight',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='black_knight',
                       tooltip=_('Black Knight'))

        button_factory('white-bishop',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='white_bishop',
                       tooltip=_('White Bishop'))

        button_factory('black-bishop',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='black_bishop',
                       tooltip=_('Black Bishop'))

        button_factory('white-queen',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='white_queen',
                       tooltip=_('White Queen'))

        button_factory('black-queen',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='black_queen',
                       tooltip=_('Black Queen'))

        button_factory('white-king',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='white_king',
                       tooltip=_('White King'))

        button_factory('black-king',
                       self.custom_toolbar,
                       self._reskin_cb,
                       cb_arg='black_king',
                       tooltip=_('Black King'))

    def _reskin_cb(self, button, piece):
        id, file_path = self._choose_skin()
        if file_path is not None:
            self._gnuchess.reskin(piece, file_path)
            self.metadata[piece] = str(id)

    def do_fullscreen_cb(self, button):
        ''' Hide the Sugar toolbars. '''
        self.fullscreen()

    def _play_history_cb(self, button):
        self._gnuchess.play_game_history()
        return

    def _show_history_cb(self, button):
        self._gnuchess.show_game_history()
        if self.showing_game_history:
            self.history_button.set_icon('checkerboard')
            self.history_button.set_tooltip(_('Show game board'))
        else:
            self.history_button.set_icon('list-numbered')
            self.history_button.set_tooltip(_('Show game history'))
        return

    def _copy_cb(self, *args):
        clipboard = gtk.Clipboard()
        clipboard.set_text(self._gnuchess.copy_game())

    def _paste_cb(self, *args):
        ''' Pasting '''
        clipboard = gtk.Clipboard()
        move_list = self._parse_move_list(clipboard.wait_for_text())
        if move_list is not None:
            self._gnuchess.restore_game(move_list)
 
    def _parse_move_list(self, text):
        ''' Take a standard game description and return a move list '''
        # Assuming of form ... 1. e4 e6 2. ...
        move_list = []
        found_one = False
        comment = False
        for move in text.split():
            if move[0] == '{':
                comment = True
            elif move[-1] == '}':
                comment = False
            if not comment:
                if move == '1.':
                    found_one = True
                    number = True
                    white = False
                elif found_one:
                    if not number:
                        number = True
                    elif not white:
                        move_list.append(move)
                        white = True
                    else:
                        move_list.append(move)
                        number = False
                        white = False
        return move_list

    def _undo_cb(self, *args):
        self._gnuchess.undo()

    def _hint_cb(self, *args):
        self._gnuchess.hint()

    def _reset_restoring_flag(self):
        self._restoring = False

    def _play_white_cb(self, *args):
        if not self.play_white_button.get_active():
            return
        if not self._restoring:
            self._new_game_alert('white')
        return True

    def _play_black_cb(self, *args):
        if not self.play_black_button.get_active():
            return
        if not self._restoring:
            self._new_game_alert('black')
        return True

    def _easy_cb(self, *args):
        if not self.easy_button.get_active():
            return
        if not self._restoring:
            self._new_game_alert('easy')
        return True

    def _hard_cb(self, *args):
        if not self.hard_button.get_active():
            return
        if not self._restoring:
            self._new_game_alert('hard')
        return True

    def _robot_cb(self, *args):
        if not self.robot_button.get_active():
            return
        if not self._restoring:
            self._new_game_alert('robot')
        return True

    def _human_cb(self, *args):
        if not self.human_button.get_active():
            return
        if not self._restoring:
            self._new_game_alert('human')
        return True

    def _new_gnuchess_cb(self, button=None):
        ''' Start a new gnuchess. '''
        self._new_game_alert('new')

    def write_file(self, file_path):
        ''' Write the grid status to the Journal '''
        fd = open(file_path, 'w')
        fd.write(self._gnuchess.copy_game())
        fd.close()
        # self.metadata['saved_game'] = json_dump(self._gnuchess.save_game())
        if self.playing_white:
            self.metadata['playing_white'] = 'True'
        else:
            self.metadata['playing_white'] = 'False'
        self.metadata['playing_mode'] = self.playing_mode
        if self.playing_robot:
            self.metadata['playing_robot'] = 'True'
        else:
            self.metadata['playing_robot'] = 'False'

    def read_file(self, file_path):
        ''' Read project file on relaunch '''
        fd = open(file_path, 'r')
        self.game_data = fd.read()
        fd.close()

    def _restore(self):
        ''' Restore the gnuchess state from metadata '''
        if 'playing_white' in self.metadata:
            if self.metadata['playing_white'] == 'False':
                self.playing_white = False
                self.play_black_button.set_active(True)
        if 'playing_mode' in self.metadata:
            self.playing_mode = self.metadata['playing_mode']
            if self.playing_mode == 'hard':
                self.hard_button.set_active(True)
        if 'playing_robot' in self.metadata:
            if self.metadata['playing_robot'] == 'False':
                self.playing_robot = False
                self.human_button.set_active(True)
        self._gnuchess.restore_game(self._parse_move_list(self.game_data))
        for piece in ['white_pawn', 'black_pawn',
                      'white_rook', 'black_rook', 
                      'white_knight', 'black_knight',
                      'white_bishop', 'black_bishop', 
                      'white_queen', 'black_queen',
                      'white_king', 'black_king']:
            if piece in self.metadata:
                id = self.metadata[piece]
                jobject = datastore.get(id)
                if jobject is not None and jobject.file_path is not None:
                    self._gnuchess.reskin(piece, jobject.file_path)

    def _choose_skin(self):
        ''' Select a skin from the Journal '''
        chooser = None
        name = None
        if hasattr(mime, 'GENERIC_TYPE_IMAGE'):
            if 'image/svg+xml' not in \
                    mime.get_generic_type(mime.GENERIC_TYPE_IMAGE).mime_types:
                mime.get_generic_type(
                    mime.GENERIC_TYPE_IMAGE).mime_types.append('image/svg+xml')
            chooser = ObjectChooser(parent=self,
                                    what_filter=mime.GENERIC_TYPE_IMAGE)
        else:
            try:
                chooser = ObjectChooser(parent=self, what_filter=None)
            except TypeError:
                chooser = ObjectChooser(None, activity,
                    gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
        if chooser is not None:
            try:
                result = chooser.run()
                if result == gtk.RESPONSE_ACCEPT:
                    jobject = chooser.get_selected_object()
                    if jobject and jobject.file_path:
                        name = jobject.metadata['title']
                        mime_type = jobject.metadata['mime_type']
            finally:
                chooser.destroy()
                del chooser
            if name is not None:
                return jobject.object_id, jobject.file_path
        else:
            return None, None

    def _take_button_action(self, button):
        if button == 'black':
            self.playing_white = False
        elif button == 'white':
            self.playing_white = True
        elif button == 'easy':
            self.playing_mode = 'easy'
        elif button == 'hard':
            self.playing_mode = 'hard'
        elif button == 'robot':
            self.playing_robot = True
        elif button == 'human':
            self.playing_robot = False
        self._gnuchess.new_game()

    def _new_game_alert(self, button):
        ''' We warn the user if the game is in progress before loading
        a new game. '''
        if len(self._gnuchess.move_list) == 0:
            self._take_button_action(button)
            return

        self._restoring = True
        alert = ConfirmationAlert()
        alert.props.title = _('Game in progress.')
        alert.props.msg = _('Do you want to start a new game?')

        def _new_game_alert_response_cb(alert, response_id, self, button):
            if response_id is gtk.RESPONSE_OK:
                self._take_button_action(button)
            elif response_id is gtk.RESPONSE_CANCEL:
                if button == 'black':
                    self.play_white_button.set_active(True)
                    self.playing_white = True
                elif button == 'white':
                    self.play_black_button.set_active(True)
                    self.playing_white = False
                elif button == 'easy':
                    self.hard_button.set_active(True)
                    self.playing_mode = 'hard'
                elif button == 'hard':
                    self.easy_button.set_active(True)
                    self.playing_mode = 'easy'
                elif button == 'robot':
                    self.robot_button.set_active(False)
                    self.playing_human = False
                elif button == 'human':
                    self.robot_button.set_active(True)
                    self.playing_robot = True
            self._restoring = False
            self.remove_alert(alert)

        alert.connect('response', _new_game_alert_response_cb, self, button)
        self.add_alert(alert)
        alert.show()

    # Collaboration-related methods

    # FIXME: share mode is not set up properly

    def _setup_presence_service(self):
        ''' Setup the Presence Service. '''
        self.pservice = presenceservice.get_instance()
        self.initiating = None  # sharing (True) or joining (False)

        owner = self.pservice.get_owner()
        self.owner = owner
        self._share = ""
        self.connect('shared', self._shared_cb)
        self.connect('joined', self._joined_cb)

    def _shared_cb(self, activity):
        ''' Either set up initial share...'''
        self._new_tube_common(True)

    def _joined_cb(self, activity):
        ''' ...or join an exisiting share. '''
        self._new_tube_common(False)

    def _new_tube_common(self, sharer):
        ''' Joining and sharing are mostly the same... '''
        if self._shared_activity is None:
            _logger.debug("Error: Failed to share or join activity ... \
                _shared_activity is null in _shared_cb()")
            return

        self.initiating = sharer
        self.waiting_for_hand = not sharer

        self.conn = self._shared_activity.telepathy_conn
        self.tubes_chan = self._shared_activity.telepathy_tubes_chan
        self.text_chan = self._shared_activity.telepathy_text_chan

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'NewTube', self._new_tube_cb)

        if sharer:
            _logger.debug('This is my activity: making a tube...')
            id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
                SERVICE, {})
        else:
            _logger.debug('I am joining an activity: waiting for a tube...')
            self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
                reply_handler=self._list_tubes_reply_cb,
                error_handler=self._list_tubes_error_cb)
        self._gnuchess.set_sharing(True)

    def _list_tubes_reply_cb(self, tubes):
        ''' Reply to a list request. '''
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        ''' Log errors. '''
        _logger.debug('Error: ListTubes() failed: %s' % (e))

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        ''' Create a new tube. '''
        _logger.debug('New tube: ID=%d initator=%d type=%d service=%s \
params=%r state=%d' % (id, initiator, type, service, params, state))

        if (type == telepathy.TUBE_TYPE_DBUS and service == SERVICE):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.tubes_chan[ \
                              telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)

            tube_conn = TubeConnection(self.conn,
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES], id, \
                group_iface=self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP])

            self.chattube = ChatTube(tube_conn, self.initiating, \
                self.event_received_cb)

    def _setup_dispatch_table(self):
        ''' Associate tokens with commands. '''
        self._processing_methods = {
            'n': [self._receive_new_gnuchess, 'get a new gnuchess board'],
            }

    def event_received_cb(self, event_message):
        ''' Data from a tube has arrived. '''
        if len(event_message) == 0:
            return
        try:
            command, payload = event_message.split('|', 2)
        except ValueError:
            _logger.debug('Could not split event message %s' % (event_message))
            return
        self._processing_methods[command][0](payload)

    def send_new_gnuchess(self):
        ''' Send a new orientation, grid to all players '''
        self.send_event('n|%s' % (json_dump(self._gnuchess.save_game())))

    def _receive_new_gnuchess(self, payload):
        ''' Sharer can start a new gnuchess. '''
        self._gnuchess.restore_game(json_load(payload))

    def send_event(self, entry):
        ''' Send event through the tube. '''
        if hasattr(self, 'chattube') and self.chattube is not None:
            self.chattube.SendText(entry)


class ChatTube(ExportedGObject):
    ''' Class for setting up tube for sharing '''

    def __init__(self, tube, is_initiator, stack_received_cb):
        super(ChatTube, self).__init__(tube, PATH)
        self.tube = tube
        self.is_initiator = is_initiator  # Are we sharing or joining activity?
        self.stack_received_cb = stack_received_cb
        self.stack = ''

        self.tube.add_signal_receiver(self.send_stack_cb, 'SendText', IFACE,
                                      path=PATH, sender_keyword='sender')

    def send_stack_cb(self, text, sender=None):
        if sender == self.tube.get_unique_name():
            return
        self.stack = text
        self.stack_received_cb(text)

    @signal(dbus_interface=IFACE, signature='s')
    def SendText(self, text):
        self.stack = text
