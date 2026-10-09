import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PdnConsentCheckbox } from "./PdnConsentCheckbox";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const src = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (path: string) => readFileSync(join(src, path), "utf8");

let container: HTMLDivElement | null = null;

afterEach(() => {
  container?.remove();
  container = null;
});

describe("PdnConsentCheckbox", () => {
  it("reports the toggle and links to the policy", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    const onChange = vi.fn();
    act(() => {
      createRoot(container!).render(
        <MemoryRouter>
          <PdnConsentCheckbox checked={false} onChange={onChange} />
        </MemoryRouter>,
      );
    });
    const box = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    act(() => box.click());
    expect(onChange).toHaveBeenCalledWith(true);
    expect(container.querySelector("a")?.getAttribute("href")).toBe("/terms");
  });
});

describe("152-ФЗ consent wiring", () => {
  /*
   * Registration, code login, the post-lead cabinet offer and chat contacts
   * sent personal data without asking; the server now rejects them without
   * pdn_consent, so each form must render the box and send its value.
   */
  it.each([
    ["account/RegisterPage.tsx", /pdn_consent: pdnConsent/],
    ["account/LoginPage.tsx", /otpStart\(.*formStartTs\.current, pdnConsent\)/],
    ["account/CabinetOffer.tsx", /otpStart\(.*formStartTs\.current, pdnConsent\)/],
    ["components/LeadForm.tsx", /pdn_consent: pdnConsent/],
  ])("%s renders the checkbox, sends consent and blocks submit without it", (path, send) => {
    const tsx = read(path);
    expect(tsx).toContain("checked={pdnConsent}");
    expect(tsx).toMatch(send);
    expect(tsx).toMatch(/disabled=\{(busy|submitting) \|\| !pdnConsent\}/);
  });

  it("chat sends contacts only together with consent", () => {
    const tsx = read("components/SupportWidget.tsx");
    expect(tsx).toContain("<PdnConsentCheckbox");
    expect(tsx).toContain('const share = pdnConsent && Boolean(name.trim() || email.trim());');
    expect(tsx).toContain("pdn_consent: share || undefined");
    expect(tsx).toContain('const displayName = share ? name.trim() : "";');
  });
});
