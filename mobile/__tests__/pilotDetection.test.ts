import { analyzeImage } from '../src/recognition/analyze';
import { detect, fullBox, readText } from '../src/recognition/models';
import { recognize } from '../src/recognition/evidence';
import type { SQLiteDatabase } from 'expo-sqlite';

jest.mock('../src/recognition/perspective', () => ({ rectifyPackage: async () => null }));
jest.mock('expo-camera', () => ({ Camera: { scanFromURLAsync: async () => [] } }));
jest.mock('expo-file-system', () => ({ File: class { bytes = async () => new Uint8Array(); delete() {} } }));
jest.mock('expo-image-manipulator', () => ({
  ImageManipulator: { manipulate: () => {
    const context = {
      resize: () => context, rotate: () => context,
      renderAsync: async () => ({ saveAsync: async () => ({ uri: 'file:///cache/photo.jpg' }) }),
    };
    return context;
  } },
  SaveFormat: { JPEG: 'jpeg' },
}));
jest.mock('jpeg-js', () => ({ decode: () => ({ width: 640, height: 480, data: new Uint8Array() }) }));
jest.mock('../src/recognition/models', () => ({
  detect: jest.fn(),
  fullBox: jest.fn(() => ({ x: 0, y: 0, width: 640, height: 480 })),
  readText: jest.fn().mockResolvedValue(null),
  visualMatches: jest.fn().mockResolvedValue(null),
}));
jest.mock('../src/recognition/evidence', () => ({
  parseBarcode: jest.fn(),
  recognize: jest.fn().mockResolvedValue({
    status: 'NOT_IDENTIFIED', reason: 'NO_CATALOG_MATCH', candidates: [], barcodes: [], lines: [],
  }),
}));

const box = { x: 160, y: 120, width: 320, height: 240 };

test.each([[[box], true], [[box, box], false]] as const)(
  'pilot results guide preview only, including ambiguous detections %#',
  async (boxes, guideExpected) => {
    jest.mocked(detect).mockResolvedValueOnce(null).mockResolvedValueOnce([...boxes]);
    const db = {} as SQLiteDatabase;
    const analysis = await analyzeImage(db, 'file:///photo.jpg', 640, 480, () => {});

    expect(analysis.status).toBe('NOT_IDENTIFIED');
    expect(analysis.reason).toBe('NO_CATALOG_MATCH');
    expect(analysis.packageGuide).toEqual(guideExpected ? { x: .25, y: .25, width: .5, height: .5 } : undefined);
    expect(readText).toHaveBeenLastCalledWith(expect.any(Object), jest.mocked(fullBox).mock.results.at(-1)?.value);
    expect(recognize).toHaveBeenLastCalledWith(db, [], [], new Map());
  },
);
