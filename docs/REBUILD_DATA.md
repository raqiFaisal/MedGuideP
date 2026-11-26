# إعادة بناء قاعدة MedGuide ومراجعتها

من جذر المشروع، باستخدام Python 3.11 أو أحدث، ثبّت الحزم:

```text
python -m pip install -e ./engine -e ./data_pipeline
```

ثم نفّذ الأمر التالي من PowerShell:

```powershell
$localBook = (Get-ChildItem data/raw/sfda -Filter '*المحلية*.xlsx').FullName
$foreignBook = (Get-ChildItem data/raw/sfda -Filter '*الغير*.xlsx').FullName
python data_pipeline/build_db.py --eg-drugs data/raw/eg-drugs/eg_drugs.csv --rxnorm-cache data/processed/rxnorm_cache.json --sfda-local "$localBook" --sfda-nonlocal "$foreignBook" --out data/processed/build
```

افتح `data/processed/build/review_sample.csv` في Excel. قارِن الاسم والتركيز والشركة مع المصدر في عمود `source`، وسجّل نتيجة كل مراجعة في `check_ok_(fill_in)` وأي اختلاف في `reviewer_note`. الرقم بعد `Data!` هو رقم الصف في ملف الهيئة السعودية. السجلات السعودية تمثّل لقطة ديسمبر 2023، والتوفر الحالي غير معلوم. حقول التركيز والشكل المشتقة من الاسم تحتاج مراجعة.

يحتوي `manifest.json` على بصمة SHA-256 للقاعدة المرفقة، ويعرض `quality_report.md` أعداد الإدخال والاستبعاد. هذه حزمة مصدر وبيانات لمرحلة المراجعة. تشغيل أندرويد يحتاج Android SDK وهاتفًا، والتعرف بالصور يحتاج بيانات صور ومراحل التدريب والتقييم.
