# CLAUDE.md

## README Screenshots

Screenshots are embedded in README.md using HTML `<img>` tags with percentage widths, scaled proportionally to each image's native pixel width so they appear at a consistent terminal font size.

To add a new screenshot:
1. Check the native pixel width of all screenshots: `python3 -c "import struct; [print(f, struct.unpack('>I', open(f,'rb').read()[16:20])[0]) for f in ['screenshot-a.png', ...]]"`
2. Find the widest image — that one gets `width="100%"`.
3. Scale the others: `round(native_width / max_width * 100)`%.
4. Use `<img src="screenshot-name.png" width="XX%">` in README.md.
