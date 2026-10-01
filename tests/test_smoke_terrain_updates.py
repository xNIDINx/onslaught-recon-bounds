# -*- coding: utf-8 -*-
"""Engine-call regressions for incremental smoke terrain projection."""
import imp
import os
import sys
import types
import unittest


SOURCE = os.path.join(os.path.dirname(__file__),
                      '../source/res/scripts/client/gui/mods/nidin_smoke')


class Matrix(object):
    def __init__(self):
        self.rotation_calls = []
        self.translation_calls = []
        self._translation = None

    def setRotateYPR(self, angles):
        self.rotation_calls.append(angles)

    @property
    def translation(self):
        return self._translation

    @translation.setter
    def translation(self, value):
        self._translation = value
        self.translation_calls.append(value)


class Area(object):
    def __init__(self):
        self.calls = []
        self.color = None
        self.size = None
        self.fail_heights = False

    def setup(self, path, size, depth, color):
        self.calls.append(('setup', path, size, depth, color))
        self.color = color
        self.size = size

    def enableAccurateCollision(self, enabled):
        self.calls.append(('collision', enabled))

    def setCutOffDistance(self, value):
        self.calls.append(('cutoff', value))

    def updateHeights(self):
        self.calls.append(('heights',))
        if self.fail_heights:
            raise RuntimeError('simulated terrain projection failure')

    def setSize(self, size):
        self.calls.append(('size', size))
        self.size = size

    def setColor(self, color):
        self.calls.append(('color', color))
        self.color = color

    def count(self, operation):
        return sum(call[0] == operation for call in self.calls)


class Node(object):
    def __init__(self):
        self.area = None
        self.detach_calls = []
        self.fail_detach = False

    def attach(self, area):
        self.area = area

    def detach(self, area):
        self.detach_calls.append(area)
        if self.fail_detach:
            raise RuntimeError('simulated detach failure')
        self.area = None


class Model(object):
    def __init__(self, path):
        self.node_instance = Node()
        self.matrix = None
        self.fail_delete = False

    def node(self, name):
        return self.node_instance

    def addMotor(self, matrix):
        self.matrix = matrix


class Owner(object):
    def __init__(self):
        self.models = []
        self.add_calls = []
        self.delete_calls = []

    def addModel(self, model):
        self.models.append(model)
        self.add_calls.append(model)

    def delModel(self, model):
        self.delete_calls.append(model)
        if model.fail_delete:
            raise RuntimeError('simulated model removal failure')
        self.models.remove(model)


def line(x, end=None, team=1):
    if end is None:
        end = x + 3.0
    return team, [(x, 2.0, 0.0), (end, 2.0, 0.0)]


class TerrainUpdateTests(unittest.TestCase):
    COLORS = {1: 0xFFDD33, 2: 0xFF4500}

    def setUp(self):
        self.saved_modules = dict(sys.modules)
        self.owner = Owner()
        self.areas = []
        self.fail_new_heights = False

        def new_area():
            area = Area()
            area.fail_heights = self.fail_new_heights
            self.areas.append(area)
            return area

        def module(name, **attributes):
            result = types.ModuleType(name)
            result.__dict__.update(attributes)
            sys.modules[name] = result

        class Section(object):
            asString = 'test/sector_border.model'

            def __getitem__(self, name):
                return self

        module('BigWorld', player=lambda: self.owner, Model=Model,
               PyTerrainSelectedArea=new_area, Servo=lambda matrix: matrix)
        module('Math', Matrix=Matrix, Vector2=lambda *values: values,
               Vector3=lambda *values: values)
        module('ResMgr', openSection=lambda path: Section())
        self.mod = imp.load_source('smoke_terrain_tested',
                                  os.path.join(SOURCE, 'terrain.py'))
        self.saved_log_disabled = self.mod.LOG.disabled
        self.mod.LOG.disabled = True
        self.outline = self.mod.TerrainOutline()

    def tearDown(self):
        self.outline.destroy()
        self.mod.LOG.disabled = self.saved_log_disabled
        for key in set(sys.modules) - set(self.saved_modules):
            del sys.modules[key]
        sys.modules.update(self.saved_modules)

    def model_at(self, x):
        matches = [model for model in self.owner.models
                   if model.matrix.translation == (x, 2.0, 0.0)]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def snapshot(self, model):
        return (list(model.node_instance.area.calls),
                list(model.matrix.rotation_calls),
                list(model.matrix.translation_calls))

    def test_identical_geometry_does_no_engine_work(self):
        self.outline.update([line(0), line(100)], self.COLORS)
        before = dict((model, self.snapshot(model)) for model in self.owner.models)
        for unused in range(3):
            self.outline.update([line(0), line(100)], dict(self.COLORS))
        self.assertEqual(len(self.owner.add_calls), 2)
        for model, snapshot in before.items():
            self.assertEqual(self.snapshot(model), snapshot)
        for area in self.areas:
            self.assertEqual(area.count('setup'), 1)
            self.assertEqual(area.count('heights'), 1)
            self.assertEqual(area.count('collision'), 1)
            self.assertEqual(area.count('cutoff'), 1)

    def test_reordering_lines_preserves_all_projectors(self):
        self.outline.update([line(0), line(100), line(200)], self.COLORS)
        before = dict((model.matrix.translation[0], (model, self.snapshot(model)))
                      for model in self.owner.models)
        self.outline.update([line(200), line(0), line(100)], self.COLORS)
        for x, (model, snapshot) in before.items():
            self.assertIs(self.model_at(x), model)
            self.assertEqual(self.snapshot(model), snapshot)
        self.assertEqual(len(self.owner.add_calls), 3)
        self.assertFalse(self.owner.delete_calls)

    def test_growth_and_insertion_leave_distant_segments_untouched(self):
        self.outline.update([line(0), line(100), line(200)], self.COLORS)
        stable = [(self.model_at(x), x) for x in (101.5, 201.5)]
        before = dict((model, self.snapshot(model)) for model, x in stable)
        # New geometry comes before an unchanged segment: matching by list
        # position would needlessly reproject the distant, stationary smoke.
        self.outline.update([line(200), line(300), line(0, 4), line(100)],
                            self.COLORS)
        for model, x in stable:
            self.assertIs(self.model_at(x), model)
            self.assertEqual(self.snapshot(model), before[model])
        self.assertEqual(len(self.owner.add_calls), 4)
        self.assertEqual(len(self.owner.models), 4)
        self.assertFalse(self.owner.delete_calls)
        self.model_at(2.0)
        self.model_at(301.5)

    def test_changed_geometry_reuses_projector_without_reinitializing(self):
        self.outline.update([line(0)], self.COLORS)
        model = self.model_at(1.5)
        area = model.node_instance.area
        self.outline.update([line(0, 4)], self.COLORS)
        self.assertIs(self.model_at(2.0), model)
        self.assertEqual(area.count('setup'), 1)
        self.assertEqual(area.count('size'), 1)
        self.assertAlmostEqual(area.size[0], 4.06)
        self.assertEqual(area.count('heights'), 2)
        self.assertEqual(area.count('collision'), 1)
        self.assertEqual(area.count('cutoff'), 1)
        self.assertEqual(len(self.owner.add_calls), 1)
        self.assertFalse(self.owner.delete_calls)

    def test_color_only_change_does_not_reproject_terrain(self):
        self.outline.update([line(0)], self.COLORS)
        model = self.model_at(1.5)
        area = model.node_instance.area
        matrices = (list(model.matrix.rotation_calls),
                    list(model.matrix.translation_calls))
        # A later enemy cloud can take ownership without changing this edge.
        self.outline.update([line(0, team=2)], self.COLORS)
        self.assertIs(self.model_at(1.5), model)
        self.assertEqual(area.color, 0xFF000000 | self.COLORS[2])
        self.assertEqual(area.count('color'), 1)
        self.assertEqual(area.count('setup'), 1)
        self.assertEqual(area.count('heights'), 1)
        self.assertEqual(area.count('size'), 0)
        self.assertEqual(matrices, (model.matrix.rotation_calls,
                                    model.matrix.translation_calls))
        updated_colors = dict(self.COLORS)
        updated_colors[2] = 0xCCCCCC
        self.outline.update([line(0, team=2)], updated_colors)
        self.assertEqual(area.color, 0xFFCCCCCC)
        self.assertEqual(area.count('color'), 2)
        self.assertEqual(area.count('heights'), 1)

    def test_moved_segment_with_same_length_reprojects_without_resizing(self):
        self.outline.update([line(0)], self.COLORS)
        model = self.model_at(1.5)
        area = model.node_instance.area
        self.outline.update([line(10)], self.COLORS)
        self.assertIs(self.model_at(11.5), model)
        self.assertEqual(area.count('setup'), 1)
        self.assertEqual(area.count('size'), 0)
        self.assertEqual(area.count('heights'), 2)
        self.assertEqual(len(model.matrix.translation_calls), 2)

    def test_failed_initial_projection_rolls_back_attached_resources(self):
        self.fail_new_heights = True
        with self.assertRaises(RuntimeError):
            self.outline.update([line(0)], self.COLORS)
        failed_model = self.owner.add_calls[0]
        self.assertFalse(self.owner.models)
        self.assertEqual(self.owner.delete_calls, [failed_model])
        self.assertEqual(len(failed_model.node_instance.detach_calls), 1)
        self.outline.destroy()
        self.assertEqual(self.owner.delete_calls, [failed_model])
        self.fail_new_heights = False
        self.outline.update([line(0)], self.COLORS)
        self.assertIsNot(self.model_at(1.5), failed_model)
        self.assertEqual(len(self.owner.models), 1)

    def test_removed_segments_are_destroyed_immediately(self):
        self.outline.update([line(0), line(100)], self.COLORS)
        kept, removed = self.model_at(1.5), self.model_at(101.5)
        self.outline.update([line(0)], self.COLORS)
        self.assertEqual(self.owner.models, [kept])
        self.assertEqual(self.owner.delete_calls, [removed])
        self.assertEqual(len(removed.node_instance.detach_calls), 1)
        self.outline.update([], self.COLORS)
        self.assertFalse(self.owner.models)
        self.assertEqual(set(self.owner.delete_calls), {kept, removed})
        self.assertEqual(len(kept.node_instance.detach_calls), 1)
        self.outline.destroy()
        self.assertEqual(len(self.owner.delete_calls), 2)

    def test_destroy_attempts_every_resource_when_cleanup_raises(self):
        self.outline.update([line(0), line(100)], self.COLORS)
        models = list(self.owner.models)
        models[0].fail_delete = True
        models[1].node_instance.fail_detach = True
        self.outline.destroy()
        self.assertEqual(set(self.owner.delete_calls), set(models))
        for model in models:
            self.assertEqual(len(model.node_instance.detach_calls), 1)
        self.outline.destroy()
        self.assertEqual(len(self.owner.delete_calls), 2)


if __name__ == '__main__':
    unittest.main()
