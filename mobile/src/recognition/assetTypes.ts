type TextRecognizer = { model: number; alphabet: string[] };

export type ModelAssets = {
  detector?: number;
  pilotDetector?: number;
  ocr?: { detection: number; arabic: number; latin: number; arabicAlphabet: string[]; latinAlphabet: string[] };
  packageOcr?: { detector: number; arabic: TextRecognizer; latin: TextRecognizer };
  visual?: { model: number; vectors: number; ids: number[] };
};
