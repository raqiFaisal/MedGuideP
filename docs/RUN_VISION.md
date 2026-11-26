# تشغيل مسار التعرف والتقييم

## 1. Google Colab وDrive

1. فكّي الحزمة في `MyDrive/MedGuide2` أو غيّري مسار `project` في دفتر 04.
2. افتحي `notebooks/03_MedGuide_YOLO11_Colab.ipynb` في Google Colab، واختاري GPU من إعدادات الجلسة المجانية. اسمحي بربط Drive. أولى الخلايا تجلب MedPackID مباشرة من [Mendeley](https://data.mendeley.com/datasets/d23kndp3sv/1) إلى `MyDrive/MedGuideData/MedPackID_v1`. يتحقق الكود من الحجم وSHA-256 المعلن ويستأنف التنزيل عند الإمكان. أرشيف الصور حجمه 3,256,769,597 بايت. لا يلزم تنزيله على اللابتوب.
3. للتجربة الاستكشافية بدّلي `ALLOW_PILOT = True` عند غياب الهويات. تحفظ الأوزان والمقاييس داخل `training/pilot_publisher_split_…`. لا يدخل هذا القياس أو النموذج في نسخة الهاتف.
4. للتقييم المعتمد استخدمي `notebooks/templates/detection_identities.csv` وانسخي الجدول المراجع باسم `identities.csv` بجانب الأرشيفات. للمشاهد التي تشترك في أكثر من عبوة، ضعي كل هوية مؤكدة مفصولة بعلامة `|`. يجمع الدفتر المنتجات المتداخلة في مجموعة واحدة. راجعي يدويًا الصور شبه المكررة والتسميات قبل التدريب. ستظهر نتائج التقييم المعتمد داخل `training/product_split_…`. مخرجات `mobile/` تُنتج بعد التحقق من انخفاض mAP50 ضمن نقطتين مقابل النموذج غير المصغّر.
5. افتحي `notebooks/04_MedGuide_OCR_Visual_Evaluation.ipynb`. ينشئ قصاصات مرجعية من المربعات الحقيقية ويشغّل OCR قبل توفر YOLO. غيّري مجلدات الإدخال في الخلايا حسب جداولك. مخرجاته في `MyDrive/MedGuideData/vision_artifacts`.

## 2. الجداول المطلوبة

| الملف | الحقول والمعنى |
|---|---|
| `identities.csv` | `file_name` هو اسم الصورة في MedPackID و`product_id` هو معرّف ثابت لنفس المنتج في جميع اللقطات و`identity_source` مرجع التحقق. معرّف تقسيم YOLO مستقل عن معرف SQLite. |
| `ocr_ground_truth.csv` | لكل قصاصة `file_name,language,reference_text,identity_source`. قيمة اللغة `arabic` أو `latin`. يكتب المراجع النص كاملاً بترتيب القراءة قبل مقارنة المخرجات، ويذكر مصدر التفريغ. للقصاصة ثنائية اللغة يمكن إضافة سطر لكل لغة. يحسب CER وWER عبر مجموع المسافات مقسومًا على إجمالي الحروف والكلمات المرجعية لكل لغة. |
| `visual_reference.csv` | `file_name,product_id,identity_source`. هنا `product_id` هو رقم `products.id` من **نسخة القاعدة نفسها**. تحققي من الاسم والتركيز والشكل والشركة والسوق للربط. يسجل الفهرس بصمة القاعدة ويرفض الربط عند تغييرها. |
| `visual_queries.csv` | الحقول نفسها مع صور من لقطات مستقلة عن المراجع. يجب أن يمثل معرض المراجع كل منتج مقاس. تُحسب الرتب على مستوى المنتج بعد جمع الصور المتعددة للمنتج. |
| `recognition_test.csv` | `file_name,product_id,identity_source,scenario,gtin,strength`. ضعي رقم سجل القاعدة للمنتج المعروف، واتركيه فارغًا عندما يؤكد المراجع أن المنتج غير موجود. استعملي `similar_pack` للعلب المتشابهة و`shared_gtin` للرمز المشترك و`unknown` للمجهول. اكتبي الباركود والتركيز إذا أمكن التحقق منهما. |

الاختبار يرفض التكرار المتطابق بالبايتات عند توفر فهرس المراجع وبيان YOLO. راجعي التقاطع بالمنتج وجلسة التصوير والتكرار البصري يدويًا. احتفظي بالصور المستقلة خارج تدريب YOLO وضبط قواعد الدمج وتقييمها الاستكشافي. نسبة الخطأ تظهر على جميع الصور وعلى المخرجات المؤكدة كل على حدة. الأعمدة الاختيارية غير المتوفرة تعطي مقاييس `null`. الزمن يسجل زمن الصورة ويعرض الوسيط والمئين 95 لتكوين المحرك الذي شُغّل.

## 3. تشغيل Python محليًا

من جذر الحزمة، مع Python 3.12:

```bash
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e "./engine[dev]" -r engine/requirements-vision.txt
python -m engine.eval.medpack_crops path/to/MedPackID_v1 path/to/crops --limit 30
python -m engine.eval.workflows ocr --images path/to/crops --output reports/paddleocr.json
python -m engine.eval.workflows build-visual --manifest visual_reference.csv --images reference_images --output visual_index
python -m engine.eval.workflows retrieval --index visual_index --manifest visual_queries.csv --images retrieval_test --output reports/retrieval.json
python -m engine.eval.workflows full --manifest recognition_test.csv --images recognition_test --ocr --index visual_index --detector path/to/best.pt --detector-manifest path/to/dataset_manifest.json --output reports/recognition_test.json
```

ينزّل دفتر 04 أوزان Paddle في Drive ويتحقق من البصمات. للتنفيذ من سطر الأوامر، شغّلي `python -m engine.eval.fetch_ocr_models path/to/paddle_models`. أسماء النماذج `PP-OCRv5_mobile_det` و`arabic_PP-OCRv5_mobile_rec` و`latin_PP-OCRv5_mobile_rec` من قائمة [PaddleOCR الرسمية](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html). مرري `--model-root` للمجلد الأب في أمر OCR أو التقييم. احتفظي بهذه الملفات داخل بيئة التشغيل.

## 4. بناء أندرويد محليًا

تتطلب الحزمة Expo SDK 58 وNode وJDK 17 كاملًا مع javac وAndroid SDK (compile SDK 37 وBuild Tools 37.0.0 وNDK 27.1.12297006). اضبطي `ANDROID_HOME` على مكان SDK. توضح الوثيقة الأصلية `BUILD_AND_RELEASE.md` خطوات الإعداد على ويندوز.

```bash
cd mobile
npm ci
npm run catalog:setup
npm run models:setup
npm run typecheck
npm run lint
npm test -- --runInBand
npx expo prebuild --platform android
cd android
./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a
# Windows: .\gradlew.bat :app:assembleRelease -PreactNativeArchitectures=arm64-v8a
```

تتحقق `models:setup` من SHA-256 للمخرجات ونسخة القاعدة. المصدر الافتراضي `models/mobile` وفيه OCR وDINOv2. لن ينشّط التطبيق المطابقة البصرية حتى تنقلي `visual.f32` و`visual_mapping.json` و`visual_manifest.json` من مجلد الفهرس الموثق إلى هذا المجلد. انقلي `yolo11n_medguide.onnx` و`yolo_export_report.json` من مخرجات YOLO المعتمدة لتفعيل الكشف. يستخدم هذا المسار ONNX Runtime على Android. نسخة TFLite المنتجة من الدفتر تُقاس للمقارنة قبل اختيار مشغّل بديل.

الصور تُعالَج داخل التطبيق. اختبري في وضع الطيران بعد بناء ملف APK وتثبيته لمسار الكاميرا والمعرض والصلاحيات. تحققي من القراءة العربية واللاتينية، ومن باركود EAN وGS1 DataMatrix، ثم قارني نتائج الملف نفسه في الهاتف والمحرك. قالب Expo الحالي يبني نسخة اختبار بمفتاح debug حتى تُضبط مفاتيح الإنتاج. اختبري الذراع المخصص للهاتف `arm64-v8a` أو اتركي خيار المعمارية الافتراضي إذا احتجتِ بناء عامًا.

لاختبار المسار عبر API أثناء التطوير فقط، شغّلي `python -m uvicorn server:app --app-dir engine --host 127.0.0.1` من جذر المشروع. يمكن ضبط `MEDGUIDE_DETECTOR` لمسار `best.pt`، و`MEDGUIDE_PADDLE_MODELS` و`MEDGUIDE_VISUAL_INDEX` لمجلدي OCR والفهرس. أمر اختبار صورة محلية: `curl -H "Content-Type: image/jpeg" --data-binary @box.jpg http://127.0.0.1:8000/api/v1/recognition/analyze`. التطبيق يعمل من وحداته المحلية ولا يستدعي هذه الواجهة.
