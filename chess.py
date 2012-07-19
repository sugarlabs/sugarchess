# -*- coding: utf-8 -*-
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
import cairo
import os
import subprocess
from string import find

from random import uniform

from gettext import gettext as _

import logging
_logger = logging.getLogger('gnuchess-activity')

from sprites import Sprites, Sprite

OPP_MOVE = 'My move is : '
TOP = 3
MID = 2
BOT = 1
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


class Gnuchess():

    def __init__(self, canvas, parent=None, path=None,
                 colors=['#A0FFA0', '#FF8080']):
        self._activity = parent
        self._bundle_path = path
        self._colors = ['#FFFFFF']
        self._colors.append(colors[0])
        self._colors.append(colors[1])
        self._colors.append('#000000')

        self._canvas = canvas
        if parent is not None:
            parent.show_all()
            self._parent = parent

        self._canvas.set_flags(gtk.CAN_FOCUS)
        self._canvas.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self._canvas.add_events(gtk.gdk.BUTTON_RELEASE_MASK)
        self._canvas.add_events(gtk.gdk.POINTER_MOTION_MASK)
        self._canvas.connect("expose-event", self._expose_cb)
        self._canvas.connect("button-press-event", self._button_press_cb)
        self._canvas.connect("button-release-event", self._button_release_cb)
        self._canvas.connect("motion-notify-event", self._mouse_move_cb)

        self._width = gtk.gdk.screen_width()
        self._height = gtk.gdk.screen_height()
        self._scale = int(self._height / 10)
        self.we_are_sharing = False
        self._saved_game = "foo"

        self.move_list = []

        self._press = None
        self._release = None
        self._dragpos = [0, 0]
        self._total_drag = [0, 0]
        self._last_piece_played = [None, (0, 0)]

        self._move = 0
        self.white = []
        self.black = []
        self._squares = []

        self.skins = []  # WPBPWRBRWNBNWBBBWQBQWKBK

        # Generate the sprites we'll need...
        self._sprites = Sprites(self._canvas)
        self._generate_sprites()

        self._all_clear()

    def move(self, my_move=None):
        ''' Send a move to the saved gnuchess instance '''

        _logger.debug(my_move)
        level = '--%s' % (self._activity.mode)
        if self._activity.playing_white:
            color = 'white'
        else:
            color = 'black'

        p = subprocess.Popen(['%s/bin/gnuchess' % (self._bundle_path), level],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)

        if my_move == 'remove':
            self.move_list = self.move_list[:-2]
            cmd = '%s\nforce manual\n' % (color)
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += 'show board\nquit\n'
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=None)
        elif my_move == 'restore':
            cmd = '%s\nforce manual\n' % (color)
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += 'show board\nquit\n'
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=None)
        elif my_move is not None:
            # TODO: if playing black and no moves yet, let white move
            cmd = '%s\nforce manual\n' % (color)
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += '%s\n' % (my_move)
            cmd += 'go\nshow board\nquit\n'
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=my_move)
        else:  # Must be a new game where the robot is playing White
            cmd = '%s\nforce manual\n' % (color)
            cmd += 'go\nshow board\nquit\n'
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=my_move)

    def _process_output(self, output, my_move=None):
        ''' process output '''
        _logger.debug(output)
        if 'Illegal move' in output:
            self._activity.status.set_label(_('Illegal move'))
            if self._last_piece_played[0] is not None:
                self._last_piece_played[0].move(self._last_piece_played[1])
                self._last_piece_played[0] = None
        else:
            if find(output, 'My move is : ') < 0:
                # Black unable to move
                if self._activity.playing_white:
                    _logger.debug('Black cannot move')
                else:
                    _logger.debug('White cannot move')
                self._activity.status.set_label(_('Checkmate'))
            output = output[find(output, OPP_MOVE):]
            opponent_move = output[len(OPP_MOVE):find(output, '\n')]
            _logger.debug(opponent_move)
            if self._activity.playing_white:
                self._activity.black_entry.set_text(opponent_move)
            else:
                self._activity.white_entry.set_text(opponent_move)
            if my_move is not None:
                self.move_list.append(my_move)
            else:
                if self._activity.playing_white:
                    self._activity.black_entry.set_text('')
                else:
                    self._activity.white_entry.set_text('')
            self.move_list.append(opponent_move)

        if self._activity.playing_white or my_move is None:
            looking_for = 'white  '
        else:
            looking_for = 'black  '
        while find(output, looking_for) > 0:
            output = output[find(output, looking_for):]
            output = output[find(output, '\n'):]
        if len(output) < 136:
            _logger.debug('bad board output')
            _logger.debug(output)
            return
        if self._activity.playing_white:
            self._activity.status.set_label(_("It is White's move."))
            self._activity.white_entry.set_text('')
        else:
            self._activity.status.set_label(_("It is Black's move."))
            self._activity.black_entry.set_text('')
        self._load_board(output)

    def _load_board(self, board):
        ''' Load the board based on gnuchess board output '''
        # TODO: Add extra pieces for queened pawns
        black_pawns = 0
        black_rooks = 0
        black_knights = 0
        black_bishops = 0
        white_pawns = 0
        white_rooks = 0
        white_knights = 0
        white_bishops = 0
        w, h = self.white[0].get_dimensions()
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        yo = int(self._scale / 2)
        for i in range(16):
            self.black[i].move((-self._scale, -self._scale))
            self.white[i].move((-self._scale, -self._scale))
        k = 1
        for i in range(8):
            x = xo
            y = yo + i * self._scale
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
                        self.white[3].move((x, y))
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
                        self.black[3].move((x, y))
                    elif piece == 'k':
                        self.black[4].move((x, y))
                x += self._scale
            x = xo
            y += self._scale
            k += 1

    def _all_clear(self):
        ''' Things to reinitialize when starting up a new game. '''
        self.reskin()
        self._reposition()

    def reskin(self):
        for i in range(8):
            if self._activity.playing_white:
                self.black[i + 8].set_image(self.skins[BP])
                self.white[i + 8].set_image(self.skins[WP])
            else:
                self.black[i + 8].set_image(self.skins[WP])
                self.white[i + 8].set_image(self.skins[BP])
            # In case some pawns were changed to queens in previous game
            self.black[i + 8].type = 'p'
            self.white[i + 8].type = 'P'
        if self._activity.playing_white:
            self.black[0].set_image(self.skins[BR])
            self.black[1].set_image(self.skins[BN])
            self.black[2].set_image(self.skins[BB])
            self.black[3].set_image(self.skins[BQ])
            self.black[4].set_image(self.skins[BK])
            self.black[5].set_image(self.skins[BB])
            self.black[6].set_image(self.skins[BN])
            self.black[7].set_image(self.skins[BR])
            self.white[0].set_image(self.skins[WR])
            self.white[1].set_image(self.skins[WN])
            self.white[2].set_image(self.skins[WB])
            self.white[3].set_image(self.skins[WQ])
            self.white[4].set_image(self.skins[WK])
            self.white[5].set_image(self.skins[WB])
            self.white[6].set_image(self.skins[WN])
            self.white[7].set_image(self.skins[WR])
        else:
            self.black[0].set_image(self.skins[WR])
            self.black[1].set_image(self.skins[WN])
            self.black[2].set_image(self.skins[WB])
            self.black[3].set_image(self.skins[WQ])
            self.black[4].set_image(self.skins[WK])
            self.black[5].set_image(self.skins[WB])
            self.black[6].set_image(self.skins[WN])
            self.black[7].set_image(self.skins[WR])
            self.white[0].set_image(self.skins[BR])
            self.white[1].set_image(self.skins[BN])
            self.white[2].set_image(self.skins[BB])
            self.white[3].set_image(self.skins[BQ])
            self.white[4].set_image(self.skins[BK])
            self.white[5].set_image(self.skins[BB])
            self.white[6].set_image(self.skins[BN])
            self.white[7].set_image(self.skins[BR])
        for i in range(16):
            if self._activity.playing_white:
                self.black[i].set_layer(MID)
                self.white[i].set_layer(MID)
            else:
                self.white[i].set_layer(MID)
                self.black[i].set_layer(MID)

    def _reposition(self):
        w, h = self.white[0].get_dimensions()
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        yo = int(self._scale / 2)
        for i in range(8):
            self.black[i].move((xo + i * self._scale, yo))
            self.black[i + 8].move((xo + i * self._scale, yo + self._scale))
            self.white[i].move((xo + i * self._scale, yo + 7 * self._scale))
            self.white[i + 8].move((xo + i * self._scale,
                                   yo + 6 * self._scale))

    def _initiating(self):
        return self._activity.initiating

    def new_game(self):
        self.move_list = []
        self._all_clear()
        if not self._activity.playing_white:
            self.move()

    def restore_game(self, move_list):
        self.move_list = []
        for move in move_list:
            self.move_list.append(str(move))
        _logger.debug(self.move_list)
        self.move(my_move='restore')
        return

    def save_game(self):
        return self.move_list

    def _button_press_cb(self, win, event):
        win.grab_focus()
        x, y = map(int, event.get_coords())

        self._dragpos = [x, y]
        self._total_drag = [0, 0]

        spr = self._sprites.find_sprite((x, y))
        if spr == None or spr.type == None:
            return
        
        # Computer plays lowercase letters
        if spr.type[0] in 'prnbqk':
            return

        self._release = None
        self._press = spr
        self._press.set_layer(TOP)
        self._last_piece_played = [spr, spr.get_xy()]

        self._activity.status.set_label(spr.type)
        return True

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
        move = '%s%s' % (spr.type, self._xy_to_grid((x, y)))
        if self._activity.playing_white:
            self._activity.white_entry.set_text(move)
        else:
            self._activity.black_entry.set_text(move)
        self._activity.status.set_label('Thinking')
        gobject.timeout_add(200, self.mover, move)
        return True

    def mover(self, move):
        self.move(my_move=move)

    def undo(self):
        if len(self.move_list) > 1:
            self.move(my_move='remove')

    def remote_button_press(self, dot, color):
        ''' Receive a button press from a sharer '''
        return

    def set_sharing(self, share=True):
        _logger.debug('enabling sharing')
        self.we_are_sharing = share

    def _grid_to_xy(self, pos):
        ''' calculate the xy position from a column and row in the board '''
        return 

    def _xy_to_grid(self, pos):
        ''' calculate the board column and row for an xy position '''
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        x = pos[0] - xo
        yo = int(self._scale / 2)
        y = yo
        return ('%s%d' % ('abcdefgh'[int((pos[0] - xo) / self._scale)],
                8 - int((pos[1] - yo) / self._scale)))
 
    def _expose_cb(self, win, event):
        self.do_expose_event(event)

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
        gtk.main_quit()

    def _generate_sprites(self):
        bg = Sprite(self._sprites, 0, 0, self._box(self._width, self._height,
                                              color=colors[1]))
        bg.set_layer(-1)
        bg.type = None

        w = h = self._scale
        self._squares.append( self._box(w, h, color='black'))
        self._squares.append( self._box(w, h, color='white'))
        self._squares.append( self._box(w, h, color=colors[0]))
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        yo = int(self._scale / 2)
        y = yo
        for i in range(8):
            x = xo
            for j in range(8):
                if i % 2 == 0:
                    if (i * 8 + j) % 2 == 1:
                        square = Sprite(self._sprites, x, y, self._squares[0])
                    else:
                        square = Sprite(self._sprites, x, y, self._squares[1])
                else:
                    if (i * 8 + j) % 2 == 1:
                        square = Sprite(self._sprites, x, y, self._squares[1])
                    else:
                        square = Sprite(self._sprites, x, y, self._squares[0])
                square.type = None  # '%s%d' % ('abcdefgh'[j], 8 - i)
                square.set_layer(BOT)
                x += self._scale
            y += self._scale

        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/WP.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/BP.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/WR.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/BR.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/WN.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/BN.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/WB.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/BB.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/WQ.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/BQ.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/WK.png', w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                'images/BK.png', w, h))

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


def svg_str_to_pixbuf(svg_string):
    """ Load pixbuf from SVG string """
    pl = gtk.gdk.PixbufLoader('svg')
    pl.write(svg_string)
    pl.close()
    pixbuf = pl.get_pixbuf()
    return pixbuf