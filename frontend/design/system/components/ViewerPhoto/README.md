# ViewerPhoto

The viewer for a photo or scan, such as a receipt photo: the original image opened at the box around a fact's value. The agent returns a pixel box and a second look reads only the boxed area and has to see the same value. There is still no OCR (optical character recognition) and no text layer. A fact whose box couldn't be checked is unconfirmed and opens the whole photo with no box (ViewerUnconfirmed).

**Use it** when a fact, a receipt in a charge's trail, or a link's name points at a photo or scan. It fills the viewer's doc area (`ft-sheet__doc`) inside the shared frame.

**The consumer provides** the file (`type: 'photo'`, name, title, meta, links) and its facts, each with a `label`, a `value` and a `box`: `[x, y, w, h]` as fractions of the photo from its top left corner, as the contract's `image_box` gives it. There is no passage.

- **It opens zoomed to the box.** The box takes about half the visible width and is centered. The zoom snaps to a step: 50%, 75%, 100%, 150%, 200%, 250% or 300%. 100% shows the photo at its own pixel size.
- **"Show whole photo"** sits at the top left of the doc area and stays there while it scrolls (`ft-photo__toggle`, `data-act="whole"`). It fits the whole photo in the doc area. In that state it reads "Zoom to the box". Zooming in or out from the whole photo starts at the fitted size.
- The box is `ft-box` placed in the photo's own coordinates, so it stays on the same spot at every zoom. On a photo it has a fixed dark dashed outline with a thin light edge, because the photo keeps its own colors in both themes. Only the surface around it follows the theme, and the photo dims slightly in dark.
- The bar names the fact and says "Box checked by a second look". Side facts show no location, because the bar already says it.
- The pager reads "Previous area" and "Next area", not "passage". Choosing a fact in the side list or with the pager opens its box at its own zoom.
- The image is `aria-hidden`. Its frame is `role="img"` with a label that names the vendor and the fact the box marks.
- Under reduced motion, it jumps to the box instead of scrolling.

**Renderer:** `FTViewer.photo` in the viewer script built into this card and the Demo has `render`, `target`, `zooms` and `initialView`, plus the helpers `center`, `fitZoom`, `levelText`, `toggleLabel`, `step` and `canStep`. The demo photos F6 and F7 are drawn as inline SVG from their receipt data, and their boxes are computed from that drawing.

**Hash params, for screenshots:** `#fact=0` picks a fact by index. `&zoom=2` sets the zoom. `&whole=1` opens the whole photo. `&t=dark` sets the dark theme. The card shows the boat rental receipt (F6); the Demo opens the camera receipt (F7) from L-1019.

Don't: draw a box for an unconfirmed fact, guess a box, or crop the photo to the box. The accountant needs the whole image to judge it.
