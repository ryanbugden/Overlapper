# Overlapper
#### Ryan Bugden, 2022.03.18

A RoboFont extension that gives you the power to add overlaps (+) and chamfers (-) to your glyph in a dynamic and high-fidelity way. The result is more editability when drawing, and more flexibility when interpolating.

*This is inspired by the [Add Overlap](https://github.com/asaumierdemers/AddOverlap) extension by Alexandre Saumier Demers.*

## How to use Overlapper:
1. Select at least one on-curve point, preferably on a sharp corner.
2. Hold `v`, and move the mouse left and right to make your corner into a chamfer or overlap, respectively. The further you move your mouse, the bigger the chamfer or overlap. 
3. Let go of `v` to commit the resulting shape.

*Note: You can change hotkey in Extensions > Overlapper > Settings...*

---    

#### Known issues:
- Speed...
- Components are not seen in overlap preview, but they are added back upon key-up.
- If your glyph has contours with start points that are off-curves, this will make the nearest on-curve the start point in the process. This is the current workaround to preventing Overlapper from crashing RoboFont.
 
---

Special thanks to Frank Grießhammer, Jackson Cavanaugh, Andy Clymer, and all of the minds behind [fontTools](https://github.com/fonttools/fonttools) (the reason the curve extrapolation is so accurate).
