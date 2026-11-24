import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { SiteSearchForm } from "./SiteSearchForm";

vi.mock("../api/client", () => ({ api: { suggest: vi.fn() } }));

const suggest = vi.mocked(api.suggest);
let container: HTMLDivElement;
let root: Root;

function typeInto(input: HTMLInputElement, text: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  act(() => {
    setter?.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function flushSuggest() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500);
  });
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter>
        <SiteSearchForm />
      </MemoryRouter>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
  suggest.mockReset();
});

describe("SiteSearchForm did-you-mean", () => {
  it("offers the corrected text and refetches suggestions when chosen", async () => {
    suggest
      .mockResolvedValueOnce({
        results: [{ type: "sku", title: "HVA-5NM", url: "/catalog/x" }],
        corrected_query: "привод",
      })
      .mockResolvedValueOnce({ results: [], corrected_query: null });
    const input = container.querySelector("input") as HTMLInputElement;

    typeInto(input, "ghbdjl");
    await flushSuggest();

    const options = container.querySelectorAll('[role="option"]');
    expect(options[0].textContent).toContain("Возможно, вы имели в виду: привод");
    expect(options).toHaveLength(3);

    act(() => {
      options[0].dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });
    expect(input.value).toBe("привод");
    await flushSuggest();
    expect(suggest).toHaveBeenLastCalledWith("привод", expect.any(AbortSignal));
  });

  it("shows no hint when the server returns none", async () => {
    suggest.mockResolvedValue({
      results: [{ type: "sku", title: "HVA-5NM", url: "/catalog/x" }],
      corrected_query: null,
    });
    typeInto(container.querySelector("input") as HTMLInputElement, "hva");
    await flushSuggest();

    expect(container.textContent).not.toContain("Возможно, вы имели в виду");
    expect(container.querySelectorAll('[role="option"]')).toHaveLength(2);
  });
});
