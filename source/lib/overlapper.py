import AppKit
from fontTools.misc.bezierTools import splitCubicAtT, approximateCubicArcLength
from fontTools.ufoLib.pointPen import PointToSegmentPen  # for Frank’s code setting start points to on-curves
from mojo.subscriber import Subscriber, registerGlyphEditorSubscriber, getRegisteredSubscriberEvents, registerSubscriberEvent
from mojo.extensions import getExtensionDefault
from mojo.roboFont import version
from mojo.UI import CurrentWindow, getDefault
from mojo.events import postEvent
from math import sqrt, atan
import merz
import time
if version >= "4.4":
    from mojo.UI import appearanceColorKey


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
    try:
        x1, y1, x2, y2 = pt1.x, pt1.y, pt2.x, pt2.y
    except:
        x1, y1, x2, y2 = pt1[0], pt1[1], pt2[0], pt2[1]
    dist = sqrt((x2-x1)**2 + (y2-y1)**2)
    return abs(dist)

def my_round(x, base=1):
    return base * round(x/base)
        
def contour_has_points(contour, point_coordinates):
    for pt in contour.points:
        if (pt.x, pt.y) in point_coordinates:
            return True
    return False
    
def average_coordinates(list_of_coords):
    av_x = sum([x for (x, y) in list_of_coords]) / len(list_of_coords)
    av_y = sum([y for (x, y) in list_of_coords]) / len(list_of_coords)
    return(av_x, av_y)

def break_dict_into_pairs(selected_contours, dictionary):
    if len(dictionary.keys()) % 2 == 0 and len(dictionary.keys()) >= 2:
        coords = list(dictionary.keys())
        coord_pairs = []
        while len(coords) > 1:
            # print("coords", coords)
            two_noncontiguous = get_noncontiguous_near_coords(selected_contours, coords)
            # print("two_noncontiguous", two_noncontiguous)
            if two_noncontiguous not in coord_pairs:
                coord_pairs.append(two_noncontiguous)
                
                for noncontig_coord in tuple(two_noncontiguous):
                    # print()
                    # print("assessing whether", noncontig_coord, "is in", coords)
                    if noncontig_coord in coords:    
                        # print("removing", noncontig_coord)
                        # print()
                        coords.remove(noncontig_coord)
                    else:
                        print("Overlapper Error: (coord_pairs)", coord_pairs)
        # print("(coord_pairs)", coord_pairs)
        # Rebuild mini pair dictionaries
        pair_dicts = []
        for pair in coord_pairs:
            # print("len(pair)", len(pair))
            if len(pair) == 2:
                new_dict = {pair[0]: dictionary[pair[0]], pair[1]: dictionary[pair[1]]}
                pair_dicts.append(new_dict)
        return pair_dicts
    else:
        return [dictionary]
        
def add_contour_to_end(g, contour_a, contour_b):
    '''Adds one contour to another'''
    deleted = False
    b_copy = contour_b.copy()
    g.removeContour(contour_b)
    for pt in b_copy.points:
        if pt.type == 'move':
            contour_a.appendPoint(
                (pt.x, pt.y), 'line', pt.smooth, pt.name, pt.identifier)
        else:
            contour_a.appendPoint(
                (pt.x, pt.y), pt.type, pt.smooth, pt.name, pt.identifier)
    
def close_contour_at_coords(g, list_of_two_coords):
    points = []
    contours = []
    for contour in g:
        for pt in contour.points:
            if (pt.x, pt.y) in list_of_two_coords:
                points.append(pt)
                if pt.contour not in contours:
                    # Make sure the one with point index `0` is the second one
                    if pt.type != 'move':                        
                        contours.insert(0, pt.contour)
                    else:
                        contours.append(pt.contour)
    if DEBUG == True: print(contours)
    # If it's the same contour, just close it.
    if len(contours) == 1:
        for contour in g:
            for pt in contour.points:
                if (pt.x, pt.y) in list_of_two_coords:
                    if pt.type == 'move': pt.type = 'line'
    else:
        try:
            add_contour_to_end(g, contours[0], contours[1])
        # Open contours, or outside corners of contour that doesn't overlap with others.
        except IndexError:
            pass
            
def get_closest_two_coords(list_of_coordinates):
    closest_dist = 0
    closest_coords = []
    for coord in list_of_coordinates:
        for coord_2 in list_of_coordinates:
            dist = get_vector_distance(coord, coord_2)
            if dist != 0 and (dist < closest_dist or closest_dist == 0):
                closest_dist = dist
                closest_coords = [coord, coord_2]
    return closest_coords
    
def get_noncontiguous_near_coords(selected_contours, list_of_coordinates):
    # Based on indexes
    # print("list_of_coordinates", list_of_coordinates)
    if len(list_of_coordinates) <= 2:
        return tuple(list_of_coordinates)
    coord_pair = []
    coord_candidates = []
    index = None
    base_contour = None
    for c in selected_contours:
        for pt in c.points:
            if (pt.x, pt.y) in list_of_coordinates:
                if index == None: 
                    # print("step 1", (pt.x, pt.y))
                    if (pt.x, pt.y) in coord_pair:
                        # print("continuing")
                        continue
                    coord_pair.append((pt.x, pt.y))
                    index = pt.index
                    base_contour = pt.contour
                else:
                    # print("step 2", (pt.x, pt.y))
                    if pt.contour != base_contour:
                        coord_candidates.append((pt.x, pt.y))
                    if abs(pt.index - index) > 1:
                        coord_candidates.append((pt.x, pt.y))
    # print("coord_candidates", coord_candidates)
    coord_pair = tuple(get_closest_two_coords(coord_pair + coord_candidates))
    return coord_pair
                
def average_point_pos(point_to_move, other_point_coords):
    point_to_move.x = (point_to_move.x + other_point_coords[0])/2
    point_to_move.y = (point_to_move.y + other_point_coords[1])/2
    
def check_continuous(list_of_coords, tol=0.1):
    try:
        (min_x, min_y), (max_x, max_y) = min(list_of_coords), max(list_of_coords)
    except ValueError:  # Not sure why this is necessary. Catches empty lists, assumes not continuous.
        return False
    if list_of_coords[1][0] == list_of_coords[0][0]:
        general_angle = 0.7853981633974483  # 90 degrees
    else:
        # Choose first pair of coords to set the standard for angle
        general_angle = atan((list_of_coords[1][1] - list_of_coords[0][1])/(list_of_coords[1][0] - list_of_coords[0][0]))
    for i, coord in enumerate(list_of_coords):
        if (coord[0] - list_of_coords[i-1][0]) == 0:
            local_angle = 0.7853981633974483
        else:
            local_angle = atan((coord[1] - list_of_coords[i-1][1])/(coord[0] - list_of_coords[i-1][0]))
        if local_angle < general_angle - tol or local_angle > general_angle + tol:
            return False
    return True
    
def search_continuity(glyph, pair_of_points):
    for c in glyph.contours:
        # Get the indexes of our central pair of points
        indexes_to_analyze = []
        for pt in c.points:
            if (pt.x, pt.y) in pair_of_points:
                indexes_to_analyze.append(pt.index)
        # Add contiguous points to the search
        new_indexes_to_analyze = []
        for i in indexes_to_analyze:
            new_indexes_to_analyze.append(i)
            if i + 1 not in new_indexes_to_analyze and i + 1 < len(c.points):
                new_indexes_to_analyze.append(i + 1)
            if i - 1 not in new_indexes_to_analyze:
                if i - 1 == -1:
                    new_indexes_to_analyze.append(len(c.points) - 1)
                else:
                    new_indexes_to_analyze.append(i - 1)
        # Check if the coordinates of the four points segment runs along the same line
        coords_to_analyze = [(pt.x, pt.y) for pt in c.points if pt.index in new_indexes_to_analyze]
        if check_continuous(coords_to_analyze) == True:
            return True
    return False

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
        self.cross_success = False

        self.hotkey = get_setting_from_defaults('hotkey')
        self.snap  = getDefault("glyphViewRoundValues")  # Expensing up top to add performance, but if snapping value is changed mid-session, RF will need restart for this to take effect on Overlapper
        
        self.glyph_editor = self.getGlyphEditor()
        self.bg_container = self.glyph_editor.extensionContainer(
            identifier="Overlapper.foreground", 
            location="foreground", 
            clear=True
            )
            
        self.pv_container = self.glyph_editor.extensionContainer(
            identifier="Overlapper.preview", 
            location="preview", 
            clear=True
            )

        self.stroked_preview = self.bg_container.appendPathSublayer(
            strokeColor=(0,0,0,0),
            fillColor=(0,0,0,0),
            strokeWidth=1
            )
            
        self.preview_preview = self.pv_container.appendPathSublayer(
            strokeColor=None,
            fillColor=(0,0,0,1),
            strokeWidth=0
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
        self.info.setFigureStyle('tabular')
        self.set_colors()  # Set the correct colors for outline and text (light or dark mode), at least upon load. Will set again later on.


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
            sel_points += list(c.selectedPoints)
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
                            self.has_curve.append(in_result)
                        else:
                            in_result = lengthen_line(in_args[0], in_args[1], in_factor, "in")
                        
                        if len(out_args) == 4:
                            out_result = splitCubicAtT(out_args[0], out_args[1], out_args[2], out_args[3], -(out_factor-1))[1]
                            self.has_curve.append(out_result)
                        else:
                            out_result = lengthen_line(out_args[0], out_args[1], -(out_factor-1), "out")
                                
                        new_sel_hubs_in.update({key: in_result})
                        new_sel_hubs_out.update({key: out_result})

        # self.has_curve = [item for result in self.has_curve for item in result]
        if DEBUG == True: 
            print(self.has_curve)
            print("new_sel_hubs_in", new_sel_hubs_in, "new_sel_hubs_out", new_sel_hubs_out)
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
        self.preview_preview.setPath(glyph_path)
        
        postEvent(f"{EXTENSION_KEY}.overlapperDidDraw", overlapGlyph=outline, strokeColor=self.color)

        
    @timeit
    def get_overlapped_glyph(self):
        in_result, out_result = self.get_selection_data(self.tool_value)

        self.hold_g = RGlyph()
        pen = self.hold_g.getPointPen()
        for c in self.sel_contours:
            c.drawPoints(pen)
            
        for c in self.hold_g:
            hits = 0  # How many points you've gone through in the loop that are selected. this will bump up the index # assigned to newly created segments
            for i, seg in enumerate(c.segments):
                if c.open: i = i-1  # Not sure why, but shifting segment index is what makes non-closed contours behave as expected
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
                        c.segments[-1].smooth = False  # Make sure the current segment doesn't maintain smooth; it's now a corner.
                        c.insertSegment(0, type="line", points=[out_result[(x, y)][0]], smooth=False)
                        next_seg = c.segments[1]
                    else:
                        if DEBUG == True: print("2")
                        c.segments[i + hits].smooth = False  # Make sure the current segment doesn't maintain smooth; it's now a corner.
                        c.insertSegment(i + 1 + hits, type="line", points=[out_result[(x, y)][0]], smooth=False)
                        try:
                            if DEBUG == True: print("2a")
                            next_seg = c.segments[i + 2 + hits]
                            if c.open: next_seg = c.segments[i + 3 + hits]  # Again, not sure why this helps open contours.
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
        
        # Cross-Overlap feature
        # Make a list of all of the coordinates of the resulting overlapped points.
        sel_points_amount = len(in_result.keys())
        if self.shift_down:
            base_and_results = {}
            for key, val_in in in_result.items():
                base_and_results[key] = {'in': [], 'out': []}
                val_in = val_in[-1]
                if not val_in == key:
                    base_and_results[key]['in'] = val_in
                val_out = out_result[key][0]
                if not val_out == key:
                    base_and_results[key]['out'] = val_out
            if sel_points_amount % 2 == 0:
                for b_and_r_pair in break_dict_into_pairs(self.sel_contours, base_and_results):
                    self.convert_overlaps_to_cross_overlap(self.hold_g, b_and_r_pair)
            
        return self.hold_g
        
    
    @timeit
    def overlap_it(self):
        with self.g.undo("Overlap"):
            try:
                if self.snap != 0:
                    for c in self.hold_g.contours:
                        for pt in c.points:
                            pt.x, pt.y = my_round(pt.x, self.snap), my_round(pt.y,  self.snap)
                            
                with self.g.holdChanges():
                    compile_g = RGlyph()
                    excess_contours = len(self.hold_g) - len(self.sel_contours)
                    hold_g_index = 0
                    for contour in self.g.contours:
                        if not contour in self.sel_contours:
                            contours_to_add = [contour]
                        else:
                            if excess_contours >= 0:
                                contour = self.hold_g[hold_g_index]
                                contours_to_add = [contour] 
                                hold_g_index += 1
                                while excess_contours > 0:
                                    contour = self.hold_g[hold_g_index]
                                    contours_to_add.append(contour)  
                                    hold_g_index += 1
                                    excess_contours -= 1 
                            # Negative excess contours are caused by Overlapper making two into one.
                            else:
                                contours_to_add = []
                                excess_contours += 1
                        for c in contours_to_add:
                            compile_g.appendContour(c)
                
                    self.g.clearContours()
                    self.g.appendGlyph(compile_g)            
                            
                # Restore components
                for comp in self.stored_components:
                    self.g.appendComponent(component=comp)
                self.g.changed()
            except Exception as error:
                print(f"Overlapper Error. Reference: Overlap Commit\n{error}")
                pass
    
    def convert_overlaps_to_cross_overlap(self, glyph, dpd):
        # List of all 4 flattened resulting points
        all_points = []
        for key, val in dpd.items():
            all_points += (val.values())
            
        # Break the contours
        for c in glyph.contours:
            for pt in c.points:
                if (pt.x, pt.y) in all_points:
                    if DEBUG == True: print("Breaking contour at", pt)
                    c.breakContour(pt)
                    
        dict_keys = list(dpd.keys())   
        # print("dpd", dpd)
        pairs_to_close_or_remove = [[dpd[dict_keys[0]]['in'], dpd[dict_keys[1]]['out']], [dpd[dict_keys[1]]['in'], dpd[dict_keys[0]]['out']]]
        
        # Remove the short segments
        for c in glyph.contours:
            remove = True
            if len(c.points) == 2:
                for pt in c.points:                
                    if (pt.x, pt.y) in all_points:
                        continue
                    else:
                        remove = False
                # Remove the short segment contour if both points’ coordinates are in the list of coordinates.
                if remove == True:
                    if DEBUG == True: print("Removing contour", c)
                    # Add coordinates of points you're about to remove to a list of associated points.
                    glyph.removeContour(c)
        
        # Close the gaps the opposite way.
        for pair in pairs_to_close_or_remove:
            close_contour_at_coords(glyph, pair)
            close_contour_at_coords(glyph, pair)
            
                                
        if DEBUG == True: print("self.has_curve", self.has_curve)
        # Remove two points if there is no curve, and the four resulting points are along the same line
        for pair in pairs_to_close_or_remove:
            # Check to see if there's an off-curve in the pair first
            if not (pt.x, pt.y) in self.has_curve:
                # Check if the four-points segment runs along the same line
                if search_continuity(glyph, pair) == True:
                    # If so, remove the point
                    for c in glyph:
                        for pt in c.points:
                            if (pt.x, pt.y) in pair:
                                if DEBUG == True:
                                    print("\n", (pt.x, pt.y), "Removing point. Note to self: check to make sure it's not an off-curve, so there's no illegal point count!")
                                    print()
                                if pt.type != 'offcurve':
                                    c.removePoint(pt, preserveCurve=True)
        self.cross_success = True
                    
    @timeit
    def glyphEditorDidKeyDown(self, info):
        if DEBUG == True: print("glyphEditorDidKeyDown", info)
        
        self.has_curve = []
        
        # Check Shift modifier
        if info['deviceState']['shiftDown'] == 0:
            self.shift_down = False
            self.cross_success = False
        else:
            self.shift_down = True

        char = info['deviceState']['keyDownWithoutModifiers']
        self.hotkey = get_setting_from_defaults('hotkey')
        if char.lower() == self.hotkey and self.mod_active == False:
            self.g = CurrentGlyph()
            self.sel_contours = self.g.selectedContours

            if self.g.selectedPoints:
                self.ready_to_go = True
            else:
                self.ready_to_go = False
                return

            # Before we start, make sure the starting point is not an off-curve (that creates issues with segment insertion [illegal point counts])
            if self.allow_redraw == True:    
                changed = False
                for contour in self.sel_contours:
                    first_point = contour.points[0]
                    first_bPoint = contour.bPoints[0]
                    first_point_coords = (first_point.x, first_point.y)
                    if first_point_coords != first_bPoint.anchor:
                        print(
                            'Fixing off-curve start point in '
                            f'{self.g.name}, ({self.g.font.info.styleName})'
                        )
                        self.start_with_oncurve(contour)  # Simple alternative to redrawing glyph
                        changed = True
                if changed:
                    self.g.changed()

                # Only do this once at the beginning 
                self.allow_redraw  = False

            # Store the components, so we can delete them from the preview glyph and add them back upon commit.
            self.stored_components = self.g.components

            self.draw_overlap_preview()
            self.stroked_preview.setVisible(True)
            self.preview_preview.setVisible(True)

            self.key_down = True

    
    def glyphEditorDidKeyUp(self, info):
        if DEBUG == True: print("glyphEditorDidKeyUp", info)
        self.g = info['glyph']

        char = info['deviceState']['keyDownWithoutModifiers']
        if char.lower() == self.hotkey and self.mod_active == False:
            self.key_down = False  # Don't need this?

            if self.ready_to_go == True:
                self.overlap_it()

            self.initial_x = None
            self.tool_value = 0
            
            self.info.setVisible(False)
            self.stroked_preview.setVisible(False)
            self.preview_preview.setVisible(False)
            
            postEvent(f"{EXTENSION_KEY}.overlapperDidStopDrawing")

            self.ready_for_init = True
            self.allow_redraw  = True


    def glyphEditorDidChangeModifiers(self, info):
        ds = info['deviceState']
        mods = [ds['optionDown'], ds['controlDown'], ds['commandDown']]  # ds['shiftDown'], 
        self.mod_active = False        
        for value in mods:
            if value > 0:
                self.mod_active = True
                break
        
        # Check Shift modifier
        if info['deviceState']['shiftDown'] == 0:
            self.shift_down = False
        else:
            self.shift_down = True
            

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
            self.description = 'Overlapping'
            if self.tool_value < 0:
                self.description = 'Chamfering'
            if self.shift_down and self.cross_success:
                self.description = 'Cross-overlapping'
            self.info.setText(f" ← {self.description} → \n{self.tool_value}")
            self.info.setPosition((self.initial_x, y))


    # Change the UI colors if the app switches to dark mode.
    roboFontAppearanceChangedDelay = 1
    def roboFontAppearanceChanged(self, info):
        self.set_colors()


    def set_colors(self):
        if version >= "4.4":
            # Update, if you're in dark mode or not. This may be expensive—may want to perform in build().
            self.color = getDefault(appearanceColorKey('glyphViewStrokeColor'))
            self.preview_color = getDefault(appearanceColorKey('glyphViewPreviewFillColor'))
        else:
            self.color = getDefault('glyphViewStrokeColor')
            self.preview_color = getDefault('glyphViewPreviewFillColor')
        self.stroked_preview.setStrokeColor(self.color)
        self.preview_preview.setFillColor(self.preview_color)
        self.info.setFillColor(self.color)
            

# ======================================================================================
        

if __name__ == '__main__':
    # Register a subscriber event for Overlapper updating a drawing
    event_name = f"{EXTENSION_KEY}.overlapperDidDraw"
    if event_name not in getRegisteredSubscriberEvents():
        registerSubscriberEvent(
            subscriberEventName=event_name,
            methodName="overlapperDidDraw",
            lowLevelEventNames=[event_name],
            dispatcher="roboFont",
            documentation="Sent when Overlapper has updated the current overlapped glyph drawing.",
            delay=None
        )
    # Register a subscriber event for Overlapper stopping drawing
    event_name = f"{EXTENSION_KEY}.overlapperDidStopDrawing"
    if event_name not in getRegisteredSubscriberEvents():
        registerSubscriberEvent(
            subscriberEventName=event_name,
            methodName="overlapperDidStopDrawing",
            lowLevelEventNames=[event_name],
            dispatcher="roboFont",
            documentation="Sent when Overlapper has stopped drawing.",
            delay=None
        )
    registerGlyphEditorSubscriber(Overlapper)

