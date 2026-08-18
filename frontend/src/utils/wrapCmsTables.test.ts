import { describe, expect, it } from "vitest";

import { wrapCmsTables } from "./wrapCmsTables";

const MATRIX = [
  '<div class="table-scroll">',
  '<table class="series-table">',
  "<thead><tr><th>Ось</th><th>На что смотреть</th><th>Ошибка</th></tr></thead>",
  "<tbody><tr><td>Момент</td><td>Нм на валу</td><td>Путать площадь</td></tr></tbody>",
  "</table></div>",
].join("");

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

  it("stamps data-label from thead onto body cells", () => {
    const out = wrapCmsTables(MATRIX);
    expect(out).toContain('data-label="Ось"');
    expect(out).toContain('data-label="На что смотреть"');
    expect(out).toContain('data-label="Ошибка"');
    expect(wrapCmsTables(out)).toBe(out);
  });
});
