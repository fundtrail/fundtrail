import { zoomForBoxes, type Box } from "./placement";

/** The smallest zoom the viewer opens at. */
export const MIN_ZOOM = 0.5;

/**
 * The zoom a PDF opens at: the box's own readable scale (zoomForBoxes), capped
 * so the page's full width fits the document area. The accountant can still
 * zoom in from there. With no width to measure, the box's scale stands.
 */
export function openingZoom(boxes: readonly Box[], areaWidth: number, pageWidth: number): number {
  const forBoxes = zoomForBoxes(boxes);
  if (!(areaWidth > 0) || !(pageWidth > 0)) return forBoxes;
  const fit = Math.max(MIN_ZOOM, Math.floor((areaWidth / pageWidth) * 100) / 100);
  return Math.min(forBoxes, fit);
}
