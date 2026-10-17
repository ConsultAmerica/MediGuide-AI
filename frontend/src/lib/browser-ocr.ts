/**
 * OCR on the user's device, for deployments where the API can't run
 * Tesseract (the Vercel API). tesseract.js is the same engine compiled to
 * WebAssembly: the photo is read here and only the words, their positions
 * and confidences are sent with the upload (as `client_ocr`). The server
 * uses them exactly as it would its own OCR, and every value still needs a
 * person to confirm it against the page.
 */

type ClientOcrWord = { x0: number; y0: number; x1: number; y1: number; text: string; confidence: number };
type ClientOcrPage = { page: number; width: number; height: number; words: ClientOcrWord[] };

// Mirrors src/ocr.py: small photos are enlarged before reading (small print
// stops reading reliably below ~1600 px on the long edge); very large ones
// are reduced so a phone photo doesn't stall the tab.
const MIN_LONG_EDGE = 1600;
const TARGET_LONG_EDGE = 2600;
const MAX_LONG_EDGE = 4000;

let serverOcrAvailable = true;

/** Set from /api/health; until it reports otherwise the server reads files. */
export function setServerOcrAvailable(value: boolean) {
  serverOcrAvailable = value;
}

export function needsBrowserOcr(file: File): boolean {
  return !serverOcrAvailable && file.type.startsWith("image/");
}

async function uprightCanvas(file: File): Promise<{ canvas: HTMLCanvasElement; width: number; height: number; scale: number }> {
  // createImageBitmap applies the photo's EXIF orientation, as the server's
  // exif_transpose does, so both see the same upright page.
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const width = bitmap.width;
  const height = bitmap.height;
  const longEdge = Math.max(width, height);
  const scale = longEdge < MIN_LONG_EDGE
    ? Math.min(3.5, TARGET_LONG_EDGE / longEdge)
    : longEdge > MAX_LONG_EDGE ? MAX_LONG_EDGE / longEdge : 1;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas is not available");
  context.imageSmoothingQuality = "high";
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return { canvas, width, height, scale };
}

/**
 * Reads a photo on this device. Returns the `client_ocr` form value, or
 * null when no browser reading is needed or it failed (the upload then
 * goes ahead and the server reports what it could and couldn't read).
 */
export async function browserOcrField(file: File, onProgress?: (fraction: number) => void): Promise<string | null> {
  if (!needsBrowserOcr(file)) return null;
  try {
    const { createWorker } = await import("tesseract.js");
    const { canvas, width, height, scale } = await uprightCanvas(file);
    const worker = await createWorker("eng", 1, {
      logger: (message) => {
        if (message.status === "recognizing text") onProgress?.(message.progress);
      },
    });
    try {
      const { data } = await worker.recognize(canvas, {}, { blocks: true });
      const words: ClientOcrWord[] = [];
      for (const block of data.blocks || []) {
        for (const paragraph of block.paragraphs) {
          for (const line of paragraph.lines) {
            for (const word of line.words) {
              const text = word.text.trim();
              if (!text) continue;
              words.push({
                x0: word.bbox.x0 / scale,
                y0: word.bbox.y0 / scale,
                x1: word.bbox.x1 / scale,
                y1: word.bbox.y1 / scale,
                text,
                confidence: word.confidence,
              });
            }
          }
        }
      }
      const page: ClientOcrPage = { page: 1, width, height, words };
      return JSON.stringify([page]);
    } finally {
      await worker.terminate();
    }
  } catch {
    return null;
  }
}
