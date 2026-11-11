import { describe, expect, it } from "vitest";
import { openingZoom } from "./zoom";

const small = { page: 1, left: 0.6, top: 0.7, width: 0.12, height: 0.03 };
const wide = { page: 1, left: 0.1, top: 0.4, width: 0.8, height: 0.05 };

describe("openingZoom", () => {
  it("caps a small value's zoom so the whole page width fits the area", () => {
    // zoomForBoxes would open this box at 300%; a 518px area fits a 760px page at 68%.
    expect(openingZoom([small], 518, 760)).toBe(0.68);
  });

  it("keeps the box's own scale when it's already smaller than fit-to-width", () => {
    expect(openingZoom([wide], 1400, 760)).toBe(1);
  });

  it("never opens smaller than 50%", () => {
    expect(openingZoom([small], 200, 760)).toBe(0.5);
  });

  it("keeps the box's scale when there's no width to measure", () => {
    expect(openingZoom([small], 0, 760)).toBe(3);
  });

  it("caps a page with no boxes at fit-to-width too", () => {
    expect(openingZoom([], 600, 760)).toBe(0.78);
    expect(openingZoom([], 1200, 760)).toBe(1);
  });
});
