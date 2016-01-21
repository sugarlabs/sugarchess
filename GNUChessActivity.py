#Copyright (c) 2012-14 Walter Bender
#Copyright (c) 2012 Ignacio Rodriguez
#Copyright (c) 2012 Aneesh Dogra <lionaneesh@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA

from gi.repository import Gtk, Gdk, GObject

from sugar3.activity import activity
from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.graphics.toolbarbox import ToolbarButton
from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics.objectchooser import ObjectChooser
from sugar3.graphics.menuitem import MenuItem
from sugar3.graphics.alert import ConfirmationAlert, NotifyAlert
from sugar3.graphics.icon import Icon
from sugar3.graphics.xocolor import XoColor
from sugar3.datastore import datastore
from sugar3 import mime
from sugar3 import profile

from toolbar_utils import button_factory, label_factory, separator_factory, \
    radio_factory, entry_factory
from utils import json_load, json_dump, get_hardware, \
    pixbuf_to_base64, base64_to_pixbuf

import telepathy
import dbus
from dbus.service import signal
from dbus.gobject_service import ExportedGObject
from sugar3.presence import presenceservice

try:
    from sugar3.presence.wrapper import CollabWrapper
except ImportError:
    from textchannelwrapper import CollabWrapper


from gettext import gettext as _

from chess import Gnuchess

import logging
_logger = logging.getLogger('gnuchess-activity')


SERVICE = 'org.sugarlabs.GNUChessActivity'
IFACE = SERVICE
PATH = '/org/augarlabs/GNUChessActivity'

PIECES = {'pawn': {'white': _('White Pawn'), 'black': _('Black Pawn')},
          'rook': {'white': _('White Rook'), 'black': _('Black Rook')},
          'knight': {'white': _('White Knight'), 'black': _('Black Knight')},
          'bishop': {'white': _('White Bishop'), 'black': _('Black Bishop')},
          'queen': {'white': _('White Queen'), 'black': _('Black Queen')},
          'king': {'white': _('White King'), 'black': _('Black King')}}


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
        self.buddy = None
        self.opponent_colors = None

        self.hardware = get_hardware()
        self._setup_toolbars()
        self._setup_dispatch_table()

        # Create a canvas
        canvas = Gtk.DrawingArea()
        canvas.set_size_request(Gdk.Screen.width(), Gdk.Screen.height())
        self.set_canvas(canvas)
        canvas.show()
        self.show_all()

        self.old_cursor = self.get_window().get_cursor()

        self._gnuchess = Gnuchess(canvas,
                                  parent=self,
                                  path=activity.get_bundle_path(),
                                  colors=self.colors)

        if self.shared_activity:
            # We're joining
            if not self.get_shared():
                xocolors = XoColor(profile.get_color().to_string())
                share_icon = Icon(icon_name='zoom-neighborhood',
                                  xo_color=xocolors)

                self._joined_alert = NotifyAlert()
                self._joined_alert.props.icon = share_icon
                self._joined_alert.props.title = _('Please wait')
                self._joined_alert.props.msg = _('Starting connection...')
                self._joined_alert.connect('response', self._alert_cancel_cb)
                self.add_alert(self._joined_alert)

                # Wait for joined signal
                self.connect("joined", self._joined_cb)

        self._setup_presence_service()

        self.stopwatch_running = False
        self.time_interval = None
        self.timer_panel_visible = False

        if self.game_data is not None:  # 'saved_game' in self.metadata:
            self._restore()
        else:
            self._gnuchess.new_game()
        self._restoring = False
 
    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)
    
    def restore_cursor(self):
        ''' No longer thinking, so restore standard cursor. '''
        self.get_window().set_cursor(self.old_cursor)

    def set_thinking_cursor(self):
        ''' Thinking, so set watch cursor. '''
        self.old_cursor = self.get_window().get_cursor()
        Watch = Gdk.Cursor(Gdk.CursorType.WATCH)
        self.get_window().set_cursor(Watch)

    def _setup_toolbars(self):
        ''' Setup the toolbars. '''
        self.max_participants = 2

        self.edit_toolbar = Gtk.Toolbar()
        self.view_toolbar = Gtk.Toolbar()
        self.adjust_toolbar = Gtk.Toolbar()
        self.custom_toolbar = Gtk.Toolbar()

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

        separator_factory(self.view_toolbar, False, True)

        skin_button1 = radio_factory('white-knight',
                                     self.view_toolbar,
                                     self.do_default_skin_cb,
                                     tooltip=_('Default pieces'),
                                     group=None)

        skin_button2 = radio_factory('white-knight-sugar',
                                     self.view_toolbar,
                                     self.do_sugar_skin_cb,
                                     tooltip=_('Sugar-style pieces'),
                                     group=skin_button1)
        xocolors = XoColor(self.colors)
        icon = Icon(icon_name='white-knight-sugar', xo_color=xocolors)
        icon.show()
        skin_button2.set_icon_widget(icon)

        self.skin_button3 = radio_factory('white-knight-custom',
                                          self.view_toolbar,
                                          self.do_custom_skin_cb,
                                          tooltip=_('Custom pieces'),
                                          group=skin_button1)
        skin_button1.set_active(True)

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

        separator_factory(self.adjust_toolbar, False, False)

        self.opponent = label_factory(self.adjust_toolbar, '')

        separator_factory(self.adjust_toolbar, False, True)

        self.timer_button = ToolButton('timer-0')
        self.timer_button.set_tooltip(_('Timer'))
        self.timer_button.connect('clicked', self._timer_button_cb)
        self.toolbar.insert(self.timer_button, -1)
        self._setup_timer_palette()
        self.timer_button.show()
        self.timer_button.set_sensitive(True)

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
        self.status = label_factory(self.toolbar, '', width=150)
        self.status.set_label(_("It is White's move."))

        separator_factory(toolbox.toolbar, True, False)
        stop_button = StopButton(self)
        stop_button.props.accelerator = '<Ctrl>q'
        toolbox.toolbar.insert(stop_button, -1)
        stop_button.show()

        for piece in PIECES.keys():
            for color in ['white', 'black']:
                button_factory('%s-%s' % (color, piece),
                               self.custom_toolbar,
                               self._reskin_cb,
                               cb_arg='%s_%s' % (color, piece),
                               tooltip=PIECES[piece][color])

    def do_default_skin_cb(self, button=None):
        for piece in PIECES.keys():
            for color in ['white', 'black']:
                self._gnuchess.reskin_from_file(
                    '%s_%s' % (color, piece),
                    '%s/icons/%s-%s.svg' % (activity.get_bundle_path(),
                                            color, piece))

    def _black_pieces(self, colors):
        for piece in PIECES.keys():
            self._gnuchess.reskin_from_svg('black_%s' % piece, colors,
                                           bw='#000000')

    def _white_pieces(self, colors):
        for piece in PIECES.keys():
            self._gnuchess.reskin_from_svg('white_%s' % piece, colors,
                                           bw='#ffffff')

    def do_sugar_skin_cb(self, button=None):
        colors = self.colors
        if not self._gnuchess.we_are_sharing:
            self._black_pieces(colors)
            self._white_pieces(colors)
        else:
            if self.playing_white:
                self._white_pieces(colors)
                if self.opponent_colors is not None:
                    colors = self.opponent_colors
                self._black_pieces(colors)
            else:
                self._black_pieces(colors)
                if self.opponent_colors is not None:
                    colors = self.opponent_colors
                self._white_pieces(colors)

    def do_custom_skin_cb(self, button=None):
        for piece in PIECES.keys():
            for color in ['white', 'black']:
                name = '%s_%s' % (color, piece)
                if name in self.metadata:
                    id = self.metadata[name]
                    jobject = datastore.get(id)
                    if jobject is not None and jobject.file_path is not None:
                        self._do_reskin(name, jobject.file_path)

    def _do_reskin(self, name, file_path):
        ''' If we are sharing, only reskin pieces of your color '''
        if self._gnuchess.we_are_sharing and self.buddy is not None:
            if 'white' in name and self.playing_white:
                pixbuf = self._gnuchess.reskin_from_file(
                    name, file_path, return_pixbuf=True)
                self.send_piece(name, pixbuf)
            elif 'black' in name and not self.playing_white:
                pixbuf = self._gnuchess.reskin_from_file(
                    name, file_path, return_pixbuf=True)
                self.send_piece(name, pixbuf)
        else:
            self._gnuchess.reskin_from_file(name, file_path)
        return

    def _timer_button_cb(self, button):
        if not self.timer_palette.is_up() and not self.timer_panel_visible:
            self.timer_palette.popup(
                immediate=True, state=self.timer_palette.SECONDARY)
            self.timer_panel_visible = True
        else:
            self.timer_palette.popdown(immediate=True)
            self.timer_panel_visible = False

    def _setup_timer_palette(self):
        self.timer_values = [None, 30, 180, 600]
        self.timer_tooltips = ['', _('30 seconds'), _('3 minutes'),
                               _('10 minutes')]
        self.timer_labels = [_('Disabled'),
                             #TRANS: Lightning chess 30 seconds between moves
                             _('Lightning: %d seconds') % (30),
                             #TRANS: Blitz chess 3 minutes between moves
                             _('Blitz: %d minutes') % (3),
                             #TRANS: Tournament chess 10 minutes between moves
                             _('Tournament: %d minutes') % (10)]
        self.timer_palette = self.timer_button.get_palette()

        for i, label in enumerate(self.timer_labels):
            menu_item = MenuItem(icon_name='timer-%d' % (i),
                                 text_label=label)
            menu_item.connect('activate', self._timer_selected_cb, i)
            self.timer_palette.menu.append(menu_item)
            menu_item.show()

    def _timer_selected_cb(self, button, index):
        game_already_started = 0
        if self.time_interval is not None:
            game_already_started = 1

        self.time_interval = self.timer_values[index]
        if self.time_interval is None:
            self.timer_button.set_tooltip(_('Timer off'))
        else:
            self.timer_button.set_tooltip(
                _('Timer') + ' (' + self.timer_tooltips[index] + ')')
            if game_already_started:
                self.alert_reset(self.timer_labels[index])
                if self.time_interval and self.time_interval is not None:
                    self.stopwatch(self.time_interval, self.alert_time)
                else:
                    GObject.source_remove(self.stopwatch_timer)
            else:
                self._gnuchess.new_game()

    def _reskin_cb(self, button, piece):
        object_id, file_path = self._choose_skin()
        if file_path is not None:
            self._do_reskin(piece, file_path)
            self.metadata[piece] = str(object_id)

    def do_fullscreen_cb(self, button):
        ''' Hide the Sugar toolbars. '''
        self.fullscreen()

    def _play_history_cb(self, button):
        self._gnuchess.play_game_history()
        return

    def _show_history_cb(self, button):
        self._gnuchess.show_game_history(self.tag_pairs())
        if self.showing_game_history:
            self.history_button.set_icon('checkerboard')
            self.history_button.set_tooltip(_('Show game board'))
        else:
            self.history_button.set_icon('list-numbered')
            self.history_button.set_tooltip(_('Show game history'))
        return

    def _copy_cb(self, *args):
        clipboard = Gtk.Clipboard()
        clipboard.set_text(self.tag_pairs() + self._gnuchess.copy_game())

    def _paste_cb(self, *args):
        ''' Pasting '''
        clipboard = Gtk.Clipboard()
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
        # No undo while sharing
        if self.initiating is None:
            self._gnuchess.undo()

    def _hint_cb(self, *args):
        self._gnuchess.hint()

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

    def tag_pairs(self):
        ''' Tag paris must be ascii '''
        if type(self.nick) == unicode:
            nick = self.nick.encode('ascii', 'replace')
        else:
            nick = self.nick
        if self.buddy is not None and type(self.buddy) == unicode:
            buddy = self.buddy.encode('ascii', 'replace')
        else:
            buddy = self.buddy
        if self.playing_white:
            white = nick
            if self.playing_robot:
                black = 'gnuchess (%s)' % (self.playing_mode)
            elif self._gnuchess.we_are_sharing and buddy is not None:
                black = buddy
            else:
                black = '?'
        else:
            black = nick
            if self.playing_robot:
                white = 'gnuchess (%s)' % (self.playing_mode)
            elif self._gnuchess.we_are_sharing and buddy is not None:
                white = buddy
            else:
                white = '?'
        return '[White "%s"]\n[Black "%s"]\n\n' % (white, black)

    def write_file(self, file_path):
        ''' Write the grid status to the Journal '''
        fd = open(file_path, 'w')
        fd.write(self.tag_pairs())
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

        '''
        self.metadata['timer_mode'] = self.timer.get_active_text()
        '''

    def read_file(self, file_path):
        ''' Read project file on relaunch '''
        fd = open(file_path, 'r')
        self.game_data = fd.read()
        fd.close()
        _logger.debug(self.game_data)

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
        '''
        if 'timer_mode' in self.metadata:
            self.timer_intervale.set_active(self.timer_list.index(
                                            self.metadata['timer_mode']))
        '''

        self._gnuchess.restore_game(self._parse_move_list(self.game_data))
        self.do_custom_skin_cb()

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
                chooser = ObjectChooser(
                    None, activity,
                    Gtk.DialogType.MODAL | Gtk.DialogType.DESTROY_WITH_PARENT)
        if chooser is not None:
            try:
                result = chooser.run()
                if result == Gtk.Responsetype.ACCEPT:
                    jobject = chooser.get_selected_object()
                    if jobject and jobject.file_path:
                        name = jobject.metadata['title']
            finally:
                jobject.destroy()
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

    def _no_action(self, button):
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
            self.human_button.set_active(True)
            self.playing_robot = False
        elif button == 'human':
            self.robot_button.set_active(True)
            self.playing_robot = True

    def _new_game_alert(self, button):
        ''' We warn the user if the game is in progress before loading
        a new game. '''
        if self.initiating is not None and not self.initiating:
            # joiner cannot push buttons
            self._restoring = True
            self._no_action(button)
            self._restoring = False
            return

        if len(self._gnuchess.move_list) == 0:
            self._take_button_action(button)
            return

        self._restoring = True
        alert = ConfirmationAlert()
        alert.props.title = _('Game in progress.')
        alert.props.msg = _('Do you want to start a new game?')

        def _new_game_alert_response_cb(alert, response_id, self, button):
            if response_id is Gtk.ResponseType.OK:
                self._take_button_action(button)
            elif response_id is Gtk.ResponseType.CANCEL:
                self._no_action(button)
            self._restoring = False
            self.remove_alert(alert)

        alert.connect('response', _new_game_alert_response_cb, self, button)
        self.add_alert(alert)
        alert.show()

    # Collaboration-related methods

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

        self.conn = self._shared_activity.telepathy_conn
        self.tubes_chan = self._shared_activity.telepathy_tubes_chan
        self.text_chan = self._shared_activity.telepathy_text_chan

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'NewTube', self._new_tube_cb)

        if sharer:
            _logger.debug('This is my activity: making a tube...')
            self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
                SERVICE, {})
        else:
            _logger.debug('I am joining an activity: waiting for a tube...')
            self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
                reply_handler=self._list_tubes_reply_cb,
                error_handler=self._list_tubes_error_cb)

        self._gnuchess.set_sharing(True)
        self.restoring = True
        self.playing_robot = False
        self.human_button.set_active(True)
        self.restoring = False

        self.easy_button.set_sensitive(False)
        self.hard_button.set_sensitive(False)
        self.robot_button.set_sensitive(False)

    def _list_tubes_reply_cb(self, tubes):
        ''' Reply to a list request. '''
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        ''' Log errors. '''
        _logger.debug('Error: ListTubes() failed: %s' % (e))

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        ''' Create a new tube. '''
        _logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                      'params=%r state=%d' %
                      (id, initiator, type, service, params, state))

        if (type == telepathy.TUBE_TYPE_DBUS and service == SERVICE):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.tubes_chan[
                    telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)

            self.collab = CollabWrapper(self)
            self.collab.message.connect(self.event_received_cb)
            self.collab.setup()

        # Now that we have a tube, send the nick to our opponent
        if not self.initiating:
            self.send_nick()
            # And let the sharer know we've joined
            self.send_join()

    def _setup_dispatch_table(self):
        ''' Associate tokens with commands. '''
        self._processing_methods = {
            'n': [self._receive_new_game, 'start a new game'],
            'm': [self._receive_move, 'make a move'],
            'r': [self._receive_restore, 'restore game state'],
            'N': [self._receive_nick, 'receive nick from opponent'],
            'C': [self._receive_colors, 'receive colors from opponent'],
            'j': [self._receive_join, 'receive new joiner'],
            'p': [self._receive_piece, 'receive new piece'],
            }

    def event_received_cb(self, collab, buddy, msg):
        ''' Data from a tube has arrived. '''
        command = msg.get("command")
        if action is None:
            return

        payload = msg.get("payload")
        self._processing_methods[command][0](payload)

    def send_new_game(self):
        ''' Send a new game to joiner. '''
        if not self.initiating:
            return
        self.send_nick()
        if self.playing_white:
            _logger.debug('send_new_game: B')
            self.send_event("n", "B")
        else:
            _logger.debug('send_new_game: W')
            self.send_event("n", "W")

    def send_restore(self):
        ''' Send a new game to joiner. '''
        if not self.initiating:
            return
        _logger.debug('send_restore')
        self.send_event("r", self._gnuchess.copy_game())

    def send_join(self):
        _logger.debug('send_join')
        self.send_event("j", self.nick)

    def send_nick(self):
        _logger.debug('send_nick')
        self.send_event("N", self.nick)
        self.send_event("C", "%s,%s" % (self.colors[0], self.colors[1]))

    def alert_time(self):
        def _alert_response_cb(alert, response_id):
            self.remove_alert(alert)

        alert = NotifyAlert()
        alert.props.title = _('Time Up!')
        alert.props.msg = _('Your time is up.')
        alert.connect('response', _alert_response_cb)
        alert.show()
        self.add_alert(alert)

    def alert_reset(self, mode):
        def _alert_response_cb(alert, response_id):
            self.remove_alert(alert)

        alert = NotifyAlert()
        alert.props.title = _('Time Reset')
        alert.props.msg = _('The timer mode was reset to %s' % mode)
        alert.connect('response', _alert_response_cb)
        alert.show()
        self.add_alert(alert)

    def stopwatch(self, time, alert_callback):
        if self.stopwatch_running:
            GObject.source_remove(self.stopwatch_timer)
            time = self.time_interval
        self.stopwatch_timer = GObject.timeout_add(time * 1000, alert_callback)
        self.stopwatch_running = True

    def _receive_join(self, payload):
        _logger.debug('received_join %s' % (payload))
        if self.initiating:
            self.send_new_game()
            _logger.debug(self.game_data)
            if self.game_data is not None:
                self.send_restore()

    def _receive_nick(self, payload):
        _logger.debug('received_nick %s' % (payload))
        self.buddy = payload
        self.opponent.set_label(self.buddy)
        if self.initiating:
            self.send_nick()

    def _receive_colors(self, payload):
        _logger.debug('received_colors %s' % (payload))
        self.opponent_colors = payload.split(',')
        xocolors = XoColor(payload)
        icon = Icon(icon_name='human', xo_color=xocolors)
        icon.show()
        self.human_button.set_icon_widget(icon)
        self.human_button.show()

    def _receive_restore(self, payload):
        ''' Get game state from sharer. '''
        if self.initiating:
            return
        _logger.debug('received_restore %s' % (payload))
        self._gnuchess.restore_game(self._parse_move_list(payload))

    def _receive_move(self, payload):
        ''' Get a move from opponent. '''
        _logger.debug('received_move %s' % (payload))
        self._gnuchess.remote_move(payload)

    def _receive_new_game(self, payload):
        ''' Sharer can start a new gnuchess. '''
        _logger.debug('received_new_game %s' % (payload))
        if self.initiating:
            return
        self.send_nick()
        if payload == 'W':
            if not self.playing_white:
                self.restoring = True
                self.play_black_button.set_active(False)
                self.play_white_button.set_active(True)
                self.playing_white = True
        else:
            if self.playing_white:
                self.restoring = True
                self.play_white_button.set_active(False)
                self.play_black_button.set_active(True)
                self.playing_white = False
        self.robot_button.set_active(False)
        self.human_button.set_active(True)
        self.playing_robot = False
        self.restoring = False
        self._gnuchess.set_sharing(True)
        self._gnuchess.new_game()

    def send_event(self, command, payload):
        ''' Send event through the tube. '''
        if hasattr(self, 'collab') and self.collab is not None:
            self.collab.post(dict(
                command=command,
                payload=payload
            ))

    # sharing pieces

    def send_piece(self, piece, pixbuf):
        _logger.debug('send_piece %s' % (piece))
        GObject.idle_add(self.send_event, ("p", self._dump(piece, pixbuf)))

    def _receive_piece(self, payload):
        piece, pixbuf = self._load(payload)
        _logger.debug('received_piece %s' % (piece))
        self._gnuchess.reskin(piece, pixbuf)

    def _dump(self, piece, pixbuf):
        ''' Dump data for sharing.'''
        _logger.debug('dumping %s' % (piece))
        data = [piece, pixbuf_to_base64(activity, pixbuf)]
        return json_dump(data)

    def _load(self, data):
        ''' Load game data from the journal. '''
        piece, pixbuf_data = json_load(data)
        pixbuf = base64_to_pixbuf(activity,
                                  pixbuf_data,
                                  width=self._gnuchess.scale,
                                  height=self._gnuchess.scale)
        return piece, pixbuf

