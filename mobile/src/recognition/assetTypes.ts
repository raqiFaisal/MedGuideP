export type ModelAssets = {
  detector?: number;
  pilotDetector?: number;
  ocr?: { detection: number; arabic: number; latin: number; arabicAlphabet: string[]; latinAlphabet: string[] };
  visual?: { model: number; vectors: number; ids: number[] };
};
