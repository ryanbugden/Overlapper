<img src="source/resources/mechanic_icon.png"  width="100">

# Overlapper
A RoboFont extension that gives you the power to add overlaps (+) and chamfers (-) to your glyph in a dynamic and high-fidelity way. The result is more editability when drawing, and more flexibility when interpolating.

**Ryan Bugden**
*Initially conceived of on 2022.03.18*

## How to use Overlapper:

**Download the extension** from this repository’s [Releases](https://github.com/ryanbugden/Overlapper/releases) page.

### Overlapping and chamferring:

1. Select at least one on-curve point, preferably on a sharp corner.
2. Hold `v`, and move the mouse right or left to make your corner into an overlap or a chamfer, respectively. The further you move your mouse, the bigger the overlap or chamfer. 
3. Let go of `v` to commit the resulting shape.

<img src="source/resources/overlapper_overlap.gif"  width="360">
<img src="source/resources/overlapper_chamfer.gif"  width="360">


### Cross-overlapping:
1. Select 2 or 4 on-curve points (Doesn't currently work on more).
2. Hold `Shift + v`, and move the mouse right or left to make your corner into an overlap or a chamfer, respectively. The further you move your mouse, the bigger the cross-overlap. 
3. Let go of `v` (before letting go of `Shift`) to commit the resulting shape.

<img src="source/resources/overlapper_cross_1.gif"  width="360">
<img src="source/resources/overlapper_cross_2.gif"  width="360">
<img src="source/resources/overlapper_cross_3.gif"  width="360">

*Note: You can change hotkey in Extensions > Overlapper > Settings...*

---

#### Notes:
- If your glyph has contours with start points that are off-curves, this will make the nearest on-curve the start point in the process. This is the current workaround to preventing Overlapper from crashing RoboFont.
- In cross-overlap mode, when selecting more than 2 points, Overlapper does its best to pair them up. If it's not doing what you want it to do, try to do it on one pair at a time.

---
Overlapper is inspired by the [Add Overlap](https://github.com/asaumierdemers/AddOverlap) extension by Alexandre Saumier Demers. The cross-overlap feature is inspired by Thom Janssen’s [Cross Overlap](https://github.com/thomgb/RF-Extensions).

Special thanks to Frank Grießhammer, Jackson Cavanaugh, Andy Clymer, and all of the minds behind [fontTools](https://github.com/fonttools/fonttools) (the reason the curve extrapolation is so accurate).
