# -*- coding: utf-8 -*-
import imp, os, sys, unittest
from test_recon import Obj, Parent, SimplePlugin, module
SOURCE=os.path.join(os.path.dirname(__file__),'../source/res/scripts/client/gui/mods')

class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(sys.modules)
        self.now=100.0; self.callbacks={}; self.serial=0; self.handlers=[]; self.cached={}
        self.frames=[]; self.terrain_frames=[]; self.destroyed=0
        self.equip=Obj(name='poi_smoke',startRadius=10,expandedRadius=37.5,expansionDuration=2)
        self.system=Obj(addSyncDataObjectCallback=self.subscribe,removeSyncDataObjectCallback=lambda k,p,h:self.handlers.remove(h))
        module('BigWorld',serverTime=lambda:self.now,callback=self.callback,cancelCallback=lambda k:self.callbacks.pop(k),player=lambda:Obj(team=2,arena=Obj(componentSystem=self.system)))
        module('Math')
        module('constants',ARENA_SYNC_OBJECTS=Obj(SMOKE=7))
        module('items.vehicles',g_cache=Obj(equipments=lambda:{9403:self.equip}))
        module('gui.Scaleform.daapi.view.battle.shared.minimap.settings')
        module('gui.mods.nidin_smoke_ui',set_contours=lambda *a:self.frames.append(a),clear=lambda:self.frames.append(None))
        geometry=imp.load_source('geometry_tested',os.path.join(SOURCE,'nidin_smoke_geometry.py'))
        module('gui.mods.nidin_smoke_geometry',polylines=geometry.polylines)
        owner=self
        class Terrain(object):
            def update(self,*a):owner.terrain_frames.append(a)
            def destroy(self):owner.destroyed+=1
        module('gui.mods.nidin_smoke_terrain',TerrainOutline=Terrain)
        self.mod=imp.load_source('smoke_tested',os.path.join(SOURCE,'nidin_smoke_bounds.py'))
        self.mod.LOG.disabled=True
        self.smoke=self.mod.SmokeBounds(SimplePlugin(Parent()))
        self.smoke.start()
        self.args=(9403,(1,2,3),100,120,2)
    def tearDown(self):
        self.smoke.stop()
        for key in set(sys.modules)-set(self.saved):del sys.modules[key]
        sys.modules.update(self.saved)
    def callback(self,delay,fn):
        self.serial+=1; self.callbacks[self.serial]=(delay,fn); return self.serial
    def subscribe(self,kind,key,handler):
        self.handlers.append(handler)
        if self.cached:handler(self.cached)
    def tick(self):
        _,fn=self.callbacks.pop(self.smoke.callback); fn()
    def test_growth_colors_and_expiry(self):
        self.smoke._onSmoke({1:self.args})
        self.assertEqual(self.frames[-1][2][2],0xFFDD33)
        self.assertEqual(self.frames[-1][2][1],0xFF4500)
        self.now=101;self.tick()
        self.assertAlmostEqual(self.frames[-1][0][0][1][0][0],24.75)
        self.now=102;self.tick()
        self.assertEqual(self.callbacks[self.smoke.callback][0],18)
        self.now=120;self.tick()
        self.assertFalse(self.callbacks or self.smoke.circles)
        self.assertEqual(self.frames[-1][0],[])
    def test_overlap_one_team_removes_duplicate_but_keeps_enemy(self):
        self.smoke._onSmoke({1:self.args,2:self.args})
        self.assertEqual(len(self.frames[-1][0]),1)
        self.smoke._onSmoke({3:self.args[:-1]+(1,)})
        self.assertEqual(len(self.frames[-1][0]),2)
    def test_duplicate_does_not_redraw_or_extend_expiry(self):
        self.smoke._onSmoke({1:self.args}); count=len(self.frames)
        self.now=105;self.tick(); count=len(self.frames)
        self.smoke._onSmoke({1:self.args})
        self.assertEqual(len(self.frames),count)
        self.assertEqual(self.callbacks[self.smoke.callback][0],15)
    def test_remove_exposes_previous_contour(self):
        self.smoke._onSmoke({1:self.args,2:(9403,(11,2,3),100,120,2)})
        self.assertGreater(len(self.frames[-1][0]),1)
        self.smoke._onSmoke({2:None})
        self.assertEqual(len(self.frames[-1][0]),1)
    def test_replay_resubscription_and_cleanup(self):
        self.cached={1:self.args}
        self.smoke.stop();self.smoke.start();self.smoke.start()
        self.assertEqual(len(self.handlers),1)
        self.assertIn(1,self.smoke.circles)
        self.smoke.stop();self.smoke.stop()
        self.assertFalse(self.handlers or self.callbacks or self.smoke.circles)
        self.assertGreater(self.destroyed,0)
    def test_invalid_inputs(self):
        for args in (None,(),(9403,), (9403,(1,2),100,120,1),(9403,(float('nan'),0,0),100,120,1),(9403,(1,2,3),100,float('inf'),1),(9403,(1,2,3),90,99,1)):
            self.smoke._onSmoke({1:args})
        self.assertFalse(self.smoke.circles or self.callbacks)
    def test_zero_growth_and_other_equipment(self):
        self.equip.expansionDuration=0
        self.smoke._onSmoke({1:self.args})
        self.assertEqual(self.callbacks[self.smoke.callback][0],20)
        self.equip.name='other'
        self.smoke._onSmoke({1:self.args})
        self.assertFalse(self.smoke.circles)
    def test_unknown_team(self):
        self.smoke._onSmoke({1:self.args[:-1]})
        self.assertEqual(self.frames[-1][0][0][0],0)
        self.assertEqual(self.frames[-1][2][0],0xCCCCCC)
    def test_minimap_failure_does_not_block_terrain(self):
        def fail(*a):raise RuntimeError('test')
        self.smoke.ui.set_contours=fail
        self.smoke._onSmoke({1:self.args})
        self.assertTrue(self.terrain_frames)
        self.assertTrue(self.callbacks)

if __name__=='__main__':unittest.main()