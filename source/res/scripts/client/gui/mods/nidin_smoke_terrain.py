"""Reusable terrain-projected line segments, following native BorderVisual."""
import math
import logging
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
        segments = [(p, q, colors[team]) for team, points in lines
                    for p, q in zip(points, points[1:])]
        for i, (p, q, color) in enumerate(segments):
            if i == len(self.segments):
                model = BigWorld.Model('')
                matrix = Math.Matrix()
                node = model.node('')
                area = BigWorld.PyTerrainSelectedArea()
                node.attach(area)
                try:
                    model.addMotor(BigWorld.Servo(matrix))
                    self.owner.addModel(model)
                except Exception:
                    node.detach(area)
                    raise
                self.segments.append((model, matrix, node, area))
            model, matrix, node, area = self.segments[i]
            dx, dz = q[0]-p[0], q[2]-p[2]
            length = math.hypot(dx, dz)
            # Native sector border's long axis is local X.
            matrix.setRotateYPR((math.atan2(dx, dz)+math.pi*0.5, 0, 0))
            matrix.translation = Math.Vector3((p[0]+q[0])*0.5, (p[1]+q[1])*0.5, (p[2]+q[2])*0.5)
            area.setup(self.model_path, Math.Vector2(length+0.06, 0.35), 0.25, 0xFF000000 | color)
            area.enableAccurateCollision(True)
            area.setCutOffDistance(5.0)
            area.updateHeights()
        while len(self.segments) > len(segments):
            self._drop(self.segments.pop())

    def _drop(self, item):
        model, matrix, node, area = item
        try:
            self.owner.delModel(model)
        except Exception:
            LOG.exception('Cannot remove smoke segment model')
        try:
            node.detach(area)
        except Exception:
            LOG.exception('Cannot detach smoke segment')

    def destroy(self):
        while self.segments:
            self._drop(self.segments.pop())
