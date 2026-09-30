# -*- coding: utf-8 -*-
import imp
import logging
import marshal
import os
import sys
import types
import unittest
import zipfile

sys.dont_write_bytecode = True
PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCE = os.path.join(PROJECT, 'source/res/scripts/client/gui/mods/mod_nidin_onslaught_recon.py')

class Obj(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class Event(list):
    def __iadd__(self, fn):
        self.append(fn)
        return self
    def __isub__(self, fn):
        self.remove(fn)
        return self
    def __call__(self, *args, **kwargs):
        for fn in list(self):
            fn(*args, **kwargs)

class Vector(object):
    def __init__(self, *values):
        self.x, self.y = values[:2]
        self.z = values[2] if len(values) > 2 else 0

class Matrix(object):
    def setTranslate(self, position):
        self.position = position

class Parent(object):
    def __init__(self):
        self.entries = {}
        self.calls = []
        self.serial = 0
        self.fail_delete = False
    def addEntry(self, *args, **kwargs):
        self.serial += 1
        self.entries[self.serial] = (args, kwargs)
        return self.serial
    def delEntry(self, ident):
        if self.fail_delete:
            raise RuntimeError('Test failure')
        del self.entries[ident]
    def invoke(self, *args):
        self.calls.append(args)
    def getBoundingBox(self):
        return ((-500, -500), (500, 500))

class SimplePlugin(object):
    def __init__(self, parent):
        self._parentObj = parent
    def start(self): pass
    def stop(self): pass
    def updateSettings(self, diff): pass
    def _addEntry(self, *args, **kwargs): return self._parentObj.addEntry(*args, **kwargs)
    def _delEntry(self, *args): return self._parentObj.delEntry(*args)
    def _invoke(self, *args): return self._parentObj.invoke(*args)

class NativeMinimap(object):
    def _setupPlugins(self, *args, **kwargs):
        self.received = (args, kwargs)
        return {'native': object}

def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    sys.modules[name] = value
    if '.' in name:
        parent, child = name.rsplit('.', 1)
        if parent not in sys.modules:
            module(parent)
        setattr(sys.modules[parent], child, value)
    return value

class ReconTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        self.callbacks = {}
        self.serial = 0
        self.event = Event()
        self.warp = Event()
        self.player = Obj(team=1, playerVehicleID=7, isVehicleAlive=True,
                          inputHandler=Obj(isGuiVisible=True))
        self.vehicle = Obj(health=1000,position=Vector(0,0,0))
        self.bw = module('BigWorld', player=lambda: self.player, serverTime=lambda: 100,
                         callback=self.callback, cancelCallback=lambda i: self.callbacks.pop(i),
                         entities={7:self.vehicle}, screenWidth=lambda:1920,screenHeight=lambda:1080)
        self.ui = module('gui.mods.nidin_recon_ui',visible=False,start=lambda:None,stop=lambda:None,
                         install=lambda:None,uninstall=lambda:None)
        self.ui.set_warning = lambda visible:setattr(self.ui,'visible',bool(visible))
        module('Math', Vector2=Vector, Vector3=Vector, Matrix=Matrix)
        module('constants', ARENA_SYNC_OBJECTS=Obj(SMOKE=7))
        module('items.vehicles', g_cache=Obj(equipments=lambda:{}))
        module('gui.mods.nidin_smoke_ui', clear=lambda:None, set_contours=lambda *a:None)
        geometry = imp.load_source('geometry_tested', os.path.join(os.path.dirname(SOURCE), 'nidin_smoke_geometry.py'))
        module('gui.mods.nidin_smoke_geometry', boundary_arcs=geometry.boundary_arcs,
               polylines_from_arcs=geometry.polylines_from_arcs)
        module('gui.mods.nidin_smoke_terrain', TerrainOutline=lambda:Obj(update=lambda *a:None,destroy=lambda:None))
        module('CombatSelectedArea', DEFAULT_RADIUS_MODEL='native.visual')
        self.warp_finish = Event()
        module('ReplayEvents', g_replayEvents=Obj(onTimeWarpStart=self.warp,onTimeWarpFinish=self.warp_finish))
        module('gui.Scaleform.daapi.view.battle.comp7.minimap', Comp7MinimapComponent=NativeMinimap)
        module('gui.Scaleform.daapi.view.battle.shared.minimap.common', SimplePlugin=SimplePlugin)
        module('gui.Scaleform.daapi.view.battle.shared.minimap.settings',
               TRANSFORM_FLAG=Obj(DEFAULT=7, NO_ROTATION=2))
        smoke = imp.load_source('smoke_under_test', os.path.join(os.path.dirname(SOURCE), 'nidin_smoke_bounds.py'))
        module('gui.mods.nidin_smoke_bounds', SmokeBounds=smoke.SmokeBounds)
        self.mod = imp.load_source('recon_under_test', SOURCE)
        self.mod.LOG.disabled = True
        self.terrain = []
        owner = self
        class Ring(object):
            def __init__(self, position, radius, color):
                self.position, self.radius, self.color = position, radius, color
                self.destroyed = False
                owner.terrain.append(self)
            def setColor(self, color): self.color = color
            def destroy(self): self.destroyed = True
        self.actual_ring = self.mod.TerrainRing
        self.mod.TerrainRing = Ring
        self.parent = Parent()
        self.plugin = self.mod.ReconBoundaryPlugin(self.parent)
        self.plugin.sessionProvider = Obj(shared=Obj(equipments=Obj(onEquipmentAreaCreated=self.event)))
        self.blind = False
        self.plugin.settingsCore = Obj(getSetting=lambda name: self.blind)
        self.plugin.start()
        self.equipment = Obj(name='comp7_recon', radius=[45,55,60], duration=[10,12,15], delay=3)
        self.position = Vector(100, 5, -90)

    def tearDown(self):
        self.mod.uninstall()
        for key in set(sys.modules) - set(self.saved):
            del sys.modules[key]
        sys.modules.update(self.saved)

    def callback(self, delay, fn):
        self.serial += 1
        self.callbacks[self.serial] = (delay, fn)
        return self.serial

    def fire(self, **kwargs):
        values = dict(level=2, team=1)
        values.update(kwargs)
        self.event(self.equipment, self.position, 103, **values)

    def test_radius_and_both_renderers(self):
        self.fire()
        self.assertEqual(self.terrain[0].radius, 55)
        self.assertEqual(self.terrain[0].color, self.mod.ALLY_COLOR)
        self.assertEqual(self.parent.calls, [(1,'as_initArenaSize',1000,1000),
                                           (1,'as_addMaxViewRage',self.mod.ALLY_COLOR,1.0,55.0)])
        self.assertEqual(self.callbacks[1][0], 15)

    def test_expiry_releases_both_renderers(self):
        self.fire()
        _, fn = self.callbacks.pop(1)
        fn()
        self.assertFalse(self.plugin._areas)
        self.assertFalse(self.parent.entries)
        self.assertTrue(self.terrain[0].destroyed)

    def test_stop_is_idempotent_and_unsubscribes(self):
        self.fire()
        self.plugin.stop()
        self.plugin.stop()
        self.assertFalse(self.event or self.warp or self.callbacks or self.parent.entries)

    def test_duplicate_event_does_not_stack(self):
        self.fire()
        self.fire()
        self.assertEqual(len(self.terrain), 1)

    def test_other_skill_and_invalid_levels_ignored(self):
        for level in [None,0,-1,4,True,1.5]:
            self.fire(level=level)
        self.equipment.name = 'comp7_redline'
        self.fire()
        self.assertFalse(self.plugin._areas)

    def test_remaining_time_uses_server_clock(self):
        self.assertEqual(self.mod.area_parameters(self.equipment,2,98,100),(55,10))
        self.assertIsNone(self.mod.area_parameters(self.equipment,2,80,100))
        self.assertEqual(self.mod.area_parameters(self.equipment,2,9999,100),(55,15))

    def test_nan_and_infinity_rejected(self):
        for value in [float('nan'),float('inf'),-1]:
            self.equipment.radius[1] = value
            self.fire()
        self.assertFalse(self.plugin._areas)

    def test_enemy_color_and_colorblind_changes(self):
        self.fire(team=2)
        self.assertEqual(self.terrain[0].color,self.mod.ENEMY_COLOR)
        self.blind = True
        self.plugin.updateSettings({'isColorBlind':True})
        self.assertEqual(self.terrain[0].color,self.mod.COLORBLIND_COLOR)

    def test_terrain_failure_keeps_minimap_and_expiry(self):
        def broken(*args): raise RuntimeError('Test failure')
        self.mod.TerrainRing = broken
        self.fire()
        self.assertEqual(len(self.parent.entries),1)
        self.assertEqual(len(self.callbacks),1)

    def test_minimap_failure_keeps_terrain_and_expiry(self):
        def broken(*args, **kwargs): raise RuntimeError('Test failure')
        self.parent.addEntry = broken
        self.fire()
        self.assertEqual(len(self.terrain),1)
        self.assertEqual(len(self.callbacks),1)

    def test_delete_failure_does_not_block_terrain_cleanup(self):
        self.fire()
        self.parent.fail_delete = True
        self.plugin.stop()
        self.assertTrue(self.terrain[0].destroyed)
        self.assertFalse(self.callbacks)

    def test_timewarp_clears_old_areas(self):
        self.fire()
        self.warp()
        self.assertFalse(self.parent.entries or self.callbacks or self.plugin._areas)

    def test_hook_preserves_arguments_and_other_plugins(self):
        view = NativeMinimap()
        result = view._setupPlugins(123, value=4)
        self.assertEqual(view.received,((123,),{'value':4}))
        self.assertIs(result['native'],object)
        self.assertIs(result[self.mod.PLUGIN_KEY],self.mod.ReconBoundaryPlugin)
        hook = NativeMinimap._setupPlugins
        self.mod.install()
        self.assertEqual(hook, NativeMinimap._setupPlugins)

    def test_uninstall_restores_original_python27_method(self):
        original = self.mod._original_setup
        self.mod.uninstall()
        self.assertEqual(NativeMinimap._setupPlugins, original)
        self.mod.install()

    def test_uninstall_preserves_later_mod_wrapper(self):
        hook = NativeMinimap._setupPlugins
        def later(view,*args,**kwargs): return hook(view,*args,**kwargs)
        NativeMinimap._setupPlugins = later
        self.mod.uninstall()
        self.assertIs(NativeMinimap._setupPlugins.im_func,later)
        self.assertNotIn(self.mod.PLUGIN_KEY,NativeMinimap()._setupPlugins())
        self.mod.install()
        self.assertIn(self.mod.PLUGIN_KEY,NativeMinimap()._setupPlugins())
        NativeMinimap._setupPlugins = hook

    def test_area_limit_releases_oldest(self):
        self.mod.MAX_AREAS = 2
        for x in range(3):
            self.position = Vector(x,0,0)
            self.fire()
        self.assertEqual(len(self.plugin._areas),2)
        self.assertTrue(self.terrain[0].destroyed)
        self.assertEqual(len(self.callbacks),2)

    def test_partial_terrain_failure_rolls_back_model(self):
        calls = []
        area = Obj(setup=lambda *a:None, enableAccurateCollision=lambda *a:None,
                   setCutOffDistance=lambda *a:None)
        def fail(): raise RuntimeError('Height collision failed')
        area.updateHeights = fail
        node = Obj(attach=lambda a:calls.append('attach'),detach=lambda a:calls.append('detach'))
        model = Obj(node=lambda name:node,addMotor=lambda m:None)
        self.player.addModel = lambda m:calls.append('add')
        self.player.delModel = lambda m:calls.append('remove')
        self.bw.Model = lambda name:model
        self.bw.PyTerrainSelectedArea = lambda:area
        self.bw.Servo = lambda m:m
        self.assertRaises(RuntimeError,self.actual_ring,self.position,55,self.mod.ALLY_COLOR)
        self.assertEqual(calls,['attach','add','remove','detach'])

    def test_installed_client_event_contract(self):
        package = os.environ.get('TANKI_SCRIPTS_PKG',r'C:\Games\Tanki\res\packages\scripts.pkg')
        with zipfile.ZipFile(package) as archive:
            code = marshal.loads(archive.read('scripts/client/gui/Scaleform/daapi/view/battle/comp7/minimap.pyc')[8:])
        def find(code,name):
            for child in code.co_consts:
                if isinstance(child,types.CodeType):
                    if child.co_name == name: return child
                    result = find(child,name)
                    if result: return result
        event = find(code,'_onEquipmentAreaCreated')
        self.assertEqual(event.co_varnames[:event.co_argcount],('self','equipment','position','endTime','level','team'))
        self.assertIn('comp7_recon',event.co_consts)
        self.assertIn('radius',event.co_names)
        self.assertIn('duration',event.co_names)

    def tick_warning(self):
        _, callback = self.callbacks.pop(self.plugin._warning_callback)
        callback()

    def test_warning_appears_on_entry_and_hides_on_exit(self):
        self.fire(team=2)
        self.assertFalse(self.ui.visible)
        self.vehicle.position = self.position
        self.tick_warning()
        self.assertTrue(self.plugin._warning.visible)
        self.assertTrue(self.ui.visible)
        self.vehicle.position = Vector(1000,5,-90)
        self.tick_warning()
        self.assertFalse(self.plugin._warning.visible)
        self.assertFalse(self.ui.visible)

    def test_video_camera_hides_area_warning(self):
        self.vehicle.position = self.position
        self.fire(team=2)
        self.assertTrue(self.ui.visible)
        self.player.inputHandler.ctrlModeName = 'video'
        self.tick_warning()
        self.assertFalse(self.ui.visible)
        self.player.inputHandler.ctrlModeName = 'sniper'
        self.tick_warning()
        self.assertTrue(self.ui.visible)

    def test_smoke_never_activates_recon_lamp(self):
        smoke_equipment = Obj(name='poi_smoke',startRadius=10,expandedRadius=37.5,expansionDuration=2)
        sys.modules['items.vehicles'].g_cache.equipments = lambda:{9403:smoke_equipment}
        handlers = []
        self.player.arena = Obj(componentSystem=Obj(
            addSyncDataObjectCallback=lambda kind,key,handler:handlers.append(handler),
            removeSyncDataObjectCallback=lambda kind,key,handler:handlers.remove(handler)))
        self.plugin._smoke.start()
        self.plugin._smoke._onSmoke({1:(9403,(0,0,0),100,120,2)})
        self.assertEqual(len(self.plugin._smoke.circles),1)
        self.assertFalse(self.ui.visible or self.plugin._areas)
        self.assertIsNone(self.plugin._warning_callback)
        self.warp()
        self.assertFalse(handlers or self.plugin._smoke.circles or self.callbacks)
        self.warp_finish()
        self.assertEqual(len(handlers),1)
        self.plugin.stop()
        self.assertFalse(handlers or self.warp_finish)

    def test_own_plane_never_creates_warning_timer_or_lamp(self):
        self.vehicle.position = self.position
        self.fire(team=1)
        self.assertIsNone(self.plugin._warning_callback)
        self.assertFalse(self.ui.visible)

    def test_native_enemy_team_zero_is_supported(self):
        self.vehicle.position = self.position
        self.fire(team=0)
        self.assertTrue(self.plugin._warning.visible)

    def test_tangent_and_height_are_handled_in_map_plane(self):
        self.vehicle.position = Vector(155,1000,-90)
        self.fire(team=2)
        self.assertTrue(self.plugin._warning.visible)
        self.vehicle.position = Vector(155.01,-1000,-90)
        self.tick_warning()
        self.assertFalse(self.plugin._warning.visible)

    def test_warning_uses_own_vehicle_not_spectator_target(self):
        self.bw.entities[9] = Obj(health=1000,position=self.position)
        self.player.getVehicleAttached = lambda:self.bw.entities[9]
        self.fire(team=2)
        self.assertFalse(self.ui.visible)
        self.vehicle.position = self.position
        self.tick_warning()
        self.assertTrue(self.plugin._warning.visible)

    def test_death_missing_vehicle_and_hidden_gui_hide_warning(self):
        self.vehicle.position = self.position
        self.fire(team=2)
        self.vehicle.health = 0
        self.tick_warning()
        self.assertFalse(self.plugin._warning.visible)
        self.vehicle.health = 1000
        self.player.isVehicleAlive = False
        self.tick_warning()
        self.assertFalse(self.plugin._warning.visible)
        self.player.isVehicleAlive = True
        self.player.inputHandler.isGuiVisible = False
        self.tick_warning()
        self.assertFalse(self.plugin._warning.visible)
        self.player.inputHandler.isGuiVisible = True
        del self.bw.entities[7]
        self.tick_warning()
        self.assertFalse(self.plugin._warning.visible)

    def test_unknown_player_team_never_warns(self):
        self.vehicle.position = self.position
        self.player.team = 0
        self.fire(team=2)
        self.assertFalse(self.ui.visible)
        self.assertIsNone(self.plugin._warning_callback)

    def test_overlapping_enemy_areas_keep_one_lamp_until_last_removed(self):
        self.vehicle.position = self.position
        self.fire(team=2)
        self.position = Vector(101,5,-90)
        self.fire(team=2)
        self.assertTrue(self.ui.visible)
        self.assertEqual(len(self.callbacks),3)  # Two expiry timers and one position check.
        self.plugin._remove(1)
        self.assertTrue(self.plugin._warning.visible)
        self.plugin._remove(2)
        self.assertIsNone(self.plugin._warning)
        self.assertFalse(self.ui.visible or self.callbacks)

    def test_warning_expiry_stop_and_rewind_hide_ui_and_cancel_callbacks(self):
        self.vehicle.position = self.position
        self.fire(team=2)
        _, expire = self.callbacks.pop(self.plugin._areas[1]['callback'])
        expire()
        self.assertFalse(self.ui.visible or self.callbacks)
        self.fire(team=2)
        self.warp()
        self.assertFalse(self.ui.visible or self.callbacks)
        self.fire(team=2)
        self.plugin.stop()
        self.assertFalse(self.ui.visible or self.callbacks)

    def test_warning_transport_failure_does_not_break_circles(self):
        calls = []
        def set_warning(visible):
            calls.append(visible)
            if visible: raise RuntimeError('Test Flash failure')
        self.ui.set_warning = set_warning
        self.vehicle.position = self.position
        self.fire(team=2)
        self.assertTrue(self.plugin._warning_failed)
        self.assertFalse(self.ui.visible)
        self.assertEqual(len(self.parent.entries),1)
        self.assertEqual(len(self.terrain),1)
        self.assertEqual(len(self.callbacks),1)
        self.plugin._updateWarning()
        self.assertEqual(calls,[True,False])

if __name__ == '__main__':
    unittest.main()
