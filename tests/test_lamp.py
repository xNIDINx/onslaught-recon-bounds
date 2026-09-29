# -*- coding: utf-8 -*-
import imp
import os
import sys
import unittest
from test_recon import module

SOURCE = os.path.join(os.path.dirname(__file__), '../source/res/scripts/client/gui/mods/nidin_recon_ui.py')

class LampTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        class Native(object):
            def __init__(self):
                self.calls = []
                self.visible = False
                self.native_timer = object()
                self.sound_count = 0
            def _populate(self): return 'populated'
            def _dispose(self):
                self.as_hideS(True)
                return 'disposed'
            def as_showS(self, immidiate):
                self.calls.append(('show', immidiate))
                self.visible = True
                return 'shown'
            def as_showIndicatorS(self):
                self.calls.append(('steady',))
                self.visible = True
                return 'steady'
            def as_hideS(self, immidiate):
                self.calls.append(('hide', immidiate))
                self.visible = False
                return 'hidden'
        self.Native = Native
        module('gui.Scaleform.daapi.view.battle.shared.indicators', SixthSenseIndicator=Native)
        self.ui = imp.load_source('lamp_under_test', SOURCE)
        self.ui.install()
        self.view = Native()
        self.assertEqual(self.view._populate(), 'populated')
        self.ui.start()

    def tearDown(self):
        self.ui.uninstall()
        for key in set(sys.modules) - set(self.saved): del sys.modules[key]
        sys.modules.update(self.saved)

    def test_zone_only_does_not_change_native_reason_timer_or_sound(self):
        timer = self.view.native_timer
        self.ui.set_warning(True)
        self.assertTrue(self.view.visible)
        self.assertFalse(self.ui._views[self.view])
        self.ui.set_warning(False)
        self.assertFalse(self.view.visible)
        self.assertIs(timer, self.view.native_timer)
        self.assertEqual(self.view.sound_count, 0)
        self.assertEqual(self.view.calls, [('show', True), ('hide', True)])

    def test_leaving_zone_does_not_hide_native_alarm(self):
        self.ui.set_warning(True)
        self.assertEqual(self.view.as_showS(immidiate=False), 'shown')
        calls = list(self.view.calls)
        self.ui.set_warning(False)
        self.assertTrue(self.view.visible)
        self.assertEqual(self.view.calls, calls)
        self.view.as_hideS(False)
        self.assertFalse(self.view.visible)

    def test_native_hide_while_in_zone_keeps_warning_then_releases(self):
        self.view.as_showS(False)
        self.ui.set_warning(True)
        self.assertEqual(self.view.as_hideS(immidiate=False), 'hidden')
        self.assertEqual(self.view.calls[-2:], [('hide', False), ('show', True)])
        self.assertTrue(self.view.visible)
        self.assertFalse(self.ui._views[self.view])
        self.ui.set_warning(False)
        self.assertFalse(self.view.visible)

    def test_entering_zone_does_not_restart_native_animation(self):
        self.view.as_showS(False)
        self.ui.set_warning(True)
        self.assertEqual(self.view.calls, [('show', False)])
        self.assertEqual(self.view.as_showIndicatorS(), 'steady')
        self.ui.set_warning(False)
        self.assertEqual(self.view.calls, [('show', False), ('steady',)])
        self.assertTrue(self.view.visible)

    def test_repeated_ticks_and_hooks_do_not_stack(self):
        hook = self.Native.as_showS.im_func
        self.ui.install()
        self.assertIs(hook, self.Native.as_showS.im_func)
        for _ in range(10): self.ui.set_warning(True)
        self.assertEqual(self.view.calls, [('show', True)])

    def test_dispose_does_not_resurrect_or_retain_view(self):
        self.ui.set_warning(True)
        self.assertEqual(self.view._dispose(), 'disposed')
        self.assertFalse(self.view.visible)
        self.assertNotIn(self.view, self.ui._views)
        self.ui.set_warning(False)

    def test_late_populate_receives_existing_area_state(self):
        self.view._dispose()
        self.ui.set_warning(True)
        second = self.Native()
        second._populate()
        self.assertTrue(second.visible)
        self.assertFalse(self.ui._views[second])
        second._dispose()

    def test_stop_hides_only_area_reason(self):
        self.ui.set_warning(True)
        self.ui.stop()
        self.assertFalse(self.view.visible)
        self.ui.start()
        self.view.as_showS(False)
        self.ui.set_warning(True)
        self.ui.stop()
        self.assertTrue(self.view.visible)

    def test_inactive_other_modes_forward_native_calls(self):
        self.ui.stop()
        self.ui.set_warning(True)
        self.assertFalse(self.view.visible)
        self.view.as_showS(False)
        self.view.as_hideS(False)
        self.assertEqual(self.view.calls, [('show', False), ('hide', False)])

    def test_uninstall_preserves_outer_mod_chain_and_native_state(self):
        inner = self.Native.as_showS.im_func
        calls = []
        def outer(view, *args, **kwargs):
            calls.append((args, kwargs))
            return inner(view, *args, **kwargs)
        self.Native.as_showS = outer
        self.view.as_showS(False)
        self.ui.set_warning(True)
        self.ui.uninstall()
        self.assertTrue(self.view.visible)
        self.assertIs(self.Native.as_showS.im_func, outer)
        self.assertEqual(self.view.as_showS(immidiate=True), 'shown')
        self.assertEqual(calls[-1], ((), {'immidiate': True}))
        self.assertFalse(self.ui._views)
        self.ui.install()
        self.assertIs(self.Native.as_showS.im_func, outer)
        self.view._populate()
        self.ui.start()
        self.ui.set_warning(True)
        self.view.as_hideS(False)
        self.assertTrue(self.view.visible)

if __name__ == '__main__': unittest.main()
