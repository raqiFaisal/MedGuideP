import { Camera, type BarcodeType } from 'expo-camera';
import { File } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import type { SQLiteDatabase } from 'expo-sqlite';
import { decode } from 'jpeg-js';
import { parseBarcode, recognize, type Barcode, type Result } from './evidence';
import { detect, fullBox, readText, visualMatches } from './models';

const types: BarcodeType[] = ['ean13', 'ean8', 'upc_a', 'datamatrix', 'code128'];
export type Stage = 'image' | 'detection' | 'barcode' | 'ocr' | 'visual' | 'matching';
type BoxGuide = { x: number; y: number; width: number; height: number };
export type Analysis = Result & { notes: string[]; timeMs: number; packageGuide?: BoxGuide };

export async function analyzeImage(db: SQLiteDatabase, uri: string, inputWidth: number, inputHeight: number,
  update: (stage: Stage) => void): Promise<Analysis> {
  if (!/^(file|content):\/\//.test(uri)) throw new Error('Photo must be local');
  if (Math.min(inputWidth, inputHeight) < 32) throw new Error('Image dimensions are too small');
  const start = performance.now();
  const resized = ImageManipulator.manipulate(uri);
  const cleanup: string[] = [];
  const notes: string[] = [];
  try {
    update('image');
    if (Math.max(inputWidth, inputHeight) > 1920) {
      resized.resize(inputWidth > inputHeight ? { width: 1920 } : { height: 1920 });
    }
    const prepared = await (await resized.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: .95 });
    cleanup.push(prepared.uri);
    const bytes = await new File(prepared.uri).bytes();
    const pixels = decode(bytes, { useTArray: true, maxMemoryUsageInMB: 96, maxResolutionInMP: 6 });
    update('detection');
    let boxes: Awaited<ReturnType<typeof detect>> = null;
    let packageGuide: BoxGuide | undefined;
    try {
      boxes = await detect(pixels);
      if (boxes === null) {
        const pilot = await detect(pixels, true);
        if (pilot !== null) {
          notes.push('الإطار التجريبي يحدّد مكانًا محتملًا للعلبة فقط.');
          if (pilot.length === 1 && pilot[0]) {
            const { x, y, width, height } = pilot[0];
            packageGuide = {
              x: x / pixels.width, y: y / pixels.height,
              width: width / pixels.width, height: height / pixels.height,
            };
          }
        } else {
          notes.push('كاشف العلبة غير مضمّن. استُخدمت الصورة كاملة.');
        }
      }
    } catch {
      notes.push('تعذّر تشغيل كاشف العلبة. استُخدمت الصورة كاملة.');
    }
    if (boxes && boxes.length > 1) {
      return { status: 'NOT_IDENTIFIED', reason: 'MULTIPLE_PACKS', candidates: [], notes,
        barcodes: [], lines: [], timeMs: performance.now() - start };
    }
    if (boxes && !boxes.length) notes.push('تعذّر تحديد موضع العلبة. استُخدمت الصورة كاملة.');
    const box = boxes?.[0] ?? fullBox(pixels);

    update('barcode');
    const reads: Barcode[] = [];
    try {
      const context = ImageManipulator.manipulate(prepared.uri);
      if (boxes?.length) context.crop({ originX: box.x, originY: box.y, width: box.width, height: box.height });
      const crop = await (await context.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: 1 });
      cleanup.push(crop.uri);
      const rotated = ImageManipulator.manipulate(crop.uri).rotate(90);
      const second = await (await rotated.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: 1 });
      cleanup.push(second.uri);
      for (const path of [crop.uri, second.uri]) {
        const codes = new Map<string, Barcode>();
        for (const code of await Camera.scanFromURLAsync(path, types)) {
          if (['datamatrix', 'code128'].includes(code.type) && !/^(?:\]|\x1d|\(|01)/.test(code.data)) continue;
          const parsed = parseBarcode(code.data);
          if (parsed) codes.set(parsed.gtin, parsed);
        }
        reads.push(...codes.values());
      }
    } catch {
      notes.push('تعذّرت قراءة الباركود من الصورة.');
    }
    update('ocr');
    let lines;
    let ocrFailed = false;
    try {
      lines = await readText(pixels, box);
      if (!lines) notes.push('نماذج قراءة النص غير مضمّنة.');
    } catch {
      ocrFailed = true;
      notes.push('تعذّر تشغيل قراءة النص محليًا.');
    }
    update('visual');
    let visual;
    try {
      visual = await visualMatches(pixels, box);
      if (!visual) notes.push('فهرس الصور المرتبط بقاعدة الأدوية غير مضمّن.');
    } catch {
      notes.push('تعذّر تشغيل المطابقة البصرية محليًا.');
    }
    update('matching');
    const result = await recognize(db, reads, lines ?? [], visual ?? new Map());
    if (ocrFailed && result.status === 'IDENTIFIED') {
      result.status = 'NEEDS_CONFIRMATION';
      result.reason = 'REVIEW_EVIDENCE';
    }
    return { ...result, notes, packageGuide, timeMs: performance.now() - start };
  } finally {
    for (const path of cleanup) {
      try { new File(path).delete(); } catch { /* The OS may already have cleared the cache file. */ }
    }
  }
}
