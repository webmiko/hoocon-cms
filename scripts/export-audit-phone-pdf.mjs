#!/usr/bin/env node
/**
 * Export audit HTML (Phone) → flat print-style PNG pages → PDF.
 * No gray canvas, no radius, no decorative gradients (same as Cmd+P).
 *
 * Usage:
 *   node scripts/export-audit-phone-pdf.mjs
 */
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const htmlPath = path.join(root, "docs/demo/yandex-competitors-audit.html");
const outDir = path.join(root, "docs/demo/export/phone");
const pdfPath = path.join(outDir, "hoocon-competitors-audit-phone.pdf");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    console.error("Need playwright. Run:\n  npm i -D playwright && npx playwright install chromium");
    process.exit(1);
  }
}

function loadPdfLib() {
  try {
    return require("pdf-lib");
  } catch {
    console.error("Need pdf-lib. Run:\n  npm i -D pdf-lib");
    process.exit(1);
  }
}

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (filePath.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

async function withStaticServer(dir, fn) {
  const server = createServer((req, res) => {
    const urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
    const safe = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, "");
    const filePath = path.join(dir, safe === "/" ? "index.html" : safe);
    if (!filePath.startsWith(dir) || !existsSync(filePath)) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": contentType(filePath) });
    res.end(readFileSync(filePath));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    return await fn(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  if (!existsSync(htmlPath)) {
    console.error("Missing", htmlPath);
    process.exit(1);
  }

  const { chromium } = loadPlaywright();
  const { PDFDocument } = loadPdfLib();
  await mkdir(outDir, { recursive: true });

  const demoDir = path.dirname(htmlPath);
  const htmlName = path.basename(htmlPath);

  await withStaticServer(demoDir, async (origin) => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({
      viewport: { width: 480, height: 1100 },
      deviceScaleFactor: 2,
    });

    await page.goto(`${origin}/${htmlName}?format=phone`, {
      waitUntil: "networkidle",
      timeout: 60000,
    });
    await page.waitForFunction(() => document.body.classList.contains("slides-phone"));
    await page.emulateMedia({ media: "print" });
    await page.evaluate(async () => {
      if (document.fonts?.ready) await document.fonts.ready;
      document.querySelectorAll("[data-w]").forEach((el) => {
        el.style.width = `${el.getAttribute("data-w")}%`;
      });
    });
    await sleep(300);

    const slides = page.locator(".slide");
    const count = await slides.count();
    if (!count) {
      console.error("No .slide elements found");
      process.exit(1);
    }

    const pngBuffers = [];
    for (let i = 0; i < count; i += 1) {
      const slide = slides.nth(i);
      await slide.scrollIntoViewIfNeeded();
      await sleep(60);
      const file = path.join(outDir, `slide-${String(i + 1).padStart(2, "0")}.png`);
      const buf = await slide.screenshot({ type: "png", omitBackground: false });
      await writeFile(file, buf);
      pngBuffers.push(buf);
      console.log("PNG", path.relative(root, file));
    }

    const pdf = await PDFDocument.create();
    for (const buf of pngBuffers) {
      const img = await pdf.embedPng(buf);
      const pagePdf = pdf.addPage([img.width, img.height]);
      pagePdf.drawImage(img, {
        x: 0,
        y: 0,
        width: img.width,
        height: img.height,
      });
    }
    await writeFile(pdfPath, await pdf.save());
    console.log("PDF", path.relative(root, pdfPath), `(${count} pages)`);

    await browser.close();
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
