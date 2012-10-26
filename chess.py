# -*- coding: utf-8 -*-
#Copyright (c) 2012 Walter Bender
#Copyright (c) 2012 Ignacio Rodriguez

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
import cairo
import os
import subprocess
from string import find

from random import uniform

from gettext import gettext as _

import logging
_logger = logging.getLogger('gnuchess-activity')

from sprites import Sprites, Sprite
from piece import svg_header, svg_footer, svg_king, svg_queen, svg_bishop, \
    svg_knight, svg_rook, svg_pawn

ROBOT_MOVE = 'My move is : '
TOP = 3
MID = 2
BOT = 1
STATUS = 'status'
ROBOT = 'robot'
RESTORE = 'restore'
REMOVE = 'remove'
UNDO = 'undo'
HINT = 'hint'
GAME = 'game'
NEW = 'new'
# Skin indicies
WP = 0
BP = 1
WR = 2
BR = 3
WN = 4
BN = 5
WB = 6
BB = 7
WQ = 8
BQ = 9
WK = 10
BK = 11
FILES = 'abcdefgh'
RANKS = '12345678'
BIN = {'i686': 'i686', 'i586': 'i686', 'armv7l': 'armv7l'}


class Gnuchess():

    def __init__(self, canvas, parent=None, path=None,
                 colors=['#A0FFA0', '#FF8080']):
        self._activity = parent
        self._bundle_path = path
        self._bin_path = 'bin/i686'
        self._colors = ['#FFFFFF']
        self._colors.append(colors[0])
        self._colors.append(colors[1])
        self._colors.append('#000000')

        self._canvas = canvas
        if parent is not None:
            parent.show_all()
            self._parent = parent

        self._canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._canvas.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK)
        self._canvas.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self._canvas.connect("draw", self.__draw_cb)
        self._canvas.connect("button-press-event", self._button_press_cb)
        self._canvas.connect("button-release-event", self._button_release_cb)
        self._canvas.connect("motion-notify-event", self._mouse_move_cb)

        self._width = Gdk.Screen.width()
        self._height = Gdk.Screen.height()
        self.scale = int((self._height - 55) / 10)
        self.we_are_sharing = False

        self.move_list = []
        self.game = ''

        self._press = None
        self._release = None
        self._dragpos = [0, 0]
        self._total_drag = [0, 0]
        self._last_piece_played = [None, (0, 0)]

        self._thinking = False
        self._move = 0
        self._counter = 0
        self.check = False
        self.checkmate = False

        self.white = []
        self.black = []
        self._board = []
        self._squares = []
        self._output = ''
        self._before = []
        self._after = []

        self.skins = []

        # Generate the sprites we'll need...
        self._sprites = Sprites(self._canvas)
        self._generate_sprites(colors)

        p = subprocess.Popen(['uname', '-p'],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        self._bin_path = 'bin/%s' % (BIN[p.communicate()[0].replace('\n', '')])
        self._all_clear()

    def move(self, my_move):
        ''' Send a command to gnuchess. '''
        # Permisos para jugar
	os.system('chmod -R 755 bin')
        p = subprocess.Popen(['%s/%s/gnuchess' % (self._bundle_path,
                                                   self._bin_path)],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)

        if my_move == HINT:
            level = 'hard\nbook on\n'  # may as well get a good hint
        elif self._activity.playing_mode == 'easy':
            level = 'easy\nbook off\ndepth 1\n'
        else:
            level = 'hard\nbook on\n'

        if my_move in [REMOVE, UNDO, RESTORE, HINT, GAME, NEW]:
            hint = False
            if my_move == REMOVE:
                self.move_list = self.move_list[:-2]
            elif my_move == UNDO:
                self.move_list = self.move_list[:-1]
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            if my_move == HINT:
                cmd += '%sgo\nquit\n' % (level)
                hint = True
            elif my_move == GAME:
                cmd += 'show game\nquit\n'
            else:
                cmd += 'show board\nquit\n'
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=None, hint=hint)
        elif my_move == ROBOT:  # Ask the computer to play
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += '%sgo\nshow board\nquit\n' % (level)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move='robot')
        elif my_move == STATUS:  # reading board state
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += 'show board\nquit\n'
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=STATUS)
        elif my_move is not None:  # human's move
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += '%s\n' % (my_move)
            cmd += 'show board\nquit\n'
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=my_move)

    def _process_output(self, output, my_move=None, hint=False):
        ''' process output from gnuchess command '''
        self.check = False
        self.checkmate = False
        if my_move == STATUS:  # Just reading board state
            self._output = output
            return
        elif 'White   Black' in output:  # processing show game
            target = 'White   Black'
            output = output[find(output, target):]
            self.game = output[:find(output, '\n\n')]
            return
        elif hint:  # What would the robot do?
            output = output[find(output, ROBOT_MOVE):]
            hint = output[len(ROBOT_MOVE):find(output, '\n')]
            self._activity.status.set_label(hint)
            self._parse_move(hint)
            self._thinking = False
            self._activity.restore_cursor()
            return
        elif 'Illegal move' in output:
            self._activity.status.set_label(_('Illegal move'))
            if self._last_piece_played[0] is not None:
                self._last_piece_played[0].move(self._last_piece_played[1])
                self._last_piece_played[0] = None
        elif my_move == ROBOT:
            if 'wins' in output or 'loses' in output:
                self.checkmate = True
            output = output[find(output, ROBOT_MOVE):]
            robot_move = output[len(ROBOT_MOVE):find(output, '\n')]
            self.move_list.append(robot_move)
            if '+' in robot_move:
                self.check = True
            if '#' in robot_move or '++' in robot_move:
                self.checkmate = True
            if self._activity.playing_white:
                self._activity.black_entry.set_text(robot_move)
                self._activity.white_entry.set_text('')
            else:
                self._activity.white_entry.set_text(robot_move)
                self._activity.black_entry.set_text('')
            self._thinking = False
            self._activity.restore_cursor()
        elif my_move is not None:
            if 'wins' in output or 'loses' in output:
                self.checkmate = True
            self.move_list.append(my_move)
            if self._activity.playing_white:
                self._activity.white_entry.set_text(my_move)
                self._activity.black_entry.set_text('')
            else:
                self._activity.black_entry.set_text(my_move)
                self._activity.white_entry.set_text('')

        if len(self.move_list) % 2 == 0:
            target = 'white  '
        else:
            target = 'black  '
        while find(output, target) > 0:
            output = output[find(output, target):]
            output = output[find(output, '\n'):]
        if len(output) < 136 or output[0:3] == 'GNU':
            self._activity.status.set_label('???')
        else:
            self._load_board(output)

        if self.checkmate or self.check:
            if self.check:
                self._activity.status.set_label(_('Check'))
            else:
                self._activity.status.set_label(_('Checkmate'))
            if len(self.move_list) % 2 == 0:
                self._flash_tile([self._xy_to_file_and_rank(
                            self.white[4].get_xy())])
            else:
                self._flash_tile([self._xy_to_file_and_rank(
                            self.black[4].get_xy())])
        else:
            if len(self.move_list) % 2 == 0:
                self._activity.status.set_label(_("It is White's move."))
            else:
                self._activity.status.set_label(_("It is Black's move."))

    def _all_clear(self):
        ''' Things to reinitialize when starting up a new game. '''
        for i in range(3):
            self.bg[i].set_layer(-1)
            self.bg[i].set_label('')
        self.move_list = []
        self.game = ''
        self.check = False
        self.checkmate = False

    def new_game(self):
        self._all_clear()
        self.move(NEW)
        if self._activity.playing_robot and not self._activity.playing_white:
            self.move(ROBOT)

        if self.we_are_sharing and self._activity.initiating:
            self._activity.send_new_game()

    def restore_game(self, move_list):
        self.move_list = []

        for move in move_list:
            self.move_list.append(str(move))

        self.move(RESTORE)

        if len(self.move_list) > 0:
            if '#' in self.move_list[-1] or '++' in self.move_list[-1]:
                if len(self.move_list) % 2 == 0:
                    self._activity.status.set_label(_('Black wins.'))
                else:
                    self._activity.status.set_label(_('White wins.'))
            elif '+' in self.move_list[-1]:
                if len(self.move_list) % 2 == 0:
                    self._activity.status.set_label(
                        _("White's King is in check."))
                else:
                    self._activity.status.set_label(
                        _("Black's King is in check."))

        if self.we_are_sharing and self._activity.initiating:
            self._activity.send_restore()

    def copy_game(self):
        self.move(GAME)
        return self.game

    def save_game(self):
        return self.move_list

    def show_game_history(self, tag_pairs):
        if not self._activity.showing_game_history:
            for i in range(3):
                self.bg[i].set_layer(TOP)
            self.move(GAME)
            # Split into two columns
            if ' 14.' in self.game:
                i = self.game.index(' 14.')
                self.bg[0].set_label(tag_pairs + self.game[: i - 1])
                if '31.' in self.game:
                    j = self.game.index('31.')
                    self.bg[1].set_label(self.game[i: j - 1])
                    self.bg[2].set_label(self.game[j:])
                else:
                    self.bg[1].set_label(self.game[i:])
            else:
                self.bg[0].set_label(self.game)
            self._activity.showing_game_history = True
        else:
            for i in range(3):
                self.bg[i].set_layer(-1)
                self.bg[i].set_label('')
            self._activity.showing_game_history = False

    def play_game_history(self):
        self._counter = 0
        self._copy_of_move_list = self.move_list[:]
        self._all_clear()
        self._stepper()

    def _stepper(self):
        if self._counter < len(self._copy_of_move_list):
            self.move(self._copy_of_move_list[self._counter])
            self._counter += 1
            GObject.timeout_add(2000, self._stepper)

    def _button_press_cb(self, win, event):
        win.grab_focus()
        x, y = map(int, event.get_coords())

        self._dragpos = [x, y]
        self._total_drag = [0, 0]

        spr = self._sprites.find_sprite((x, y))
        if spr == None or spr.type == None:
            return

        if self._thinking:  # Robot is thinking or conjuring up a hint
            self._wait_your_turn()
            return
        elif self.we_are_sharing:
            if not self._activity.playing_white and \
               len(self.move_list) % 2 == 0:
                self._wait_your_turn()
                return
            elif self._activity.playing_white and \
                 len(self.move_list) % 2 == 1:
                self._wait_your_turn() 
                return

        # Only play your color
        if self._activity.playing_robot or self.we_are_sharing:
            if self._activity.playing_white and spr.type[0] in 'prnbqk':
                self._play_your_color()
                return
            elif not self._activity.playing_white and spr.type[0] in 'PRNBQK':
                self._play_your_color()
                return
        else:
            if len(self.move_list) % 2 == 0 and spr.type[0] in 'prnbqk':
                self._play_your_color()
                return
            elif len(self.move_list) % 2 == 1 and spr.type[0] in 'PRNBQK':
                self._play_your_color()
                return

        self._release = None
        self._press = spr
        self._press.set_layer(TOP)
        self._last_piece_played = [spr, spr.get_xy()]
        return True

    def _wait_your_turn(self):
        if self._activity.playing_white:
            self._activity.status.set_label(
                _('Please wait for your turn.'))
        else:
            self._activity.status.set_label(
                _('Please wait for your turn.'))

    def _play_your_color(self):
        if self._activity.playing_white:
            self._activity.status.set_label(_('Please play White.'))
        else:
            self._activity.status.set_label(_('Please play Black.'))

    def _mouse_move_cb(self, win, event):
        """ Drag a tile with the mouse. """
        spr = self._press
        if spr is None:
            self._dragpos = [0, 0]
            return True
        win.grab_focus()
        x, y = map(int, event.get_coords())
        dx = x - self._dragpos[0]
        dy = y - self._dragpos[1]
        spr.move_relative([dx, dy])
        self._dragpos = [x, y]
        self._total_drag[0] += dx
        self._total_drag[1] += dy
        return True

    def _button_release_cb(self, win, event):
        win.grab_focus()

        self._dragpos = [0, 0]

        if self._press is None:
            return

        x, y = map(int, event.get_coords())
        spr = self._sprites.find_sprite((x, y))

        self._release = spr
        self._release.set_layer(MID)
        self._press = None
        self._release = None

        g1 = self._xy_to_file_and_rank(self._last_piece_played[1])
        g2 = self._xy_to_file_and_rank((x, y))
        if g1 == g2:  # We'll let beginners touch a piece and return it.
            spr.move(self._last_piece_played[1])
            return True

        move = '%s%s' % (g1, g2)

        # Queen a pawn (FIXME: really should be able to choose any piece)
        if spr.type == 'p' and g2[1] == '1':
            move += 'Q'
        elif spr.type == 'P' and g2[1] == '8':
            move += 'Q'

        if len(self.move_list) % 2 == 0:
            self._activity.white_entry.set_text(move)
        else:
            self._activity.black_entry.set_text(move)
        self._activity.status.set_label('making a move %s' % (move))
        self.move(move)

        # Get game notation from last move to share and to check for
        # check, checkmate
        self.move(GAME)
        if self.game == '':
            _logger.debug('bad move: reseting')
            return True
        last_move = self.game.split()[-1]
        if self.we_are_sharing:
            self._activity.send_event('m|%s' % (last_move))
        if '+' in last_move:
            self.check = True
            self._activity.status.set_label(_('Check'))
        if '#' in last_move or '++' in last_move:
            self.checkmate = True
            self._activity.status.set_label(_('Checkmate'))

        if self.checkmate or self.check:
            if self.check:
                self._activity.status.set_label(_('Check'))
            else:
                self._activity.status.set_label(_('Checkmate'))
            if len(self.move_list) % 2 == 0:
                self._flash_tile([self._xy_to_file_and_rank(
                            self.white[4].get_xy())])
            else:
                self._flash_tile([self._xy_to_file_and_rank(
                            self.black[4].get_xy())])

        # Check to see if it is the robot's turn
        if self._activity.playing_robot and \
           self._activity.playing_white and \
           len(self.move_list) % 2 == 0:
            _logger.debug("not the robot's turn")
            return True
        if self._activity.playing_robot and \
           not self._activity.playing_white and \
           len(self.move_list) % 2 == 1:
            _logger.debug("not the robot's turn")
            return True
        if self._activity.playing_robot and not self.checkmate:
            self._activity.set_thinking_cursor()
            self._activity.status.set_label(_('Thinking...'))
            self._thinking = True
            self._get_before()
            GObject.timeout_add(500, self._robot_move)

        return True

    def _robot_move(self):
        self.move(ROBOT)
        # Flash the squares of any piece that robot has moved
        self._get_after()
        pieces = []  # Array, since if could be a castling move
        before = []
        after = []
        for i in range(64):
            if self._before[i] != self._after[i]:
                if self._activity.playing_white and \
                   self._before[i] in 'prnbqk':
                    pieces.append(self._before[i])
                    before.append(i)
                elif not self._activity.playing_white and \
                     self._before[i] in 'PRNBQK':
                    pieces.append(self._before[i])
                    before.append(i)
                if self._activity.playing_white and \
                   self._after[i] in 'prnbqk':
                    pieces.append(self._after[i])
                    after.append(i)
                elif not self._activity.playing_white and \
                     self._after[i] in 'PRNBQK':
                    pieces.append(self._after[i])
                    after.append(i)
        tiles = []
        for i in range(len(before)):
            tiles.append(self._index_to_file_and_rank(before[i]))
            tiles.append(self._index_to_file_and_rank(after[i]))
        self._flash_tile(tiles, flash_color=3)

    def _get_before(self):
        self.move(STATUS)
        if self._activity.playing_white:
            tmp = self._output.split('Black')
        else:
            tmp = self._output.split('White')
        self._before = tmp[-2][-137:].split()

    def _get_after(self):
        self.move(STATUS)
        if self._activity.playing_white:
            tmp = self._output.split('White')
        else:
            tmp = self._output.split('Black')
        self._after = tmp[-2][-137:].split()

    def undo(self):
        # TODO: Lock out while robot is playing
        if self._activity.playing_robot and len(self.move_list) > 1:
            if self._activity.playing_white:
                if len(self.move_list) % 2 == 0:
                    self.move(REMOVE)
                else:
                    self.move(UNDO)
            else:
                if len(self.move_list) % 2 == 1:
                    self.move(REMOVE)
                else:
                    self.move(UNDO)
        elif len(self.move_list) > 0:
            self.move(UNDO)

    def hint(self):
        # TODO: Lock out while robot is playing
        if self._thinking:
            self._activity.status.set_label(_('Please wait for your turn.'))
            return
        self._activity.set_thinking_cursor()
        self._activity.status.set_label(_('Thinking'))
        self._thinking = True
        GObject.timeout_add(500, self.move, HINT)

    def _flash_tile(self, tiles, flash_color=2):
        self._counter = 0
        GObject.timeout_add(100, self._flasher, tiles, flash_color)
        return

    def _flasher(self, tiles, flash_color):
        # flash length (must be odd in order to guarentee that the
        # original color is restored)
        if self._counter < 13:
            self._counter += 1
            for tile in tiles:
                i = self._file_and_rank_to_index(tile)
                if self._counter % 2 == 0:
                    self._board[i].set_image(self._squares[flash_color])
                else:
                    self._board[i].set_image(self._squares[black_or_white(i)])
                self._board[i].set_layer(BOT)
            GObject.timeout_add(200, self._flasher, tiles, flash_color)

    def _parse_move(self, move):
        tiles = []
        label = move
        source_file = None
        source_rank = None
        capture_piece = None
        capture_file = None
        capture_rank = None
        if 'x' in move:
            capture = True
        else:
            capture = False
        if len(self.move_list) % 2 == 0:
            white = True
            if move[0] in FILES:
                piece = 'P'
                source_file = move[0]
                if move[1] in RANKS:
                    source_rank = move[1]
            elif move[0] == 'O':
                if move == 'O-O':
                    tiles.append('e1')
                    tiles.append('g1')
                else:  # O-O-O
                    tiles.append('c1')
                    tiles.append('e1')
                self._flash_tile(tiles)
                return
            else:
                piece = move[0]
                if move[1] in FILES:
                    source_file = move[1]
                    if move[2] in RANKS:
                        source_rank = move[2]
                elif move[1] in RANKS:
                    source_rank = move[1]
                if source_rank is None or source_file is None:
                    if move[2] in FILES:
                        capture_file = move[2]
                        if len(move) > 3:
                            if move[3] in RANKS:
                                capture_rank = move[3]
        else:
            white = False
            if move[0] in FILES:
                piece = 'p'
                source_file = move[0]
                if move[1] in RANKS:
                    source_rank = move[1]
            elif move[0] == 'O':
                if move == 'O-O':
                    tiles.append('e8')
                    tiles.append('g8')
                else:  # O-O-O
                    tiles.append('c8')
                    tiles.append('e8')
                self._flash_tile(tiles)
                return
            else:
                piece = move[0]
                if move[1] in FILES:
                    source_file = move[1]
                    if move[2] in RANKS:
                        source_rank = move[2]
                elif move[1] in RANKS:
                    source_rank = move[1]
                if source_rank is None or source_file is None:
                    if move[2] in FILES:
                        capture_file = move[2]
                        if len(move) > 3:
                            if move[3] in RANKS:
                                capture_rank = move[3]
        if capture:
            move = move[find(move, 'x') + 1:]
            if white:
                if move[0] in 'KQBNR':
                    capture_piece = move[0]
                    if len(move) > 1:
                        if move[1] in FILES:
                            capture_file = move[1]
                            if len(move) > 2:
                                if move[2] in RANKS:
                                    capture_rank = move[2]
                        elif move[1] in RANKS:
                            capture_rank = move[1]
                else:
                    capture_piece = 'p'
                    if move[0] in FILES:
                        capture_file = move[0]
                        if len(move) > 1:
                            if move[1] in RANKS:
                                capture_rank = move[1]
                    elif move[0] in RANKS:
                        capture_rank = move[0]
            else:
                if move[0] in 'KQBNR':
                    capture_piece = move[0]
                    if len(move) > 1:
                        if move[1] in FILES:
                            capture_file = move[1]
                            if len(move) > 2:
                                if move[2] in RANKS:
                                    capture_rank = move[2]
                        elif move[1] in RANKS:
                            capture_rank = move[1]
                else:
                    capture_piece = 'P'
                    if move[0] in FILES:
                        capture_file = move[0]
                        if len(move) > 1:
                            if move[1] in RANKS:
                                capture_rank = move[1]
                    elif move[0] in RANKS:
                        capture_rank = move[0]

        if capture_file is None:
            capture_file = source_file
        if capture_rank is None:
            capture_rank = source_rank
        if source_file is None:
            source_file = capture_file
        if source_rank is None:
            source_rank = capture_rank

        if piece in 'pP':
            source_file, source_rank = self._search_for_pawn(
                piece, source_file, source_rank, capture_file, capture_rank,
                capture=capture)
        elif piece in 'rR':
            source_file, source_rank = self._search_for_rook(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'nN':
            source_file, source_rank = self._search_for_knight(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'bB':
            source_file, source_rank = self._search_for_bishop(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'qQ':
            source_file, source_rank = self._search_for_queen(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'kK':
            source_file, source_rank = self._search_for_king(
                piece, source_file, source_rank, capture_file, capture_rank)
        tiles.append('%s%s' % (source_file, source_rank))
        tiles.append('%s%s' % (capture_file, capture_rank))
        self._flash_tile(tiles)

    def _search_for_pawn(
        self, piece, source_file, source_rank, capture_file, capture_rank,
        capture=False):
        # Check for capture
        if capture and len(self.move_list) % 2 == 0:
            if source_file == capture_file:
                f = FILES.index(capture_file)
                if f > 0:
                    i = self._file_and_rank_to_index('%s%s' % (
                            FILES[f - 1], RANKS[RANKS.index(capture_rank) - 1]))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.white[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f - 1], \
                                   RANKS[RANKS.index(capture_rank) - 1]
                if f < 7:
                    i = self._file_and_rank_to_index('%s%s' % (
                            FILES[f + 1], RANKS[RANKS.index(capture_rank) - 1]))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.white[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f + 1], \
                                   RANKS[RANKS.index(capture_rank) - 1]
            else:
                i = self._file_and_rank_to_index('%s%s' % (
                        source_file, RANKS[RANKS.index(capture_rank) - 1]))
                x, y = self._index_to_xy(i)
                for p in range(8):
                    pos = self.white[8 + p].get_xy()
                    if x == pos[0] and y == pos[1]:
                        return source_file, \
                               RANKS[RANKS.index(capture_rank) - 1]
        elif capture:
            if source_file == capture_file:
                f = FILES.index(capture_file)
                if f > 0:
                    i = self._file_and_rank_to_index('%s%s' % (
                            FILES[f - 1], RANKS[RANKS.index(capture_rank) + 1]))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.black[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f - 1], \
                                   RANKS[RANKS.index(capture_rank) + 1]
                if f < 7:
                    i = self._file_and_rank_to_index('%s%s' % (
                            FILES[f + 1], RANKS[RANKS.index(capture_rank) + 1]))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.black[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f + 1], \
                                   RANKS[RANKS.index(capture_rank) + 1]
            else:
                i = self._file_and_rank_to_index('%s%s' % (
                        source_file, RANKS[RANKS.index(capture_rank) + 1]))
                x, y = self._index_to_xy(i)
                for p in range(8):
                    pos = self.black[8 + p].get_xy()
                    if x == pos[0] and y == pos[1]:
                        return source_file, \
                               RANKS[RANKS.index(capture_rank) + 1]
        # Check for first move
        if piece == 'p' and capture_rank == '5':
            i = self._file_and_rank_to_index('%s7' % (capture_file))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.black[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, '7'
        elif piece == 'P' and capture_rank == '4':
            i = self._file_and_rank_to_index('%s2' % (capture_file))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.white[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, '2'
        # Check for previous space
        if piece == 'p':
            i = self._file_and_rank_to_index('%s%s' % (
                    capture_file, RANKS[RANKS.index(capture_rank) + 1]))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.black[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, RANKS[RANKS.index(capture_rank) + 1]
        elif piece == 'P':
            i = self._file_and_rank_to_index('%s%s' % (
                    capture_file, RANKS[RANKS.index(capture_rank) - 1]))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.white[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, RANKS[RANKS.index(capture_rank) - 1]
        return capture_file, capture_rank

    def _search_for_rook(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        # Change rank
        if len(self.move_list) % 2 == 1:
            for r in range(7 - RANKS.index(capture_rank)):
                i = self._file_and_rank_to_index('%s%s' % (
                        capture_file, RANKS[RANKS.index(capture_rank) + r + 1]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'rR' and (b == 0 or b == 7):
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) + r + 1]
                    elif piece in 'qQ' and b == 3:
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) + r + 1]
                    else:
                        break
                elif p is not None:
                    break
            for r in range(RANKS.index(capture_rank)):
                i = self._file_and_rank_to_index('%s%s' % (
                        capture_file, RANKS[RANKS.index(capture_rank) - r - 1]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'rR' and (b == 0 or b == 7):
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) - r - 1]
                    elif piece in 'qQ' and b == 3:
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) - r - 1]
                    else:
                        break
                elif p is not None:
                    break
        else:
            for r in range(7 - RANKS.index(capture_rank)):
                i = self._file_and_rank_to_index('%s%s' % (
                        capture_file, RANKS[RANKS.index(capture_rank) + r + 1]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) + r + 1]
                    elif piece == 'Q' and w == 3:
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) + r + 1]
                    else:
                        break
                elif p is not None:
                    break
            for r in range(RANKS.index(capture_rank)):
                i = self._file_and_rank_to_index('%s%s' % (
                        capture_file, RANKS[RANKS.index(capture_rank) - r - 1]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) - r - 1]
                    elif piece == 'Q' and w == 3:
                        return capture_file, \
                               RANKS[RANKS.index(capture_rank) - r - 1]
                    else:
                        break
                elif p is not None:
                    break
        # Change file
        if len(self.move_list) % 2 == 1:
            for f in range(7 - FILES.index(capture_file)):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + f + 1], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'rR' and (b == 0 or b == 7):
                        return FILES[FILES.index(capture_file) + f + 1], \
                               capture_rank
                    elif piece in 'qQ' and b == 3:
                        return FILES[FILES.index(capture_file) + f + 1], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
            for f in range(FILES.index(capture_file)):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - f - 1], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'rR' and (b == 0 or b == 7):
                        return FILES[FILES.index(capture_file) - f - 1], \
                               capture_rank
                    elif piece in 'qQ' and b == 3:
                        return FILES[FILES.index(capture_file) - f - 1], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
        else:
            for f in range(7 - FILES.index(capture_file)):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + f + 1], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return FILES[FILES.index(capture_file) + f + 1], \
                               capture_rank
                    elif piece == 'Q' and w == 3:
                        return FILES[FILES.index(capture_file) + f + 1], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
            for f in range(FILES.index(capture_file)):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - f - 1], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return FILES[FILES.index(capture_file) - f - 1], \
                               capture_rank
                    elif piece == 'Q' and w == 3:
                        return FILES[FILES.index(capture_file) - f - 1], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
        if piece in 'rR':
            return capture_file, capture_rank
        else:
            return None, None

    def _search_for_knight(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        if len(self.move_list) % 2 == 1:  # if piece == 'n':
            if RANKS.index(capture_rank) < 6 and FILES.index(capture_file) > 0:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 1],
                        RANKS[RANKS.index(capture_rank) + 2]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) - 1], \
                               RANKS[RANKS.index(capture_rank) + 2]
            if RANKS.index(capture_rank) < 6 and FILES.index(capture_file) < 7:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 1],
                        RANKS[RANKS.index(capture_rank) + 2]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) + 1], \
                               RANKS[RANKS.index(capture_rank) + 2]
            if RANKS.index(capture_rank) > 1 and FILES.index(capture_file) < 7:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 1],
                        RANKS[RANKS.index(capture_rank) - 2]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) + 1], \
                               RANKS[RANKS.index(capture_rank) - 2]
            if RANKS.index(capture_rank) > 1 and FILES.index(capture_file) > 0:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 1],
                        RANKS[RANKS.index(capture_rank) - 2]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) - 1], \
                               RANKS[RANKS.index(capture_rank) - 2]
            if RANKS.index(capture_rank) < 7 and FILES.index(capture_file) > 1:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 2],
                        RANKS[RANKS.index(capture_rank) + 1]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) - 2], \
                               RANKS[RANKS.index(capture_rank) + 1]
            if RANKS.index(capture_rank) < 7 and FILES.index(capture_file) < 6:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 2],
                        RANKS[RANKS.index(capture_rank) + 1]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) + 2], \
                               RANKS[RANKS.index(capture_rank) + 1]
            if RANKS.index(capture_rank) > 0 and FILES.index(capture_file) < 6:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 2],
                        RANKS[RANKS.index(capture_rank) - 1]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) + 2], \
                               RANKS[RANKS.index(capture_rank) - 1]
            if RANKS.index(capture_rank) > 0 and FILES.index(capture_file) > 1:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 2],
                        RANKS[RANKS.index(capture_rank) - 1]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b in [1, 6]:
                        return FILES[FILES.index(capture_file) - 2], \
                               RANKS[RANKS.index(capture_rank) - 1]
        else:
            if RANKS.index(capture_rank) < 6 and FILES.index(capture_file) > 0:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 1],
                        RANKS[RANKS.index(capture_rank) + 2]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) - 1], \
                               RANKS[RANKS.index(capture_rank) + 2]
            if RANKS.index(capture_rank) < 6 and FILES.index(capture_file) < 7:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 1],
                        RANKS[RANKS.index(capture_rank) + 2]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) + 1], \
                               RANKS[RANKS.index(capture_rank) + 2]
            if RANKS.index(capture_rank) > 1 and FILES.index(capture_file) < 7:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 1],
                        RANKS[RANKS.index(capture_rank) - 2]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) + 1], \
                               RANKS[RANKS.index(capture_rank) - 2]
            if RANKS.index(capture_rank) > 1 and FILES.index(capture_file) > 0:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 1],
                        RANKS[RANKS.index(capture_rank) - 2]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) - 1], \
                               RANKS[RANKS.index(capture_rank) - 2]
            if RANKS.index(capture_rank) < 7 and FILES.index(capture_file) > 1:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 2],
                        RANKS[RANKS.index(capture_rank) + 1]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) - 2], \
                               RANKS[RANKS.index(capture_rank) + 1]
            if RANKS.index(capture_rank) < 7 and FILES.index(capture_file) < 6:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 2],
                        RANKS[RANKS.index(capture_rank) + 1]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) + 2], \
                               RANKS[RANKS.index(capture_rank) + 1]
            if RANKS.index(capture_rank) > 0 and FILES.index(capture_file) < 6:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) + 2],
                        RANKS[RANKS.index(capture_rank) - 1]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) + 2], \
                               RANKS[RANKS.index(capture_rank) - 1]
            if RANKS.index(capture_rank) > 0 and FILES.index(capture_file) > 1:
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - 2],
                        RANKS[RANKS.index(capture_rank) - 1]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w in [1, 6]:
                        return FILES[FILES.index(capture_file) - 2], \
                               RANKS[RANKS.index(capture_rank) - 1]
        return capture_file, capture_rank

    def _search_for_bishop(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        # rank++, file++
        if len(self.move_list) % 2 == 1:  # if piece in 'bq':
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) + 1
            while r < 8 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'bB' and (b == 2 or b == 5):
                        return FILES[f], RANKS[r]
                    elif piece in 'qQ' and b == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r += 1
                f += 1
        if len(self.move_list) % 2 == 0:  # if piece in 'BQ':
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) + 1
            while r < 8 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'B' and (w == 2 or w == 5):
                        return FILES[f], RANKS[r]
                    elif piece == 'Q' and w == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r += 1
                f += 1
        # rank--, file++
        if len(self.move_list) % 2 == 1:  # if piece in 'bq':
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) + 1
            while r > -1 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'bB' and (b == 2 or b == 5):
                        return FILES[f], RANKS[r]
                    elif piece in 'qQ' and b == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r -= 1
                f += 1
        if len(self.move_list) % 2 == 0:  # if piece in 'BQ':
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) + 1
            while r > -1 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'B' and (w == 2 or w == 5):
                        return FILES[f], RANKS[r]
                    elif piece == 'Q' and w == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r -= 1
                f += 1
        # rank-- file--
        if len(self.move_list) % 2 == 1:  # if piece in 'bq':
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) - 1
            while r > -1 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'bB' and (b == 2 or b == 5):
                        return FILES[f], RANKS[r]
                    elif piece in 'qQ' and b == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r -= 1
                f -= 1
        if len(self.move_list) % 2 == 0:  # if piece in 'BQ':
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) - 1
            while r > -1 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'B' and (w == 2 or w == 5):
                        return FILES[f], RANKS[r]
                    elif piece == 'Q' and w == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r -= 1
                f -= 1
        # rank++ file--
        if len(self.move_list) % 2 == 1:  # if piece in 'bq':
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) - 1
            while r < 8 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece in 'bB' and (b == 2 or b == 5):
                        return FILES[f], RANKS[r]
                    elif piece in 'qQ' and b == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r += 1
                f -= 1
        if len(self.move_list) % 2 == 0:  # if piece in 'BQ':
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) - 1
            while r < 8 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'B' and (w == 2 or w == 5):
                        return FILES[f], RANKS[r]
                    elif piece == 'Q' and w == 3:
                        return FILES[f], RANKS[r]
                    else:
                        break
                elif p is not None:
                    break
                r += 1
                f -= 1
        return capture_file, capture_rank

    def _search_for_queen(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        file_and_rank = self._search_for_rook(
            piece, source_file, source_rank, capture_file, capture_rank)
        if file_and_rank[0] is not None:
            return file_and_rank[0], file_and_rank[1]
        return self._search_for_bishop(
            piece, source_file, source_rank, capture_file, capture_rank)

    def _search_for_king(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        if len(self.move_list) % 2 == 1:  # if piece == 'k':
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) + 1
            if r < 8 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file)
            if r < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) - 1
            if r < 8 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank)
            f = FILES.index(capture_file) + 1
            if r < 8 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank)
            f = FILES.index(capture_file) - 1
            if f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) + 1
            if r > -1 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file)
            if r > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) - 1
            if r > -1 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if b == 4:
                        return FILES[f], RANKS[r]
        else:
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) + 1
            if r < 8 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file)
            if r < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) + 1
            f = FILES.index(capture_file) - 1
            if r < 8 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank)
            f = FILES.index(capture_file) + 1
            if r < 8 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank)
            f = FILES.index(capture_file) - 1
            if f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) + 1
            if r > -1 and f < 8:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file)
            if r > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
            r = RANKS.index(capture_rank) - 1
            f = FILES.index(capture_file) - 1
            if r > -1 and f > -1:
                i = self._file_and_rank_to_index('%s%s' % (FILES[f], RANKS[r]))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if w == 4:
                        return FILES[f], RANKS[r]
        return capture_file, capture_rank

    def remote_move(self, move):
        ''' Receive a move from a network '''
        if not self.we_are_sharing:
            return
        if self._activity.playing_white and len(self.move_list) % 2 == 0:
            return
        elif not self._activity.playing_white and len(self.move_list) % 2 == 1:
            return
        _logger.debug('Processing remote move (%s)' % (move))
        self.move(move)

    def set_sharing(self, share=True):
        _logger.debug('enabling sharing')
        self.we_are_sharing = share

    def _find_piece_at_index(self, i):
        pos = self._index_to_xy(i)
        return self._find_piece_at_xy(pos)

    def _find_piece_at_xy(self, pos):
        for w in self.white:
            x, y = w.get_xy()
            if x == pos[0] and y == pos[1]:
                return w
        for b in self.black:
            x, y = b.get_xy()
            if x == pos[0] and y == pos[1]:
                return b
        return None

    def _index_to_file_and_rank(self, i):
        return '%s%s' % (FILES[i % 8], RANKS[7 - int(i / 8)])

    def _file_and_rank_to_index(self, file_and_rank):
        ''' calculate the tile index from the file and rank '''
        return FILES.index(file_and_rank[0]) + \
            8 * (7 - RANKS.index(file_and_rank[1]))

    def _index_to_xy(self, i):
        return self._board[i].get_xy()

    def _xy_to_file_and_rank(self, pos):
        ''' calculate the board column and row for an xy position '''
        xo = self._width - 8 * self.scale
        xo = int(xo / 2)
        x = pos[0] - xo
        yo = int(self.scale / 2)
        y = yo
        return ('%s%d' % (FILES[int((pos[0] - xo) / self.scale)],
                8 - int((pos[1] - yo) / self.scale)))

    def __draw_cb(self, canvas, cr):
	self._sprites.redraw_sprites(cr=cr)
    def do_expose_event(self, event):
        ''' Handle the expose-event by drawing '''
        # Restrict Cairo to the exposed area
        cr = self._canvas.window.cairo_create()
        cr.rectangle(event.area.x, event.area.y,
                event.area.width, event.area.height)
        cr.clip()
        # Refresh sprite list
        self._sprites.redraw_sprites(cr=cr)

    def _destroy_cb(self, win, event):
        Gtk.main_quit()

    def _load_board(self, board):
        ''' Load the board based on gnuchess board output '''
        # _logger.debug(board)
        white_pawns = 0
        white_rooks = 0
        white_knights = 0
        white_bishops = 0
        white_queens = 0
        black_pawns = 0
        black_rooks = 0
        black_knights = 0
        black_bishops = 0
        black_queens = 0
        w, h = self.white[0].get_dimensions()
        xo = self._width - 8 * self.scale
        xo = int(xo / 2)
        yo = int(self.scale / 2)
        for i in range(17):  # extra queen
            self.black[i].move((-self.scale, -self.scale))
            self.white[i].move((-self.scale, -self.scale))
        k = 1
        for i in range(8):
            x = xo
            y = yo + i * self.scale
            for j in range(8):
                piece = board[k]
                k += 2
                if piece in 'PRNBQK':  # white
                    if piece == 'P':
                        self.white[8 + white_pawns].move((x, y))
                        white_pawns += 1
                    elif piece == 'R':
                        if white_rooks == 0:
                            self.white[0].move((x, y))
                            white_rooks += 1
                        else:
                            self.white[7].move((x, y))
                            white_rooks += 1
                    elif piece == 'N':
                        if white_knights == 0:
                            self.white[1].move((x, y))
                            white_knights += 1
                        else:
                            self.white[6].move((x, y))
                            white_knights += 1
                    elif piece == 'B':
                        if white_bishops == 0:
                            self.white[2].move((x, y))
                            white_bishops += 1
                        else:
                            self.white[5].move((x, y))
                            white_bishops += 1
                    elif piece == 'Q':
                        if white_queens == 0:
                            self.white[3].move((x, y))
                            white_queens += 1
                        else:
                            self.white[16].move((x, y))
                            self.white[16].set_layer(MID)
                    elif piece == 'K':
                        self.white[4].move((x, y))
                elif piece in 'prnbqk':  # black
                    if piece == 'p':
                        self.black[8 + black_pawns].move((x, y))
                        black_pawns += 1
                    elif piece == 'r':
                        if black_rooks == 0:
                            self.black[0].move((x, y))
                            black_rooks += 1
                        else:
                            self.black[7].move((x, y))
                            black_rooks += 1
                    elif piece == 'n':
                        if black_knights == 0:
                            self.black[1].move((x, y))
                            black_knights += 1
                        else:
                            self.black[6].move((x, y))
                            black_knights += 1
                    elif piece == 'b':
                        if black_bishops == 0:
                            self.black[2].move((x, y))
                            black_bishops += 1
                        else:
                            self.black[5].move((x, y))
                            black_bishops += 1
                    elif piece == 'q':
                        if black_queens == 0:
                            self.black[3].move((x, y))
                            black_queens += 1
                        else:
                            self.black[16].move((x, y))
                            self.black[16].set_layer(MID)
                    elif piece == 'k':
                        self.black[4].move((x, y))
                x += self.scale
            x = xo
            y += self.scale
            k += 1

    def reskin_from_svg(self, piece, colors, bw='#ffffff'):
        DICT = {'white_pawn': svg_pawn, 'black_pawn': svg_pawn,
                'white_rook': svg_rook, 'black_rook': svg_rook,
                'white_knight': svg_knight, 'black_knight': svg_knight,
                'white_bishop': svg_bishop, 'black_bishop': svg_bishop,
                'white_queen': svg_queen, 'black_queen': svg_queen,
                'white_king': svg_king, 'black_king': svg_king}
        pixbuf = svg_str_to_pixbuf(
            svg_header(colors) + DICT[piece](bw) + svg_footer(),
            w=self.scale, h=self.scale)
        self.reskin(piece, pixbuf)

    def reskin_from_file(self, piece, file_path, return_pixbuf=False):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            file_path, self.scale, self.scale)
        self.reskin(piece, pixbuf)
        if return_pixbuf:
            return pixbuf

    def reskin(self, piece, pixbuf):
        DICT = {'white_pawn': WP, 'black_pawn': BP,
                'white_rook': WR, 'black_rook': BR,
                'white_knight': WN, 'black_knight': BN,
                'white_bishop': WB, 'black_bishop': BB,
                'white_queen': WQ, 'black_queen': BQ,
                'white_king': WK, 'black_king': BK}
        self.skins[DICT[piece]] = pixbuf
        if piece == 'white_pawn':
            for i in range(8):
                self.white[i + 8].set_image(pixbuf)
                self.white[i + 8].set_layer(MID)
        elif piece == 'black_pawn':
            for i in range(8):
                self.black[i + 8].set_image(pixbuf)
                self.black[i + 8].set_layer(MID)
        elif piece == 'white_rook':
            self.white[0].set_image(pixbuf)
            self.white[7].set_image(pixbuf)
            self.white[0].set_layer(MID)
            self.white[7].set_layer(MID)
        elif piece == 'black_rook':
            self.black[0].set_image(pixbuf)
            self.black[7].set_image(pixbuf)
            self.black[0].set_layer(MID)
            self.black[7].set_layer(MID)
        elif piece == 'white_knight':
            self.white[1].set_image(pixbuf)
            self.white[6].set_image(pixbuf)
            self.white[1].set_layer(MID)
            self.white[6].set_layer(MID)
        elif piece == 'black_knight':
            self.black[1].set_image(pixbuf)
            self.black[6].set_image(pixbuf)
            self.black[1].set_layer(MID)
            self.black[6].set_layer(MID)
        elif piece == 'white_bishop':
            self.white[2].set_image(pixbuf)
            self.white[5].set_image(pixbuf)
            self.white[2].set_layer(MID)
            self.white[5].set_layer(MID)
        elif piece == 'black_bishop':
            self.black[2].set_image(pixbuf)
            self.black[5].set_image(pixbuf)
            self.black[2].set_layer(MID)
            self.black[5].set_layer(MID)
        elif piece == 'white_queen':
            self.white[3].set_image(pixbuf)
            self.white[16].set_image(pixbuf)
            self.white[3].set_layer(MID)
            self.white[16].set_layer(MID)
        elif piece == 'black_queen':
            self.black[3].set_image(pixbuf)
            self.black[16].set_image(pixbuf)
            self.black[3].set_layer(MID)
            self.black[16].set_layer(MID)
        elif piece == 'white_king':
            self.white[4].set_image(pixbuf)
            self.white[4].set_layer(MID)
        elif piece == 'black_king':
            self.black[4].set_image(pixbuf)
            self.black[4].set_layer(MID)

    def _generate_sprites(self, colors):

        if 'xo' in self._activity.hardware:
            fontsize = 24
        else:
            fontsize = 18
        self.bg = []
        for i in range(3):
            self.bg.append(Sprite(self._sprites, 0, 0, self._box(
                        int(self._width), self._height, color=colors[1])))
            self.bg[-1].set_layer(-1)
            self.bg[-1].set_margins(l=10, t=10, r=10, b=10)
            self.bg[-1].set_label_attributes(fontsize, horiz_align="left",
                                             vert_align="top")
            self.bg[-1].type = None

        self.bg[1].move_relative((int(self._width / 3), 0))
        self.bg[2].move_relative((int(2 * self._width / 3), 0))

        xo = self._width - 8 * self.scale
        xo = int(xo / 2)
        yo = int(self.scale / 2)

        self.rank = Sprite(self._sprites, xo - self.scale, yo,
                           GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/images/rank.svg' % (self._bundle_path),
                self.scale, 8 * self.scale))
        self.rank.set_layer(0)
        self.file =  Sprite(self._sprites, xo, yo + int(self.scale * 8),
                            GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/images/file.svg' % (self._bundle_path),
                8 * self.scale, self.scale))
        self.file.set_layer(0)

        w = h = self.scale
        self._squares.append(self._box(w, h, color='black'))
        self._squares.append(self._box(w, h, color='white'))
        self._squares.append(self._box(w, h, color=colors[0]))
        self._squares.append(self._box(w, h, color=colors[1]))
        xo = self._width - 8 * self.scale
        xo = int(xo / 2)
        yo = int(self.scale / 2)
        y = yo
        for i in range(8):
            x = xo
            for j in range(8):
                self._board.append(
                    Sprite(self._sprites, x, y,
                           self._squares[black_or_white([i, j])]))
                self._board[-1].type = None  # '%s%d' % (FILES[j], 8 - i)
                self._board[-1].set_layer(BOT)
                x += self.scale
            y += self.scale

        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/white-pawn.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/black-pawn.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/white-rook.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/black-rook.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/white-knight.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/black-knight.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/white-bishop.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/black-bishop.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/white-queen.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/black-queen.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/white-king.svg' % (self._bundle_path), w, h))
        self.skins.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                '%s/icons/black-king.svg' % (self._bundle_path), w, h))

        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WR]))
        self.white[-1].type = 'R'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WN]))
        self.white[-1].type = 'N'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WB]))
        self.white[-1].type = 'B'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WQ]))
        self.white[-1].type = 'Q'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WK]))
        self.white[-1].type = 'K'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WB]))
        self.white[-1].type = 'B'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WN]))
        self.white[-1].type = 'N'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WR]))
        self.white[-1].type = 'R'
        self.white[-1].set_layer(MID)
        for i in range(8):
            self.white.append(Sprite(self._sprites, 0, 0, self.skins[WP]))
            self.white[-1].type = 'P'
            self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WQ]))
        self.white[-1].type = 'Q'
        self.white[-1].hide()  # extra queen for pawn

        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BR]))
        self.black[-1].type = 'r'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BN]))
        self.black[-1].type = 'n'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BB]))
        self.black[-1].type = 'b'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BQ]))
        self.black[-1].type = 'q'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BK]))
        self.black[-1].type = 'k'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BB]))
        self.black[-1].type = 'b'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BN]))
        self.black[-1].type = 'n'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BR]))
        self.black[-1].type = 'r'
        self.black[-1].set_layer(MID)
        for i in range(8):
            self.black.append(Sprite(self._sprites, 0, 0, self.skins[BP]))
            self.black[-1].type = 'p'
            self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BQ]))
        self.black[-1].type = 'q'
        self.black[-1].hide()  # extra queen for pawn

    def _box(self, w, h, color='black'):
        ''' Generate a box '''
        self._svg_width = w
        self._svg_height = h
        return svg_str_to_pixbuf(
                self._header() + \
                self._rect(self._svg_width, self._svg_height, 0, 0,
                           color=color) + \
                self._footer())

    def _header(self):
        return '<svg\n' + 'xmlns:svg="http://www.w3.org/2000/svg"\n' + \
            'xmlns="http://www.w3.org/2000/svg"\n' + \
            'xmlns:xlink="http://www.w3.org/1999/xlink"\n' + \
            'version="1.1"\n' + 'width="' + str(self._svg_width) + '"\n' + \
            'height="' + str(self._svg_height) + '">\n'

    def _rect(self, w, h, x, y, color='black'):
        svg_string = '       <rect\n'
        svg_string += '          width="%f"\n' % (w)
        svg_string += '          height="%f"\n' % (h)
        svg_string += '          rx="%f"\n' % (0)
        svg_string += '          ry="%f"\n' % (0)
        svg_string += '          x="%f"\n' % (x)
        svg_string += '          y="%f"\n' % (y)
        if color == 'black':
            svg_string += 'style="fill:#000000;stroke:#000000;"/>\n'
        elif color == 'white':
            svg_string += 'style="fill:#ffffff;stroke:#ffffff;"/>\n'
        else:
            svg_string += 'style="fill:%s;stroke:%s;"/>\n' % (color, color)
        return svg_string

    def _footer(self):
        return '</svg>\n'


def svg_str_to_pixbuf(svg_string, w=None, h=None):
    """ Load pixbuf from SVG string """
    pl = GdkPixbuf.PixbufLoader.new_with_type('svg')
    if w is not None:
        pl.set_size(w, h)
    pl.write(svg_string)
    pl.close()
    pixbuf = pl.get_pixbuf()
    return pixbuf


def black_or_white(n):
    ''' Return 0 is it is a black square; 1 if it is a white square '''
    if type(n) is int:
        i = int(n / 8)
        j = n % 8
    else:
        i = n[0]
        j = n[1]

    if i % 2 == 0:
        if (i * 8 + j) % 2 == 1:
            return 0
        else:
            return 1
    else:
        if (i * 8 + j) % 2 == 1:
            return 1
        else:
            return 0
