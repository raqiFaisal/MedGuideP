import { detectPreview } from '../src/recognition/liveGuide';
import { detect } from '../src/recognition/models';
import { logicalArabic } from '../src/recognition/readingOrder';

jest.mock('../src/recognition/generatedAssets', () => ({ assets: { pilotDetector: 1 } }));
jest.mock('../src/recognition/models', () => ({ detect: jest.fn() }));

test('a live framing sample decodes luminance into RGBA and returns one framed box', async () => {
  const box = { x: 0, y: 0, width: 2, height: 2 };
  jest.mocked(detect).mockResolvedValueOnce([box]);
  await expect(detectPreview({ width: 2, height: 2, luma: 'AEB//w==' }))
    .resolves.toEqual({ ...box, frameWidth: 2, frameHeight: 2 });
  expect(detect).toHaveBeenCalledWith({
    width: 2, height: 2,
    data: new Uint8Array([0, 0, 0, 255, 64, 64, 64, 255, 127, 127, 127, 255, 255, 255, 255, 255]),
  }, true);
});

test('invalid frame bytes and ambiguous detections do not display a live box', async () => {
  const box = { x: 0, y: 0, width: 2, height: 2 };
  jest.mocked(detect).mockClear().mockResolvedValueOnce([box, box]);
  await expect(detectPreview({ width: 2, height: 2, luma: '%%%%%%==' })).resolves.toBeUndefined();
  expect(detect).not.toHaveBeenCalled();
  await expect(detectPreview({ width: 2, height: 2, luma: 'AEB//w==' })).resolves.toBeUndefined();
});

test('reading order preserves the number order in Arabic text', () => {
  expect(logicalArabic('غلم ٥٠٠ لودانب')).toBe('بنادول ٥٠٠ ملغ');
  expect(logicalArabic('غلم 12.5 لودانب')).toBe('بنادول 12.5 ملغ');
});
