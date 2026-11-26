import { Asset } from 'expo-asset';
import { File } from 'expo-file-system';
import { InferenceSession, Tensor } from 'onnxruntime-react-native';
import { assets } from './generatedAssets';
import type { Line } from './evidence';
import rules from '../../../shared/recognition.json';

export type Pixels = { data: Uint8Array; width: number; height: number };
type Box = { x: number; y: number; width: number; height: number };
const means = [.485, .456, .406];
const deviations = [.229, .224, .225];
const sessions = new Map<number, Promise<InferenceSession>>();

async function assetFile(id: number) {
  const asset = await Asset.fromModule(id).downloadAsync();
  if (!asset.localUri?.startsWith('file://')) throw new Error('Model asset is unavailable locally');
  return new File(asset.localUri);
}

async function infer(id: number, data: Float32Array, height: number, width: number) {
  let pending = sessions.get(id);
  if (!pending) {
    pending = assetFile(id).then(async file => InferenceSession.create(await file.bytes(), { intraOpNumThreads: 2 }));
    sessions.set(id, pending);
    pending.catch(() => sessions.delete(id));
  }
  const model = await pending;
  const output = (await model.run({ [model.inputNames[0]!]: new Tensor('float32', data, [1, 3, height, width]) }))[model.outputNames[0]!];
  if (!output || output.type !== 'float32' || !(output.data instanceof Float32Array)) throw new Error('Unexpected model output');
  return { data: output.data, dimensions: output.dims };
}

function tensor(
  pixels: Pixels, box: Box, width: number, height: number, transform: 'yolo' | 'dino' | 'ocr-det' | 'ocr-rec',
  canvasWidth = width, canvasHeight = height, left = 0, top = 0,
) {
  const plane = canvasWidth * canvasHeight;
  const output = new Float32Array(plane * 3);
  if (transform === 'yolo') output.fill(114 / 255);
  for (let y = 0; y < height; y++) {
    const sy = box.y + Math.max(0, Math.min(box.height - 1, (y + .5) * box.height / height - .5));
    const iy = Math.floor(sy);
    const ny = Math.min(iy + 1, box.y + box.height - 1);
    const fy = sy - iy;
    for (let x = 0; x < width; x++) {
      const sx = box.x + Math.max(0, Math.min(box.width - 1, (x + .5) * box.width / width - .5));
      const ix = Math.floor(sx);
      const nx = Math.min(ix + 1, box.x + box.width - 1);
      const fx = sx - ix;
      const j = (y + top) * canvasWidth + x + left;
      for (let c = 0; c < 3; c++) {
        const channel = transform.startsWith('ocr') ? 2 - c : c;
        const upper = (iy * pixels.width + ix) * 4 + channel;
        const lower = (ny * pixels.width + ix) * 4 + channel;
        const offset = (nx - ix) * 4;
        const value = ((pixels.data[upper]! * (1 - fx) + pixels.data[upper + offset]! * fx) * (1 - fy) +
          (pixels.data[lower]! * (1 - fx) + pixels.data[lower + offset]! * fx) * fy) / 255;
        output[c * plane + j] = transform === 'yolo' ? value : transform === 'ocr-rec' ?
          (value - .5) / .5 : (value - means[c]!) / deviations[c]!;
      }
    }
  }
  return output;
}

export function fullBox(pixels: Pixels): Box {
  return { x: 0, y: 0, width: pixels.width, height: pixels.height };
}

type Detection = { left: number; top: number; right: number; bottom: number; score: number };

function overlaps(a: Detection, b: Detection) {
  const area = (r: Detection) => (r.right - r.left) * (r.bottom - r.top);
  const intersection = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) *
    Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return intersection / (area(a) + area(b) - intersection) > .45;
}

export async function detect(pixels: Pixels): Promise<Box[] | null> {
  if (!assets.detector) return null;
  const size = 640;
  const scale = Math.min(size / pixels.width, size / pixels.height);
  const width = Math.round(pixels.width * scale);
  const height = Math.round(pixels.height * scale);
  const dx = Math.floor((size - width) / 2);
  const dy = Math.floor((size - height) / 2);
  const { data, dimensions } = await infer(assets.detector,
    tensor(pixels, fullBox(pixels), width, height, 'yolo', size, size, dx, dy), size, size);
  if (dimensions.length !== 3 || dimensions[0] !== 1 || dimensions[1] !== 5 || !dimensions[2]) {
    throw new Error('Expected a one-class YOLO11 ONNX model without embedded NMS');
  }
  const n = dimensions[2];
  const hits: Detection[] = [];
  for (let i = 0; i < n; i++) {
    const score = data[4 * n + i]!;
    if (!(score >= rules.min_detector_score)) continue;
    const x = data[i]!, y = data[n + i]!, w = data[2 * n + i]!, h = data[3 * n + i]!;
    if (w <= 0 || h <= 0) continue;
    hits.push({ left: x - w / 2, top: y - h / 2, right: x + w / 2, bottom: y + h / 2, score });
  }
  const kept: Detection[] = [];
  for (const hit of hits.sort((a, b) => b.score - a.score)) {
    if (!kept.some(box => overlaps(hit, box))) kept.push(hit);
    if (kept.length === 2) break;
  }
  return kept.map(hit => {
    const marginX = (hit.right - hit.left) * .04, marginY = (hit.bottom - hit.top) * .04;
    const x = Math.max(0, Math.floor((hit.left - dx - marginX) / scale));
    const y = Math.max(0, Math.floor((hit.top - dy - marginY) / scale));
    const endX = Math.min(pixels.width, Math.ceil((hit.right - dx + marginX) / scale));
    const endY = Math.min(pixels.height, Math.ceil((hit.bottom - dy + marginY) / scale));
    return { x, y, width: endX - x, height: endY - y };
  }).filter(box => box.width > 8 && box.height > 8);
}

function textBoxes(probability: Float32Array, width: number, height: number, crop: Box) {
  const visited = new Uint8Array(probability.length);
  const queue = new Int32Array(probability.length);
  const boxes: Box[] = [];
  for (let i = 0; i < probability.length; i++) {
    if (visited[i] || !(probability[i]! > .3)) continue;
    let start = 0, end = 1, sum = 0;
    queue[0] = i;
    visited[i] = 1;
    let minX = i % width, maxX = minX, minY = Math.floor(i / width), maxY = minY;
    while (start < end) {
      const index = queue[start++]!;
      const x = index % width, y = Math.floor(index / width);
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      sum += probability[index]!;
      const neighbors = [x > 0 ? index - 1 : -1, x + 1 < width ? index + 1 : -1, index - width, index + width];
      for (const next of neighbors) {
        if (next < 0 || next >= probability.length || visited[next] || !(probability[next]! > .3)) continue;
        visited[next] = 1;
        queue[end++] = next;
      }
    }
    if (end < 12 || maxY - minY < 2 || maxX - minX < 3 || sum / end < .6) continue;
    const padding = Math.max(2, Math.round((maxY - minY) * .45));
    const x = Math.max(0, Math.floor((minX - padding) * crop.width / width));
    const y = Math.max(0, Math.floor((minY - padding) * crop.height / height));
    const right = Math.min(crop.width, Math.ceil((maxX + padding + 1) * crop.width / width));
    const bottom = Math.min(crop.height, Math.ceil((maxY + padding + 1) * crop.height / height));
    boxes.push({ x: crop.x + x, y: crop.y + y, width: right - x, height: bottom - y });
  }
  return boxes.sort((a, b) => b.height - a.height).slice(0, 24).sort((a, b) => a.y - b.y || a.x - b.x);
}

export function decodeCtc(data: Float32Array, alphabet: string[]) {
  const classes = alphabet.length + 1;
  if (data.length % classes) throw new Error('OCR output and dictionary do not match');
  let previous = -1, count = 0, total = 0, text = '';
  for (let i = 0; i < data.length; i += classes) {
    let best = 0;
    for (let j = 1; j < classes; j++) if (data[i + j]! > data[i + best]!) best = j;
    if (best !== 0 && best !== previous) {
      text += alphabet[best - 1]!;
      total += data[i + best]!;
      count++;
    }
    previous = best;
  }
  return { text, confidence: count ? total / count : 0 };
}

export async function readText(pixels: Pixels, crop: Box): Promise<Line[] | null> {
  const models = assets.ocr;
  if (!models) return null;
  const scale = Math.min(1, 960 / Math.max(crop.width, crop.height));
  const width = Math.max(32, Math.round(crop.width * scale / 32) * 32);
  const height = Math.max(32, Math.round(crop.height * scale / 32) * 32);
  const result = await infer(models.detection, tensor(pixels, crop, width, height, 'ocr-det'), height, width);
  const [batch, channels, h, w] = result.dimensions;
  if (batch !== 1 || channels !== 1 || !h || !w) throw new Error('Unexpected OCR detection output');
  const lines: Line[] = [];
  for (const box of textBoxes(result.data, w, h, crop)) {
    const resized = Math.min(960, Math.ceil(box.width * 48 / box.height));
    const canvas = Math.max(320, resized);
    const input = tensor(pixels, box, resized, 48, 'ocr-rec', canvas);
    for (const language of ['arabic', 'latin'] as const) {
      const alphabet = language === 'arabic' ? models.arabicAlphabet : models.latinAlphabet;
      const output = await infer(models[language], input, 48, canvas);
      if (output.dimensions[0] !== 1 || output.dimensions[2] !== alphabet.length + 1) {
        throw new Error('Unexpected OCR recognition output');
      }
      const decoded = decodeCtc(output.data, alphabet);
      const { x, y, width, height } = box;
      if (decoded.text) lines.push({ language, ...decoded, polygon: [
        [x - crop.x, y - crop.y], [x + width - crop.x, y - crop.y],
        [x + width - crop.x, y + height - crop.y], [x - crop.x, y + height - crop.y],
      ] });
    }
  }
  return lines;
}

export async function visualMatches(pixels: Pixels, crop: Box): Promise<Map<number, number> | null> {
  const models = assets.visual;
  if (!models) return null;
  const { data: embedding } = await infer(models.model, tensor(pixels, crop, 224, 224, 'dino'), 224, 224);
  const bytes = await (await assetFile(models.vectors)).bytes();
  const matrix = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (embedding.length !== 384 || bytes.byteLength !== models.ids.length * 384 * 4) {
    throw new Error('Invalid visual index dimensions');
  }
  const scores = new Map<number, number>();
  models.ids.forEach((pid, row) => {
    let score = 0;
    for (let col = 0; col < 384; col++) score += embedding[col]! * matrix.getFloat32((row * 384 + col) * 4, true);
    scores.set(pid, Math.max(scores.get(pid) ?? -1, score));
  });
  return new Map([...scores.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]).slice(0, 20));
}
