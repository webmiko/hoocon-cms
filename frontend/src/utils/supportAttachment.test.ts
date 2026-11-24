import { describe, expect, it } from "vitest";

import {
  ATTACHMENT_MAX_BYTES,
  MEDIA_ATTACHMENT_MAX_BYTES,
  attachmentLimitBytes,
  attachmentTooBigMessage,
} from "./supportAttachment";

describe("support attachment limits", () => {
  it("lets video and audio use the larger limit", () => {
    expect(attachmentLimitBytes({ type: "video/mp4" })).toBe(MEDIA_ATTACHMENT_MAX_BYTES);
    expect(attachmentLimitBytes({ type: "audio/ogg" })).toBe(MEDIA_ATTACHMENT_MAX_BYTES);
  });

  it("keeps documents and images at 10 MB", () => {
    expect(attachmentLimitBytes({ type: "application/pdf" })).toBe(ATTACHMENT_MAX_BYTES);
    expect(attachmentLimitBytes({ type: "image/png" })).toBe(ATTACHMENT_MAX_BYTES);
  });

  it("stays below the 20 MB nginx body cap", () => {
    expect(MEDIA_ATTACHMENT_MAX_BYTES).toBeLessThan(20 * 1024 * 1024);
  });

  it("points oversized video at the e-mail / cloud fallback", () => {
    expect(attachmentTooBigMessage({ type: "video/mp4" })).toContain("sales@hoocon.ru");
    expect(attachmentTooBigMessage({ type: "application/pdf" })).toBe("Файл больше 10 МБ.");
  });
});
