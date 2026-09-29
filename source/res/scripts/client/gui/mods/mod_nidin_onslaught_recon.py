# -*- coding: utf-8 -*-
"""Client-provided Comp7 recon areas, with native minimap and terrain rendering."""
import logging
import math
from functools import partial, wraps

import BigWorld
from gui.mods import nidin_recon_ui as warning_ui
from gui.mods.nidin_smoke_bounds import SmokeBounds
import Math
from CombatSelectedArea import DEFAULT_RADIUS_MODEL
from ReplayEvents import g_replayEvents
from gui.Scaleform.daapi.view.battle.comp7.minimap import Comp7MinimapComponent
from gui.Scaleform.daapi.view.battle.shared.minimap import common, settings

LOG = logging.getLogger('nidin.onslaught_recon')
VERSION = '1.2.4'
PLUGIN_KEY = 'nidinReconBoundary'
ALLY_COLOR = 0x54EFAC
ENEMY_COLOR = 0xFF6659
COLORBLIND_COLOR = 0xB69AFF
MAX_AREAS = 64
WARNING_INTERVAL = 0.1
_instances = set()
_original_setup = None
_setup_wrapper = None
_enabled = False


def _finite(value):
    return not math.isnan(value) and not math.isinf(value)


def area_parameters(equipment, level, end_time, now):
    """end_time is launchTime + delay, not the end of the spotting duration."""
    if getattr(equipment, 'name', None) != 'comp7_recon':
        return None
    if isinstance(level, bool) or not isinstance(level, (int, long)) or level < 1:
        return None
    try:
        radius = float(equipment.radius[level - 1])
        duration = float(equipment.duration[level - 1])
        delay = float(equipment.delay)
        remaining = min(float(end_time) + duration - float(now), delay + duration)
    except (TypeError, ValueError, IndexError, KeyError, AttributeError):
        return None
    if not all(_finite(v) for v in (radius, duration, delay, remaining)):
        return None
    if radius <= 0 or duration < 0 or delay < 0 or remaining <= 0:
        return None
    return radius, remaining


def inside_enemy_area(position, player_team, areas):
    """Use the tank centre in the map plane, independently of terrain height."""
    if player_team not in (1, 2):
        return False
    for item in areas:
        # Team 0 is also used for enemy notifications by the current client;
        # match the native recon minimap's comparison with the player's team.
        if item['team'] is None or item['team'] == player_team:
            continue
        x, z = item['center']
        if (position.x - x) ** 2 + (position.z - z) ** 2 <= item['radius'] ** 2:
            return True
    return False


class ReconLamp(object):
    """The bridge merges this warning with the native lamp independently."""
    def __init__(self):
        self.visible = False

    def setVisible(self, visible):
        warning_ui.set_warning(visible)
        self.visible = bool(visible)

    def destroy(self):
        self.setVisible(False)

class TerrainRing(object):
    """Own the model explicitly, including rollback after partial setup."""
    def __init__(self, position, radius, color):
        self.color = color
        self.owner = BigWorld.player()
        self.model = None
        self.area = None
        self.node = None
        self.added = False
        self.attached = False
        try:
            self.model = BigWorld.Model('')
            self.node = self.model.node('')
            self.area = BigWorld.PyTerrainSelectedArea()
            self.area.setup(DEFAULT_RADIUS_MODEL, Math.Vector2(radius * 2, radius * 2),
                            0.25, 0xFF000000 | color)
            self.area.enableAccurateCollision(True)
            self.area.setCutOffDistance(5.0)
            self.node.attach(self.area)
            self.attached = True
            matrix = Math.Matrix()
            matrix.setTranslate(position)
            self.matrix = matrix
            self.model.addMotor(BigWorld.Servo(matrix))
            self.owner.addModel(self.model)
            self.added = True
            self.area.updateHeights()
        except Exception:
            self.destroy()
            raise

    def setColor(self, color):
        self.color = color
        if self.area is not None:
            self.area.setColor(0xFF000000 | color)

    def setRadius(self, radius):
        if self.area is not None:
            self.area.setup(DEFAULT_RADIUS_MODEL, Math.Vector2(radius * 2, radius * 2),
                            0.25, 0xFF000000 | self.color)
            self.area.enableAccurateCollision(True)
            self.area.setCutOffDistance(5.0)
            self.area.updateHeights()

    def destroy(self):
        if self.added:
            self.added = False
            try:
                self.owner.delModel(self.model)
            except Exception:
                LOG.exception('Cannot remove terrain model')
        if self.attached:
            self.attached = False
            try:
                self.node.detach(self.area)
            except Exception:
                LOG.exception('Cannot detach terrain area')
        self.model = self.area = self.node = self.owner = None


class ReconBoundaryPlugin(common.SimplePlugin):
    def __init__(self, parent):
        super(ReconBoundaryPlugin, self).__init__(parent)
        self._controller = None
        self._areas = {}
        self._next_id = 0
        self._started = False
        self._warning = None
        self._warning_callback = None
        self._warning_failed = False
        self._smoke = SmokeBounds(self, TerrainRing)

    def start(self):
        if self._started or not _enabled:
            return
        super(ReconBoundaryPlugin, self).start()
        self._controller = self.sessionProvider.shared.equipments
        if self._controller is not None:
            self._controller.onEquipmentAreaCreated += self._onArea
        self._started = True
        g_replayEvents.onTimeWarpStart += self._onTimeWarp
        g_replayEvents.onTimeWarpFinish += self._onTimeWarpFinish
        _instances.add(self)
        self._smoke.start()
        try:
            warning_ui.start()
        except Exception:
            LOG.exception('Cannot start warning UI')

    def stop(self):
        if self._controller is not None:
            try:
                self._controller.onEquipmentAreaCreated -= self._onArea
            except Exception:
                LOG.exception('Cannot unsubscribe equipment events')
            self._controller = None
        if self._started:
            g_replayEvents.onTimeWarpStart -= self._onTimeWarp
            g_replayEvents.onTimeWarpFinish -= self._onTimeWarpFinish
        self._started = False
        self._smoke.stop()
        self._clearWarning()
        for area_id in list(self._areas):
            self._remove(area_id)
        _instances.discard(self)
        if not _instances:
            warning_ui.stop()
        super(ReconBoundaryPlugin, self).stop()

    def _onTimeWarp(self, *args, **kwargs):
        self._smoke.stop()
        for area_id in list(self._areas):
            self._remove(area_id)

    def _onTimeWarpFinish(self, *args, **kwargs):
        if self._started:
            self._smoke.start()

    def _clearWarning(self):
        if self._warning_callback is not None:
            try:
                BigWorld.cancelCallback(self._warning_callback)
            except Exception:
                LOG.exception('Cannot cancel warning update')
            self._warning_callback = None
        if self._warning is not None:
            self._warning.destroy()
            self._warning = None

    def _tickWarning(self):
        self._warning_callback = None
        self._updateWarning()

    def _updateWarning(self):
        if self._warning_failed:
            return
        try:
            player = BigWorld.player()
            team = getattr(player, 'team', None)
            enemies = [item for item in self._areas.values()
                       if item['team'] is not None and item['team'] != team]
            if not self._started or team not in (1, 2) or not enemies:
                self._clearWarning()
                return
            vehicle = BigWorld.entities.get(getattr(player, 'playerVehicleID', 0))
            input_handler = getattr(player, 'inputHandler', None)
            visible = (bool(getattr(player, 'isVehicleAlive', False)) and
                       vehicle is not None and getattr(vehicle, 'health', 0) > 0 and
                       bool(getattr(input_handler, 'isGuiVisible', False)) and
                       getattr(input_handler, 'ctrlModeName', None) != 'video' and
                       inside_enemy_area(vehicle.position, team, enemies))
            if visible and self._warning is None:
                self._warning = ReconLamp()
            if self._warning is not None:
                self._warning.setVisible(visible)
            if self._warning_callback is None:
                self._warning_callback = BigWorld.callback(WARNING_INTERVAL, self._tickWarning)
        except Exception:
            # A graphics failure must not affect native events or repeatedly log
            # at 10 Hz. Circle rendering continues independently until battle end.
            self._warning_failed = True
            self._clearWarning()
            LOG.exception('Warning border disabled for this battle')

    def _color(self, team):
        if team == BigWorld.player().team:
            return ALLY_COLOR
        return COLORBLIND_COLOR if self.settingsCore.getSetting('isColorBlind') else ENEMY_COLOR

    def updateSettings(self, diff):
        super(ReconBoundaryPlugin, self).updateSettings(diff)
        if 'isColorBlind' not in diff:
            return
        for item in self._areas.values():
            try:
                color = self._color(item['team'])
                if item['entry']:
                    self._invoke(item['entry'], 'as_delMaxViewRage')
                    self._invoke(item['entry'], 'as_addMaxViewRage', color, 1.0, item['radius'])
                if item['terrain'] is not None:
                    item['terrain'].setColor(color)
            except Exception:
                LOG.exception('Cannot update recon color')

    def _onArea(self, equipment, position, endTime, level=None, team=None):
        if not self._started:
            return
        try:
            params = area_parameters(equipment, level, endTime, BigWorld.serverTime())
            if params is None or team is None:
                return
            radius, remaining = params
            if not all(_finite(float(v)) for v in (position.x, position.y, position.z)):
                return
            # Re-delivery of the same server event must not stack resources.
            key = (position.x, position.y, position.z, endTime, level, team)
            if any(item['key'] == key for item in self._areas.values()):
                return
            if len(self._areas) >= MAX_AREAS:
                self._remove(min(self._areas))
            self._next_id += 1
            area_id = self._next_id
            item = {'key': key, 'entry': None, 'terrain': None, 'callback': None,
                    'team': team, 'radius': radius, 'center': (position.x, position.z)}
            self._areas[area_id] = item
            color = self._color(team)
            # One failed renderer must not prevent the other or expiry cleanup.
            try:
                bounds = self._parentObj.getBoundingBox()
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                if width <= 0 or height <= 0:
                    raise ValueError('Invalid arena bounds')
                matrix = Math.Matrix()
                matrix.setTranslate(position)
                flags = settings.TRANSFORM_FLAG.DEFAULT ^ settings.TRANSFORM_FLAG.NO_ROTATION
                item['entry'] = self._addEntry('ViewRangeCirclesEntry', 'equipments',
                                               matrix=matrix, active=True, transformProps=flags)
                if item['entry']:
                    self._invoke(item['entry'], 'as_initArenaSize', width, height)
                    self._invoke(item['entry'], 'as_addMaxViewRage', color, 1.0, radius)
            except Exception:
                LOG.exception('Cannot create minimap circle')
            try:
                item['terrain'] = TerrainRing(position, radius, color)
            except Exception:
                LOG.exception('Cannot create terrain circle')
            try:
                item['callback'] = BigWorld.callback(remaining, partial(self._expire, area_id))
            except Exception:
                self._remove(area_id)
                raise
            self._updateWarning()
        except Exception:
            LOG.exception('Recon notification failed')

    def _expire(self, area_id):
        item = self._areas.get(area_id)
        if item is not None:
            item['callback'] = None
            self._remove(area_id)

    def _remove(self, area_id):
        item = self._areas.pop(area_id, None)
        if item is None:
            return
        if item['callback'] is not None:
            try:
                BigWorld.cancelCallback(item['callback'])
            except Exception:
                LOG.exception('Cannot cancel expiry')
        if item['entry']:
            try:
                self._delEntry(item['entry'])
            except Exception:
                LOG.exception('Cannot remove minimap circle')
        if item['terrain'] is not None:
            try:
                item['terrain'].destroy()
            except Exception:
                LOG.exception('Cannot destroy terrain ring')
        self._updateWarning()


def install():
    global _original_setup, _setup_wrapper, _enabled
    if _enabled:
        return
    warning_ui.install()
    _enabled = True
    if _setup_wrapper is not None:
        return
    _original_setup = Comp7MinimapComponent._setupPlugins
    original = _original_setup

    @wraps(original)
    def setup(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if _enabled and PLUGIN_KEY not in result:
            result[PLUGIN_KEY] = ReconBoundaryPlugin
        return result

    _setup_wrapper = setup
    Comp7MinimapComponent._setupPlugins = setup
    LOG.info('Registered %s', VERSION)


def uninstall():
    global _original_setup, _setup_wrapper, _enabled
    _enabled = False
    for instance in list(_instances):
        try:
            instance.stop()
        except Exception:
            LOG.exception('Cannot stop recon plugin')
    warning_ui.uninstall()
    current = Comp7MinimapComponent._setupPlugins
    if getattr(current, 'im_func', current) is _setup_wrapper:
        Comp7MinimapComponent._setupPlugins = _original_setup
        _original_setup = _setup_wrapper = None
    # If another mod wrapped ours, leave its chain intact; our wrapper is inert.


install()


