from AppKit import NSApp, NSColor, NSTextAlignmentRight, NSTextAlignmentLeft
from AppKit import NSImage
from fontTools.ufoLib.pointPen import AbstractPointPen
from fontTools.misc.bezierTools import splitCubicAtT, approximateCubicArcLength
from lib.UI.toolbarGlyphTools import ToolbarGlyphTools
from mojo.subscriber import Subscriber, registerGlyphEditorSubscriber
from mojo.UI import CurrentGlyphWindow, CurrentWindow, getDefault
import mojo.drawingTools as dt
import math
import os
import re
import merz
from merz.tools.drawingTools import NSImageDrawingTools
import time


'''
This was adapted from the Add Overlap extension by Alexandre Saumier Demers.

Thank you for the advice:
- Frank Griesshammer
- Jackson Cavanaugh
- Andy Clymer

Next steps:
- Speed it up. Only focus on specific segments as opposed to the whole glyph?
- Keep the "Overlapping" message on the same X it was when mouseDown

Ryan Bugden
2022.10.28
2022.03.18
'''


# testing method from Jackson; add @timeit before methods to test
def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        if 'log_time' in kw:
            name = kw.get('log_name', method.__name__.upper())
            kw['log_time'][name] = int((te - ts) * 1000)
        else:
            # print('%r  %2.2f ms' %(method.__name__, (te - ts) * 1000))
            pass
        return result
    return timed


def lengthenLine(pt1, pt2, factor, direction="out"):
    x1, y1, x2, y2           = pt1[0], pt1[1], pt2[0], pt2[1]
    delta_x, delta_y         = x2 - x1, y2 - y1
    new_delta_x, new_delta_y = delta_x * factor, delta_y * factor
    new_x, new_y             = new_delta_x + x1, new_delta_y + y1
    
    if direction == "in":
        return ((x2, y2), (new_x, new_y))
    else:
        return ((new_x, new_y), (x2, y2))


def vectorDistance(pt1, pt2):
    x1, y1, x2, y2 = pt1.x, pt1.y, pt2.x, pt2.y
    dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)

    return abs(dist)


def myRound(x, base=1):
    return base * round(x/base)


# ======================================================================================


class Overlapper(Subscriber):

    base_path = os.path.dirname(__file__)
    toolValue = 0

    def build(self):

        self.stored_pts = None
        self.v = False
        self.initialX = None
        self.initialY = None
        self.currentX = None
        self.ready_to_go = False
        self.mod_active = False
        
        self.glyph_editor = self.getGlyphEditor()
        self.bg_container = self.glyph_editor.extensionContainer(
            identifier="Overlapper.foreground", 
            location="foreground", 
            clear=True
            )

        self.stroked_preview = self.bg_container.appendPathSublayer(
            strokeColor=(0,0,0,1),
            fillColor=(0,0,0,0),
            strokeWidth=1
            )

        self.info = self.bg_container.appendTextLineSublayer(
            position=(100, 100),
            size=(400, 100),
            text="Overlapping",
            fillColor=(0, 0, 0, 1),
            horizontalAlignment="center",
            pointSize=12,
            visible=False,
            weight="bold",
            offset=(0,-50)
            )


    # @timeit
    def getSelectionData(self, offset):
        self.g = CurrentGlyph()
        sel_points = []
        for c in self.g.contours:
            i = 0
            for seg in c.segments:
                for pt in seg.points:
                    if pt.selected:
                        sel_points.append(pt)
                    
        # # print(sel_points)
        sel_hubs = {}
        new_sel_hubs_in = {}
        new_sel_hubs_out = {}
        for c in self.g.contours:
            for i, seg in enumerate(c.segments):
        
                # try to associate selected points with their respective segments
                for pt in sel_points:
                    if pt in seg.points:
                    
                        # get inbound curve information for selected point
                        try:
                            seg_before = c.segments[i-1]
                        except IndexError:
                            seg_before = c.segments[-1]

                        onC_before = seg_before.points[-1]
                        if len(seg.points) == 3:
                            onC_here = seg.points[2]
                            sel_hubs.update({(onC_here.x, onC_here.y): {"in": [onC_before, seg.points[0], seg.points[1], onC_here]}})
                            in_dist = approximateCubicArcLength((onC_before.x, onC_before.y), (seg.points[0].x, seg.points[0].y), (seg.points[1].x, seg.points[1].y), (onC_here.x, onC_here.y))
                            # # print("arc in_dist", in_dist)
                        else:
                            onC_here = seg.points[0]
                            sel_hubs.update({(onC_here.x, onC_here.y): {"in": [onC_before, onC_here]}})
                            in_dist = vectorDistance(onC_here, onC_before)
                            # # print("line in_dist", in_dist)
                        
                        
                        # get outbound curve information for selected point
                        try:
                            seg_after = c.segments[i+1]
                            onC_after = seg_after.points[-1]
                        except IndexError:
                            seg_after = c.segments[0]
                        # print("seg_before", seg_before)
                        # print("seg_after", seg_after)

                        onC_after = seg_after.points[-1]

                        if len(seg_after.points) == 3:
                            sel_hubs[(onC_here.x, onC_here.y)].update({"out": [onC_here, seg_after.points[0], seg_after.points[1], onC_after]})
                            out_dist = approximateCubicArcLength((onC_here.x, onC_here.y), (seg_after.points[0].x, seg_after.points[0].y), (seg_after.points[1].x, seg_after.points[1].y), (onC_after.x, onC_after.y))
                            # # print("arc out_dist", out_dist)
                        else:
                            sel_hubs[(onC_here.x, onC_here.y)].update({"out": [onC_here, onC_after]})
                            out_dist = vectorDistance(onC_here, onC_after)
                            # # print("line out_dist", out_dist)

                        in_factor = (float(offset) + float(in_dist)) / float(in_dist)
                        out_factor = (float(offset) + float(out_dist)) / float(out_dist)

                        # print("in_factor", in_factor)
                        # print("out_factor", out_factor)
                        # print("sel_hubs", sel_hubs)
                        
                        key = (onC_here.x, onC_here.y)
                        _in = sel_hubs[key]["in"]
                        _out = sel_hubs[key]["out"]
                    
                        in_args = []
                        for i in range(len(_in)):
                            in_args.append((_in[i].x, _in[i].y))
                        
                        out_args = []
                        for i in range(len(_out)):
                            out_args.append((_out[i].x, _out[i].y))

                        # print("in_args, out_args", in_args, out_args)

                        if len(in_args) == 4:
                            in_result = splitCubicAtT(in_args[0], in_args[1], in_args[2], in_args[3], in_factor)[0]
                        else:
                            in_result = lengthenLine(in_args[0], in_args[1], in_factor, "in")
                        
                        if len(out_args) == 4:
                            out_result = splitCubicAtT(out_args[0], out_args[1], out_args[2], out_args[3], -(out_factor-1))[1]
                        else:
                            out_result = lengthenLine(out_args[0], out_args[1], -(out_factor-1), "out")
                                
                        new_sel_hubs_in.update({key: in_result})
                        new_sel_hubs_out.update({key: out_result})

                        # print("new_sel_hubs_in", new_sel_hubs_in)
                        # print("new_sel_hubs_out", new_sel_hubs_out)

        return (new_sel_hubs_in, new_sel_hubs_out)


    # @timeit
    def glyphEditorDidKeyDown(self, info):

        # print("glyphEditorDidKeyDown", info)

        char = info['deviceState']['keyDownWithoutModifiers']
        if char == "v" and self.mod_active == False:
            self.v = True

            self.drawOverlapPreview()
            self.stroked_preview.setVisible(True)

            if CurrentGlyph().selectedPoints != ():
                self.ready_to_go = True
            else:
                self.ready_to_go = False
            

    def glyphEditorDidKeyUp(self, info):

        char = info['deviceState']['keyDownWithoutModifiers']
        if char == "v" and self.mod_active == False:
            self.v = False # don't need this

            if self.ready_to_go == True:
                self.overlapIt()

            self.initialX = None
            self.toolValue = 0
            
            self.info.setVisible(False)
            self.stroked_preview.setVisible(False)

            self.ready_for_init = True


    def glyphEditorDidChangeModifiers(self, info):

        ds = info['deviceState']
        mods = [ds['shiftDown'], ds['optionDown'], ds['controlDown'], ds['commandDown']]
        self.mod_active = False
        for value in mods:
            if value > 0:
                self.mod_active = True
                break


    glyphEditorDidMouseMoveDelay = 0
    def glyphEditorDidMouseMove(self, info):

        if self.v == True:

            x = info['locationInGlyph'].x
            y = info['locationInGlyph'].y

            if self.initialX == None:
                self.initialX = int(x)
                self.initialY = int(y)
            self.currentX = int(x)
            self.toolValue = int((self.currentX - self.initialX)/2)
            
            self.drawOverlapPreview()

            # draw info
            self.info.setVisible(True)
            self.info.setText(f"← Overlapping → {self.toolValue}")
            self.info.setPosition((x, y))
            

    # @timeit
    def drawOverlapPreview(self):

        outline = self.getOverlappedGlyph()
        glyph_path = outline.getRepresentation("merz.CGPath")
        self.stroked_preview.setPath(glyph_path)

        
    # @timeit
    def getOverlappedGlyph(self):

        in_result, out_result = self.getSelectionData(self.toolValue)

        self.hold_g = self.g.copy()
        for c in self.hold_g:
            hits = 0 # how many points you've gone through in the loop that are selected. this will bump up the index # assigned to newly created segments
            for i, seg in enumerate(c.segments):
                x, y = seg.onCurve.x, seg.onCurve.y
                next_x, next_y = None, None
                if (x, y) in in_result.keys():
                    

                    if len(seg.points) == 3:
                        seg.offCurve[0].x, seg.offCurve[0].y = in_result[(x, y)][-3][0], in_result[(x, y)][-3][1]
                        seg.offCurve[1].x, seg.offCurve[1].y = in_result[(x, y)][-2][0], in_result[(x, y)][-2][1]
                    else:
                        # print("a")
                        pass
                    seg.onCurve.x, seg.onCurve.y = in_result[(x, y)][-1][0], in_result[(x, y)][-1][1]
                    
                    # print("hits", hits)
                    # print("UNIQUE XY", (x,y))
                    # print("len(c.segments)", len(c.segments))
                    # print("i", i)
                    # print("in_result, out_result", in_result, out_result)
                    # print("len(in_result)", len(in_result))
                    # add a gap, special case if starting over on the contour
                    if i + 1 == len(c.segments) - hits:
                        # print("1")
                        # # print("this is the end of the contour", "should be putting a point at the 0 index of: ",  out_result[(x, y)])
                        c.insertSegment(0, type="line", points=[out_result[(x, y)][0]], smooth=False)
                        next_seg = c.segments[1]
                    else:
                        # print("2")
                        c.insertSegment(i + 1 + hits, type="line", points=[out_result[(x, y)][0]], smooth=False)
                        try:
                            next_seg = c.segments[i + 2 + hits]
                        except IndexError:
                            next_seg = c.segments[0]

                    # onto the next segment, change the point positions                 
                    if len(next_seg.points) == 3:
                        # print("3")
                        next_seg.offCurve[0].x, next_seg.offCurve[0].y = out_result[(x, y)][-3][0], out_result[(x, y)][-3][1]
                        next_seg.offCurve[1].x, next_seg.offCurve[1].y = out_result[(x, y)][-2][0], out_result[(x, y)][-2][1]
                    else:
                        # print("4")
                        pass
                    # should all do this ???:  next_seg.onCurve.x, y??
                    next_x, next_y = out_result[(x, y)][-1][0], out_result[(x, y)][-1][1]

                    hits += 1

        return self.hold_g
        
    
    # @timeit
    def overlapIt(self):

        with self.g.undo("Overlap"):
            self.g.clear()
            self.g.appendGlyph(self.hold_g)

            snap = getDefault("glyphViewRoundValues")
            if snap != 0:
                for c in self.g.contours:
                    for pt in c.points:
                        pt.x, pt.y = myRound(pt.x, snap), myRound(pt.y,  snap)
                        
            self.g.changed()


    def roboFontDidSwitchCurrentGlyph(self, info):
        self.window = CurrentWindow()



# ======================================================================================
        
if __name__ == "__main__":    
    registerGlyphEditorSubscriber(Overlapper)

