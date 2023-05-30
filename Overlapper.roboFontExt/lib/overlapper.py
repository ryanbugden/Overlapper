import AppKit
from fontTools.misc.bezierTools import splitCubicAtT, approximateCubicArcLength
from fontTools.ufoLib.pointPen import PointToSegmentPen  # for Frank’s code setting start points to on-curves
from mojo.subscriber import Subscriber, registerGlyphEditorSubscriber
from mojo.extensions import getExtensionDefault
from mojo.UI import CurrentWindow, getDefault
from math import sqrt
import merz
import time



DEBUG = False

EXTENSION_KEY = 'com.ryanbugden.overlapper.settings'
def get_setting_from_defaults(setting):
    all_settings = getExtensionDefault(EXTENSION_KEY, fallback={'hotkey': 'v'})
    return all_settings[setting] 


# Testing method from Jackson. Add @timeit before methods to test
def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        if 'log_time' in kw:
            name = kw.get('log_name', method.__name__.upper())
            kw['log_time'][name] = int((te - ts) * 1000)
        else:
            if DEBUG == True: print('%r  %2.2f ms' %(method.__name__, (te - ts) * 1000))
            pass
        return result
    return timed


def lengthen_line(pt1, pt2, factor, direction="out"):
    x1, y1, x2, y2           = pt1[0], pt1[1], pt2[0], pt2[1]
    delta_x, delta_y         = x2 - x1, y2 - y1
    new_delta_x, new_delta_y = delta_x * factor, delta_y * factor
    new_x, new_y             = new_delta_x + x1, new_delta_y + y1
    
    if direction == "in":
        return ((x2, y2), (new_x, new_y))
    else:
        return ((new_x, new_y), (x2, y2))


def get_vector_distance(pt1, pt2):
    x1, y1, x2, y2 = pt1.x, pt1.y, pt2.x, pt2.y
    dist = sqrt((x2-x1)**2 + (y2-y1)**2)

    return abs(dist)


def my_round(x, base=1):
    return base * round(x/base)


# ======================================================================================


class Overlapper(Subscriber):
    '''
    A tool that allows you to dynamically add overlaps (+) or chamfers (-) 
    to hard corners of contours in RoboFont.
    '''

    def build(self):
        self.allow_redraw = True
        self.tool_value = 0
        self.stored_pts = None
        self.stored_components = ()
        self.key_down = False
        self.initial_x = None
        self.initial_y = None
        self.current_x = None
        self.ready_to_go = False
        self.mod_active = False
        self.g = None

        self.hotkey = get_setting_from_defaults('hotkey')
        self.snap  = getDefault("glyphViewRoundValues")  # Expensing up top to add performance, but if snapping value is changed mid-session, RF will need restart for this to take effect on Overlapper
        
        self.glyph_editor = self.getGlyphEditor()
        self.bg_container = self.glyph_editor.extensionContainer(
            identifier="Overlapper.foreground", 
            location="foreground", 
            clear=True
            )

        self.stroked_preview = self.bg_container.appendPathSublayer(
            strokeColor=(0,0,0,0),
            fillColor=(0,0,0,0),
            strokeWidth=1
            )
        
        self.info = self.bg_container.appendTextLineSublayer(
            position=(100, 100),
            size=(500, 160),
            text="Overlapping",
            fillColor=(0,0,0,0),
            horizontalAlignment="center",
            pointSize=12,
            visible=False,
            weight="bold",
            offset=(0,-40)
            )
        self.set_colors()  # Set the correct colors for outline and text (light or dark mode), at least upon load. Will set again later on.


    def set_colors(self):
        # Check to see if you're in dark mode or not
        self.mode_suffix = ""
        if AppKit.NSApp().appearance() == AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua):
            self.mode_suffix = ".dark"
        self.color = getDefault(f"glyphViewStrokeColor{self.mode_suffix}")

        self.stroked_preview.setStrokeColor(self.color)
        self.info.setFillColor(self.color)


    def start_with_oncurve(self, contour):
        with contour.glyph.undo(f'Make contour #{contour.index} start with an oncurve point'):
            # Hold selection
            sels = []
            for pt in contour.points:
                if pt.selected == True:
                    sels.append(pt)

            # Set the start point to the nearest oncurve
            for point_i, point in enumerate(contour.points):
                if point.type != "offcurve":
                    contour.setStartPoint(point_i)
                    break

            # Reapply selection
            for pt in contour.points:
                if DEBUG == True: print("looking at pt:", pt)
                for sel_pt in sels:
                    # This is messy. I'm trying to never deselect the selected points, but this attempts to get it back by looking at pt.type and coordinates. hacky.
                    if pt.type == sel_pt.type and (pt.x, pt.y) == (sel_pt.x, sel_pt.y):
                        pt.selected = True


    @timeit
    def get_selection_data(self, offset):
        self.g = CurrentGlyph()
        sel_points = []
        for c in self.g.contours:
            i = 0
            for seg in c.segments:
                for pt in seg.points:
                    if pt.selected:
                        sel_points.append(pt)
        if DEBUG == True: print(sel_points)

        sel_hubs = {}
        new_sel_hubs_in = {}
        new_sel_hubs_out = {}
        for c in self.g.contours:
            for i, seg in enumerate(c.segments):
        
                # Try to associate selected points with their respective segments
                for pt in sel_points:
                    if pt in seg.points:
                    
                        # Get inbound curve information for selected point
                        try:
                            seg_before = c.segments[i-1]
                        except IndexError:
                            seg_before = c.segments[-1]

                        onC_before = seg_before.points[-1]
                        if len(seg.points) == 3:
                            onC_here = seg.points[2]
                            sel_hubs.update({(onC_here.x, onC_here.y): {"in": [onC_before, seg.points[0], seg.points[1], onC_here]}})
                            in_dist = approximateCubicArcLength((onC_before.x, onC_before.y), (seg.points[0].x, seg.points[0].y), (seg.points[1].x, seg.points[1].y), (onC_here.x, onC_here.y))
                            if DEBUG == True: print("arc in_dist", in_dist)
                        else:
                            onC_here = seg.points[0]
                            sel_hubs.update({(onC_here.x, onC_here.y): {"in": [onC_before, onC_here]}})
                            in_dist = get_vector_distance(onC_here, onC_before)
                            if DEBUG == True: print("line in_dist", in_dist)
                        
                        
                        # Get outbound curve information for selected point
                        try:
                            seg_after = c.segments[i+1]
                            onC_after = seg_after.points[-1]
                        except IndexError:
                            seg_after = c.segments[0]
                        if DEBUG == True: print("seg_before:", seg_before, "\tseg_after:", seg_after)

                        onC_after = seg_after.points[-1]

                        if len(seg_after.points) == 3:
                            sel_hubs[(onC_here.x, onC_here.y)].update({"out": [onC_here, seg_after.points[0], seg_after.points[1], onC_after]})
                            out_dist = approximateCubicArcLength((onC_here.x, onC_here.y), (seg_after.points[0].x, seg_after.points[0].y), (seg_after.points[1].x, seg_after.points[1].y), (onC_after.x, onC_after.y))
                            if DEBUG == True: print("arc out_dist", out_dist)
                        else:
                            sel_hubs[(onC_here.x, onC_here.y)].update({"out": [onC_here, onC_after]})
                            out_dist = get_vector_distance(onC_here, onC_after)
                            if DEBUG == True: print("line out_dist", out_dist)

                        in_factor = (float(offset) + float(in_dist)) / float(in_dist)
                        out_factor = (float(offset) + float(out_dist)) / float(out_dist)

                        if DEBUG == True:
                            print("in_factor", in_factor)
                            print("out_factor", out_factor)
                            print("sel_hubs", sel_hubs)
                        
                        # Start building output
                        key = (onC_here.x, onC_here.y)
                        _in = sel_hubs[key]["in"]
                        _out = sel_hubs[key]["out"]
                    
                        in_args = []
                        for i in range(len(_in)):
                            in_args.append((_in[i].x, _in[i].y))
                        
                        out_args = []
                        for i in range(len(_out)):
                            out_args.append((_out[i].x, _out[i].y))

                        if DEBUG == True: print("in_args, out_args", in_args, out_args)

                        if len(in_args) == 4:
                            in_result = splitCubicAtT(in_args[0], in_args[1], in_args[2], in_args[3], in_factor)[0]
                        else:
                            in_result = lengthen_line(in_args[0], in_args[1], in_factor, "in")
                        
                        if len(out_args) == 4:
                            out_result = splitCubicAtT(out_args[0], out_args[1], out_args[2], out_args[3], -(out_factor-1))[1]
                        else:
                            out_result = lengthen_line(out_args[0], out_args[1], -(out_factor-1), "out")
                                
                        new_sel_hubs_in.update({key: in_result})
                        new_sel_hubs_out.update({key: out_result})

                        if DEBUG == True: print("new_sel_hubs_in", new_sel_hubs_in, "new_sel_hubs_out", new_sel_hubs_out)

        return (new_sel_hubs_in, new_sel_hubs_out)


    @timeit
    def draw_overlap_preview(self):
        outline = self.get_overlapped_glyph()

        if DEBUG == True: 
            for c_i in range(len(outline.contours)):
                c = outline.contours[c_i]
                for seg in c.segments:
                    print(len(seg))
                    if len(seg) == 2:
                        print("WHOA BUDDY! look at contour index:", c_i)
                        print("seg.onCurve, seg.offCurve", seg.onCurve, seg.offCurve)
                        for pt in seg.points:
                            print(pt, pt.type, pt.index)

        glyph_path = outline.getRepresentation("merz.CGPath")
        self.stroked_preview.setPath(glyph_path)

        
    @timeit
    def get_overlapped_glyph(self):
        in_result, out_result = self.get_selection_data(self.tool_value)

        self.hold_g = self.g.copy()
        # Remove components for this preview. They're added back on mouse-up.
        self.hold_g.clearComponents()

        for c in self.hold_g:
            hits = 0  # How many points you've gone through in the loop that are selected. this will bump up the index # assigned to newly created segments
            for i, seg in enumerate(c.segments):
                x, y = seg.onCurve.x, seg.onCurve.y
                next_x, next_y = None, None
                if (x, y) in in_result.keys():
                    

                    if len(seg.points) == 3:
                        seg.offCurve[0].x, seg.offCurve[0].y = in_result[(x, y)][-3][0], in_result[(x, y)][-3][1]
                        seg.offCurve[1].x, seg.offCurve[1].y = in_result[(x, y)][-2][0], in_result[(x, y)][-2][1]
                    else:
                        if DEBUG == True: print("a")
                        pass
                    seg.onCurve.x, seg.onCurve.y = in_result[(x, y)][-1][0], in_result[(x, y)][-1][1]
                    
                    if DEBUG == True: 
                        print("hits", hits)
                        print("UNIQUE XY", (x,y))
                        print("len(c.segments)", len(c.segments))
                        print("i", i)
                        print("in_result, out_result", in_result, out_result)
                        print("len(in_result)", len(in_result))

                    # Add a gap, special case if starting over on the contour
                    if i + 1 == len(c.segments) - hits:
                        if DEBUG == True: print("1", "this is the end of the contour", "should be putting a point at the 0 index of: ",  out_result[(x, y)])
                        c.insertSegment(0, type="line", points=[out_result[(x, y)][0]], smooth=False)
                        next_seg = c.segments[1]
                    else:
                        if DEBUG == True: print("2")
                        c.insertSegment(i + 1 + hits, type="line", points=[out_result[(x, y)][0]], smooth=False)
                        try:
                            if DEBUG == True: print("2a")
                            next_seg = c.segments[i + 2 + hits]
                        except IndexError:
                            if DEBUG == True: print("2b")
                            next_seg = c.segments[0]

                    # Onto the next segment, change the point positions                 
                    if len(next_seg.points) == 3:
                        if DEBUG == True: print("3", "len(seg), len(next_seg)", len(seg), len(next_seg))
                        next_seg.offCurve[0].x, next_seg.offCurve[0].y = out_result[(x, y)][-3][0], out_result[(x, y)][-3][1]
                        next_seg.offCurve[1].x, next_seg.offCurve[1].y = out_result[(x, y)][-2][0], out_result[(x, y)][-2][1]
                    else:
                        if DEBUG == True: print("4")
                        pass
                    # Should all do this ???:  next_seg.onCurve.x, y?? THIS MIGHT NOT BE NECESSARY, because it's just describing the next point
                    next_x, next_y = out_result[(x, y)][-1][0], out_result[(x, y)][-1][1]
                    if DEBUG == True: print("5", "len(seg), len(next_seg)", len(seg), len(next_seg))

                    # You just went through and added another point, so prepare to bump up the index one more than previously assumed
                    hits += 1

        return self.hold_g
        
    
    @timeit
    def overlap_it(self):
        with self.g.undo("Overlap"):
            try:
                self.g.clear()
                self.g.appendGlyph(self.hold_g)

                # Restore components
                for comp in self.stored_components:
                    self.g.appendComponent(component=comp)

                if self.snap != 0:
                    for c in self.g.contours:
                        for pt in c.points:
                            pt.x, pt.y = my_round(pt.x, snap), my_round(pt.y,  snap)
                            
                self.g.changed()
            except:
                pass


    def roboFontDidSwitchCurrentGlyph(self, info):
        self.window = CurrentWindow()


    @timeit
    def glyphEditorDidKeyDown(self, info):
        if DEBUG == True: print("glyphEditorDidKeyDown", info)

        char = info['deviceState']['keyDownWithoutModifiers']
        self.hotkey = get_setting_from_defaults('hotkey')
        if char == self.hotkey and self.mod_active == False:
            self.g = CurrentGlyph()

            if self.g.selectedPoints:
                self.ready_to_go = True
            else:
                self.ready_to_go = False
                return

            # Before we start, make sure the starting point is not an off-curve (that creates issues with segment insertion [illegal point counts])
            if self.allow_redraw == True:    

                for contour in self.g.contours:
                    first_point = contour.points[0]
                    first_bPoint = contour.bPoints[0]
                    first_point_coords = (first_point.x, first_point.y)
                    if first_point_coords != first_bPoint.anchor:
                        print(
                            'Fixing off-curve start point in '
                            f'{self.g.name}, ({self.g.font.info.styleName})'
                        )
                        self.start_with_oncurve(contour)  # Simple alternative to redrawing glyph

                self.g.changed()

                # Only do this once at the beginning 
                self.allow_redraw  = False

            # Store the components
            self.stored_components = self.g.components

            self.draw_overlap_preview()
            self.set_colors()
            self.stroked_preview.setVisible(True)

            self.key_down = True

    
    def glyphEditorDidKeyUp(self, info):
        char = info['deviceState']['keyDownWithoutModifiers']
        if char == self.hotkey and self.mod_active == False:
            self.key_down = False  # Don't need this

            if self.ready_to_go == True:
                self.overlap_it()

            self.initial_x = None
            self.tool_value = 0
            
            self.info.setVisible(False)
            self.stroked_preview.setVisible(False)

            self.ready_for_init = True
            self.allow_redraw  = True


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
        if self.key_down == True:
            x = info['locationInGlyph'].x
            y = info['locationInGlyph'].y

            if self.initial_x == None:
                self.initial_x = int(x)
                self.initial_y = int(y)
            self.current_x = int(x)
            self.tool_value = int((self.current_x - self.initial_x)/2)
            
            self.draw_overlap_preview()

            # Draw info
            self.info.setVisible(True)
            self.info.setText(f" ← Overlapping → \n{self.tool_value}")
            self.info.setPosition((self.initial_x, y))
            

# ======================================================================================
        
if __name__ == "__main__":    
    registerGlyphEditorSubscriber(Overlapper)

