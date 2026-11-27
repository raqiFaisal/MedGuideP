import { Camera, type BarcodeType } from 'expo-camera';
import { File } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import type { SQLiteDatabase } from 'expo-sqlite';
import { decode } from 'jpeg-js';
import { parseBarcode, recognize, type Barcode, type Result } from './evidence';
import { detect, fullBox, readText, visualMatches } from './models';
import { rectifyPackage } from './perspective';

const types: BarcodeType[] = ['ean13', 'ean8', 'upc_a', 'datamatrix', 'code128'];
export type Stage = 'image' | 'detection' | 'barcode' | 'ocr' | 'visual' | 'matching';
type BoxGuide = { x: number; y: number; width: number; height: number };
export type Analysis = Result & { notes: string[]; timeMs: number; packageGuide?: BoxGuide };

export async function analyzeImage(db: SQLiteDatabase, uri: string, inputWidth: number, inputHeight: number,
  update: (stage: Stage) => void, language: 'ar' | 'en' = 'ar'): Promise<Analysis> {
  if (!/^(file|content):\/\//.test(uri)) throw new Error('Photo must be local');
  if (![inputWidth, inputHeight].every(Number.isFinite) || Math.min(inputWidth, inputHeight) < 32) throw new Error('Image dimensions are too small');
  const start = performance.now();
  const resized = ImageManipulator.manipulate(uri, { maxWidth: 1920, maxHeight: 1920 });
  const cleanup: string[] = [];
  const notes: string[] = [];
  try {
    update('image');
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
          notes.push(language === 'ar' ? 'الإطار التجريبي يحدّد مكانًا محتملًا للعلبة فقط.' : 'The pilot frame marks a possible package location.');
          if (pilot.length === 1 && pilot[0]) {
            const { x, y, width, height } = pilot[0];
            packageGuide = {
              x: x / pixels.width, y: y / pixels.height,
              width: width / pixels.width, height: height / pixels.height,
            };
          }
        } else {
          notes.push(language === 'ar' ? 'كاشف العلبة غير مضمّن. استُخدمت الصورة كاملة.' : 'Package detector unavailable. The full image was used.');
        }
      }
    } catch {
      notes.push(language === 'ar' ? 'تعذّر تشغيل كاشف العلبة. استُخدمت الصورة كاملة.' : 'Package detection failed. The full image was used.');
    }
    if (boxes && boxes.length > 1) {
      return { status: 'NOT_IDENTIFIED', reason: 'MULTIPLE_PACKS', candidates: [], notes,
        barcodes: [], lines: [], timeMs: performance.now() - start };
    }
    if (boxes && !boxes.length) notes.push(language === 'ar' ? 'تعذّر تحديد موضع العلبة. استُخدمت الصورة كاملة.' : 'No package box was found. The full image was used.');
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
      notes.push(language === 'ar' ? 'تعذّرت قراءة الباركود من الصورة.' : 'Could not read a barcode from the photo.');
    }
    update('ocr');
    let lines: Awaited<ReturnType<typeof readText>> = null;
    try {
      const corrected = await rectifyPackage(prepared.uri);
      if (corrected) {
        cleanup.push(corrected);
        const correctedPixels = decode(await new File(corrected).bytes(), { useTArray: true, maxMemoryUsageInMB: 96, maxResolutionInMP: 6 });
        lines = await readText(correctedPixels, fullBox(correctedPixels));
      }
    } catch {
      // Continue with the unmodified image if correction is unavailable.
    }
    let ocrFailed = false;
    try {
      if (!lines?.some(line => line.confidence >= .65)) lines = await readText(pixels, box);
      if (!lines) notes.push(language === 'ar' ? 'نماذج قراءة النص غير مضمّنة.' : 'This build has no text recognition model.');
    } catch {
      ocrFailed = true;
      notes.push(language === 'ar' ? 'تعذّر تشغيل قراءة النص محليًا.' : 'Text recognition failed on the device.');
    }
    update('visual');
    let visual;
    try {
      visual = await visualMatches(pixels, box);
      if (!visual) notes.push(language === 'ar' ? 'فهرس الصور المرتبط بقاعدة الأدوية غير مضمّن.' : 'This build has no catalog-linked image index.');
    } catch {
      notes.push(language === 'ar' ? 'تعذّر تشغيل المطابقة البصرية محليًا.' : 'Visual matching failed on the device.');
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
