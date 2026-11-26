# النماذج المصدّرة

| الملف | المصدر | ملاحظات |
|---|---|---|
| `mobile/ocr_detection.onnx` | PaddleOCR PP-OCRv5 Mobile Det | ONNX opset 17، يخرج خريطة احتمالات النص |
| `mobile/ocr_arabic.onnx` | PaddleOCR PP-OCRv5 Arabic Mobile Rec | ONNX opset 17، مع قاموس CTC `ocr_arabic_alphabet.json` |
| `mobile/ocr_latin.onnx` | PaddleOCR PP-OCRv5 Latin Mobile Rec | ONNX opset 17، مع قاموس CTC `ocr_latin_alphabet.json` |
| `mobile/dinov2_int8.onnx` | Meta DINOv2 ViT-S/14، backbone دون registers | ONNX opset 17 وتكميم ديناميكي لأوزان MatMul؛ خرج CLS من 384 عنصرًا بطول وحدة |
| `yolo11n_medguide.onnx` و `yolo11n_medguide_int8.tflite` | Ultralytics YOLO11n | يُنتجان عبر دفتر 03 بعد التدريب والتقييم بفصل المنتجات |

تتضمن تقارير `*_export_report.json` الحجم وSHA-256 ومقارنة CPU. توافق الرسوم العددية على المعالج يسبق تجربتها في Android. تعالج نسخة الهاتف مناطق Paddle ذات المحاذاة المستطيلة، بينما يستخرج PaddleOCR المرجعي مناطق DB متعددة الأضلاع. قياس أثر هذا الفرق على CER/WER يحتاج مجموعة نص مرجعي واختبار هاتف.

`reports/visual_exploratory/` يحتوي بصمات وFAISS استكشافي على قصاصات MedPackID. حقل `product_id` فارغ لأنها لا تحمل ربطًا مؤكّدًا بمنتجات قاعدة الأدوية. مجموعة الفهرس التجريبي لم تدخل التطبيق. التراخيص في `docs/LICENSES.md`.
