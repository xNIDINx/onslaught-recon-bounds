package {
    import flash.display.DisplayObjectContainer;
    import flash.display.Sprite;
    import flash.display.Graphics;
    import flash.display.LineScaleMode;
    import flash.events.Event;
    import flash.geom.Rectangle;
    import flash.utils.getTimer;
    import net.wg.infrastructure.base.AbstractView;
    import net.wg.infrastructure.interfaces.IManagedContainer;
    import net.wg.infrastructure.interfaces.IManagedContent;
    import net.wg.infrastructure.interfaces.IView;
    import net.wg.data.constants.generated.LAYER_NAMES;

    public class NidinSmokeContourUI extends AbstractView {
        private var map:DisplayObjectContainer;
        private var layer:Sprite = new Sprite();
        private var data:Array = [];
        private var dirty:Boolean = true;
        private var nextSearch:int = 0;
        private var lastWidth:Number = -1;
        private var lastHeight:Number = -1;

        public function NidinSmokeContourUI() {
            super();
            mouseEnabled = mouseChildren = false;
            layer.mouseEnabled = layer.mouseChildren = false;
        }
        override protected function onPopulate():void {
            super.onPopulate();
            addEventListener(Event.EXIT_FRAME, onFrame, false, 0, true);
        }
        override protected function nextFrameAfterPopulateHandler():void {
            super.nextFrameAfterPopulateHandler();
            if(parent != App.instance) {
                leaveModalFocus();
                if(parent is IManagedContainer) parent.removeChild(this);
                DisplayObjectContainer(App.instance).addChild(this);
                App.containerMgr.updateFocus();
            }
        }
        override protected function onDispose():void {
            removeEventListener(Event.EXIT_FRAME, onFrame);
            detach();
            data = [];
            super.onDispose();
        }
        public function as_setContours(value:Array):void {
            data = value == null ? [] : value;
            dirty = true;
            if(data.length == 0) layer.graphics.clear();
        }
        private function detach():void {
            if(layer.parent) layer.parent.removeChild(layer);
            layer.graphics.clear();
            map = null;
        }
        private function findMap():void {
            var container:DisplayObjectContainer = App.containerMgr.getContainer(
                LAYER_NAMES.LAYER_ORDER.indexOf(LAYER_NAMES.VIEWS)) as DisplayObjectContainer;
            if(!container) return;
            for(var i:int=0; i<container.numChildren; i++) {
                var content:IManagedContent = container.getChildAt(i) as IManagedContent;
                var view:IView = content ? content.sourceView : null;
                if(view && "minimap" in view) {
                    var candidate:DisplayObjectContainer = Object(view).minimap as DisplayObjectContainer;
                    if(candidate && "background" in candidate && "entriesContainer" in candidate) {
                        map = candidate;
                        map.addChildAt(layer, map.getChildIndex(Object(map).entriesContainer));
                        dirty = true;
                        trace("[nidin.onslaught_recon_bounds.contour] minimap attached");
                        return;
                    }
                }
            }
        }
        private function onFrame(event:Event):void {
            try {
                if(map && !map.stage) detach();
                if(!map) {
                    if(getTimer() >= nextSearch) {
                        nextSearch = getTimer()+500;
                        findMap();
                    }
                    if(!map) return;
                }
                var bg:Object = Object(map).background;
                var w:Number = bg.width;
                var h:Number = bg.height;
                layer.x = bg.x; layer.y = bg.y;
                if(w != lastWidth || h != lastHeight) dirty = true;
                if(!dirty || w <= 0 || h <= 0) return;
                lastWidth = w; lastHeight = h;
                layer.scrollRect = new Rectangle(0,0,w,h);
                var g:Graphics = layer.graphics;
                g.clear();
                for each(var line:Object in data) {
                    var points:Array = line.points as Array;
                    if(!points || points.length < 4) continue;
                    g.lineStyle(3,uint(line.color),1,false,LineScaleMode.NONE);
                    g.moveTo(Number(points[0])*w,Number(points[1])*h);
                    for(var j:int=2; j+1<points.length; j+=2)
                        g.lineTo(Number(points[j])*w,Number(points[j+1])*h);
                }
                dirty = false;
            } catch(error:Error) {
                trace("[nidin.onslaught_recon_bounds.contour] " + error.message);
                detach();
                nextSearch = getTimer()+5000;
            }
        }
    }
}
