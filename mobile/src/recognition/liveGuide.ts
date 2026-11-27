import { assets } from './generatedAssets';
import { detect } from './models';

export type PreviewFrame = { luma: string; width: number; height: number };

export const hasLiveGuide = Boolean(assets.pilotDetector);

export async function detectPreview({ luma, width, height }: PreviewFrame) {
  if (!Number.isInteger(width) || !Number.isInteger(height) ||
      width < 2 || height < 2 || width > 256 || height > 256) return undefined;
  const count = width * height;
  const expectedPadding = (3 - count % 3) % 3;
  if (luma.length !== Math.ceil(count / 3) * 4 ||
      luma.length - luma.replace(/=+$/, '').length !== expectedPadding) return undefined;
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const data = new Uint8Array(count * 4);
  let written = 0;
  let accumulator = 0;
  let bits = 0;
  for (let i = 0; i < luma.length - expectedPadding; i++) {
    const index = alphabet.indexOf(luma.charAt(i));
    if (index < 0) return undefined;
    accumulator = (accumulator << 6) | index;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      const value = (accumulator >> bits) & 255;
      data.fill(value, written * 4, written * 4 + 3);
      data[written * 4 + 3] = 255;
      written++;
    }
  }
  if (written !== count) return undefined;
  const boxes = await detect({ data, width, height }, true);
  return boxes?.length === 1 && boxes[0] ? { ...boxes[0], frameWidth: width, frameHeight: height } : undefined;
}
