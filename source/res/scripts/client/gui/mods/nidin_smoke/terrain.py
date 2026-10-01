"""Reusable terrain-projected line segments, following native BorderVisual."""
import math
import logging
from collections import defaultdict
import BigWorld
import Math
import ResMgr

LOG = logging.getLogger('nidin.onslaught_recon_bounds.terrain')


class TerrainOutline(object):
    def __init__(self):
        self.owner = BigWorld.player()
        self.segments = []
        self.model_path = ResMgr.openSection('scripts/dynamic_objects.xml')['SectorBorderVisual/modelPath'].asString

    def update(self, lines, colors):
        segments = [(tuple(p), tuple(q), colors[team]) for team, points in lines
                    for p, q in zip(points, points[1:])]
        # Reserve every exact match before recycling anything. A growing early
        # arc must not steal the objects belonging to an unchanged later arc.
        available = defaultdict(list)
        for item in self.segments:
            available[item['geometry']].append(item)
        matched = []
        for p, q, color in segments:
            bucket = available.get((p, q))
            matched.append(bucket.pop() if bucket else None)
        spare = [item for bucket in available.values() for item in bucket]
        active = []
        for (p, q, color), item in zip(segments, matched):
            if item is None:
                if spare:
                    item = spare.pop()
                else:
                    item = self._create(p, q, color)
                    # Keep ownership during partial failure so the caller's
                    # destroy() also cleans objects created in this update.
                    self.segments.append(item)
            self._update(item, p, q, color)
            active.append(item)
        for item in spare:
            self._drop(item)
        self.segments = active

    @staticmethod
    def _place(matrix, p, q):
        dx, dz = q[0]-p[0], q[2]-p[2]
        matrix.setRotateYPR((math.atan2(dx, dz)+math.pi*0.5, 0, 0))
        matrix.translation = Math.Vector3((p[0]+q[0])*0.5, (p[1]+q[1])*0.5, (p[2]+q[2])*0.5)
        return math.hypot(dx, dz)

    def _create(self, p, q, color):
        item = dict(model=None, matrix=None, node=None, area=None,
                    attached=False, added=False, geometry=None, color=None, length=None)
        try:
            item['model'] = model = BigWorld.Model('')
            item['matrix'] = matrix = Math.Matrix()
            item['node'] = node = model.node('')
            item['area'] = area = BigWorld.PyTerrainSelectedArea()
            length = self._place(matrix, p, q)
            node.attach(area)
            item['attached'] = True
            area.setup(self.model_path, Math.Vector2(length+0.06, 0.35), 0.25, 0xFF000000 | color)
            area.enableAccurateCollision(True)
            area.setCutOffDistance(5.0)
            model.addMotor(BigWorld.Servo(matrix))
            self.owner.addModel(model)
            item['added'] = True
            area.updateHeights()
            item.update(geometry=(p,q), color=color, length=length)
            return item
        except Exception:
            self._drop(item)
            raise

    def _update(self, item, p, q, color):
        area = item['area']
        if item['geometry'] != (p,q):
            length = self._place(item['matrix'], p, q)
            if length != item['length']:
                area.setSize(Math.Vector2(length+0.06, 0.35))
            area.updateHeights()
            item.update(geometry=(p,q), length=length)
        if color != item['color']:
            area.setColor(0xFF000000 | color)
            item['color'] = color

    def _drop(self, item):
        if item['added']:
            item['added'] = False
            try:
                self.owner.delModel(item['model'])
            except Exception:
                LOG.exception('Cannot remove smoke segment model')
        if item['attached']:
            item['attached'] = False
            try:
                item['node'].detach(item['area'])
            except Exception:
                LOG.exception('Cannot detach smoke segment')

    def destroy(self):
        while self.segments:
            self._drop(self.segments.pop())
