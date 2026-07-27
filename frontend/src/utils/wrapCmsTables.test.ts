import { describe, expect, it } from "vitest";

import { wrapCmsTables } from "./wrapCmsTables";

describe("wrapCmsTables", () => {
  it("wraps a bare table in .table-scroll", () => {
    const html = "<p>x</p><table><tr><td>a</td></tr></table><p>y</p>";
    const out = wrapCmsTables(html);
    expect(out).toContain('<div class="table-scroll"><table>');
    expect(out).toContain("</table></div>");
  });

  it("does not double-wrap existing table-scroll", () => {
    const html =
      '<div class="table-scroll"><table><tr><td>a</td></tr></table></div>';
    expect(wrapCmsTables(html)).toBe(html);
    expect(wrapCmsTables(wrapCmsTables(html))).toBe(html);
  });
});
