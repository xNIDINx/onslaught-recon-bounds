# -*- coding: utf-8 -*-
"""Client-synchronized Onslaught smoke circles; no spotting/lamp integration."""
import logging
from functools import partial
import math
import BigWorld
import Math
from constants import ARENA_SYNC_OBJECTS
from items import vehicles
from gui.Scaleform.daapi.view.battle.shared.minimap import settings

LOG = logging.getLogger('nidin.onslaught_recon_bounds.smoke')
ALLY_COLOR = 0xFFDD33
ENEMY_COLOR = 0xFF4500
UNKNOWN_COLOR = 0xCCCCCC
MAX_SMOKES = 64
UPDATE_INTERVAL = 0.1


def parameters(args, equipment, now):
    try:
        if equipment.name != 'poi_smoke':
            return None
        position = tuple(float(v) for v in args[1])
        start, end = float(args[2]), float(args[3])
        small = float(equipment.startRadius)
        large = float(equipment.expandedRadius)
        expansion = float(equipment.expansionDuration)
        values = position + (start, end, small, large, expansion, float(now))
        if len(position) != 3 or not all(not math.isnan(v) and not math.isinf(v) for v in values):
            return None
        if small <= 0 or large < small or expansion < 0 or end <= max(start, now):
            return None
        return position, start, end, small, large, expansion
    except (TypeError, ValueError, IndexError, AttributeError):
        return None


def radius_at(params, now):
    _, start, _, small, large, expansion = params
    fraction = 1.0 if expansion == 0 else max(0.0, min(1.0, (now-start)/expansion))
    return small + (large-small)*fraction


class SmokeBounds(object):
    def __init__(self, plugin, terrain_factory=None):
        self.plugin = plugin
        self.system = None
        self.circles = {}
        self.callback = None
        self.terrain = None
        self.signature = None
        self.ui = None

    def start(self):
        if self.system is not None:
            return
        from gui.mods.nidin_smoke import ui
        self.ui = ui
        arena = getattr(BigWorld.player(), 'arena', None)
        self.system = getattr(arena, 'componentSystem', None)
        if self.system is not None:
            try:
                self.system.addSyncDataObjectCallback(ARENA_SYNC_OBJECTS.SMOKE, '', self._onSmoke)
            except Exception:
                self.stop()
                LOG.exception('Cannot subscribe smoke areas')

    def stop(self):
        system, self.system = self.system, None
        if system is not None:
            try:
                system.removeSyncDataObjectCallback(ARENA_SYNC_OBJECTS.SMOKE, '', self._onSmoke)
            except Exception:
                LOG.exception('Cannot unsubscribe smoke areas')
        self._cancel()
        self.circles.clear()
        self.signature = None
        if self.terrain is not None:
            self.terrain.destroy()
            self.terrain = None
        if self.ui is not None:
            try:
                self.ui.clear()
            except Exception:
                LOG.exception('Cannot clear smoke minimap')

    def _cancel(self):
        callback, self.callback = self.callback, None
        if callback is not None:
            try:
                BigWorld.cancelCallback(callback)
            except Exception:
                LOG.exception('Cannot cancel smoke callback')

    def _onSmoke(self, changes):
        if self.system is None:
            return
        for key, args in changes.items():
            try:
                if args is None:
                    self.circles.pop(key, None)
                    continue
                equipment = vehicles.g_cache.equipments().get(args[0])
                params = parameters(args, equipment, BigWorld.serverTime())
                if params is None:
                    self.circles.pop(key, None)
                    continue
                team = args[4] if len(args) > 4 and args[4] in (1, 2) else 0
                if key not in self.circles and len(self.circles) >= MAX_SMOKES:
                    self.circles.pop(min(self.circles, key=lambda k: self.circles[k]['params'][2]))
                self.circles[key] = dict(params=params, team=team)
            except Exception:
                self.circles.pop(key, None)
                LOG.exception('Cannot process smoke area')
        self._cancel()
        self._tick()

    def _tick(self):
        self.callback = None
        if self.system is None:
            return
        now = BigWorld.serverTime()
        for key in list(self.circles):
            if self.circles[key]['params'][2] <= now:
                self.circles.pop(key)
        circles = []
        next_delay = None
        for key in sorted(self.circles):
            item = self.circles[key]
            params = item['params']
            if now < params[1]:
                delay = params[1]-now
                next_delay = delay if next_delay is None else min(next_delay, delay)
                continue
            radius = radius_at(params, now)
            circles.append(params[0] + (radius, item['team'], params[1]))
            delay = min(UPDATE_INTERVAL, params[2]-now) if now < params[1]+params[5] else params[2]-now
            next_delay = delay if next_delay is None else min(next_delay, delay)
        player_team = getattr(BigWorld.player(), 'team', None)
        signature = (tuple(circles), player_team)
        if signature != self.signature:
            from gui.mods.nidin_smoke.geometry import priority_boundary_arcs, polylines_from_arcs
            arcs = priority_boundary_arcs(circles)
            lines = polylines_from_arcs(arcs, step=3.0)
            colors = {team: (UNKNOWN_COLOR if team == 0 or player_team not in (1,2)
                             else ALLY_COLOR if team == player_team else ENEMY_COLOR)
                      for team in (0,1,2)}
            try:
                self.ui.set_contours(lines, self.plugin._parentObj.getBoundingBox(), colors)
            except Exception:
                LOG.exception('Cannot draw smoke minimap contour')
            try:
                terrain_lines = lines
                if self.terrain is None and terrain_lines:
                    from gui.mods.nidin_smoke.terrain import TerrainOutline
                    self.terrain = TerrainOutline()
                if self.terrain is not None:
                    self.terrain.update(terrain_lines, colors)
            except Exception:
                if self.terrain is not None:
                    self.terrain.destroy()
                    self.terrain = None
                LOG.exception('Cannot draw smoke terrain contour')
            self.signature = signature
        if next_delay is not None:
            self.callback = BigWorld.callback(max(0.01, next_delay), self._tick)
