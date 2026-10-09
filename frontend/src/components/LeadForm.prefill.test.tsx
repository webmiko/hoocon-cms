import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompareProvider } from "../compare/CompareContext";
import { LeadForm } from "./LeadForm";

let container: HTMLDivElement;
let root: Root;

function renderForm(skuName: string, skuSlug: string) {
  act(() =>
    root.render(
      <MemoryRouter>
        <CompareProvider>
          <LeadForm compact leadType="rfq" skuSlug={skuSlug} skuName={skuName} />
        </CompareProvider>
      </MemoryRouter>,
    ),
  );
}

function message(): HTMLTextAreaElement {
  return container.querySelector("textarea#message") as HTMLTextAreaElement;
}

function type(el: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ skus: [], csrfToken: "t" }), { status: 200 })),
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("LeadForm prefill on product change", () => {
  it("replaces the untouched message when the SKU changes (A→B)", () => {
    renderForm("DA24-A", "da24-a");
    expect(message().value).toBe("Прошу подготовить КП на DA24-A.");
    renderForm("SA10-B", "sa10-b");
    expect(message().value).toBe("Прошу подготовить КП на SA10-B.");
  });

  it("keeps a message the visitor already edited", () => {
    renderForm("DA24-A", "da24-a");
    type(message(), "Нужно 40 шт. к пятнице");
    renderForm("SA10-B", "sa10-b");
    expect(message().value).toBe("Нужно 40 шт. к пятнице");
  });
});
