import { CameraView, useCameraPermissions } from 'expo-camera';
import { File } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { Link, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Image, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLanguage } from '../preferences/store';
import { detectPreview, hasLiveGuide, type PreviewFrame } from '../recognition/liveGuide';
import { analyzeImage, type Analysis, type Stage } from '../recognition/analyze';

type Photo = { uri: string; width: number; height: number; owned: boolean };
function Action({ title, onPress, disabled = false }: { title: string; onPress: () => void; disabled?: boolean }) {
  return <Pressable style={[styles.action, disabled && styles.disabled]} accessibilityRole="button"
    onPress={onPress} disabled={disabled}><Text style={styles.actionText}>{title}</Text></Pressable>;
}

export default function Scan() {
  const { language, direction, t } = useLanguage();
  const stages: Record<Stage, string> = {
    image: t('تجهيز الصورة', 'Preparing image'), detection: t('تحديد موضع العلبة', 'Locating package'), barcode: t('قراءة الباركود', 'Reading barcode'),
    ocr: t('قراءة النص', 'Reading text'), visual: t('البحث عن صور مشابهة', 'Finding similar images'), matching: t('المطابقة مع قاعدة الأدوية', 'Matching the catalog'),
  };
  const statuses = {
    IDENTIFIED: t('✓ تم التعرف', '✓ Identified'),
    NEEDS_CONFIRMATION: t('؟ نحتاج تأكيدك', '? Please confirm'),
    NOT_IDENTIFIED: t('! لم نتعرف', '! No match'),
  };
  const reasons: Record<string, string> = {
    MULTIPLE_PACKS: t('تظهر أكثر من علبة. التقطي صورة لعلبة واحدة.', 'More than one package is visible. Photograph one package.'),
    SHARED_GTIN: t('الباركود مرتبط بأكثر من سجل. قارني الاسم والتركيز والشركة على العلبة.', 'The barcode matches multiple records. Compare the name, strength and manufacturer.'),
    CONFLICTING_GTIN: t('ظهرت رموز مختلفة في الصورة. صوّري علبة واحدة.', 'Different barcodes were found. Photograph one package.'),
    CONFLICTING_TEXT: t('النص المقروء يختلف عن بيانات السجل. تحققي من التركيز والاسم.', 'The text conflicts with the record. Check the strength and name.'),
    REVIEW_EVIDENCE: t('قارني الاسم والتركيز والشركة على العلبة بالسجل المقترح.', 'Compare the package name, strength and manufacturer with the suggested record.'),
    NO_CATALOG_MATCH: t('جرّبي لقطة أوضح للعلبة أو استخدمي البحث اليدوي.', 'Try a clearer photo or search manually.'),
    UNIQUE_REPEATED_GTIN: t('قُرئ الباركود مرتين ووجدنا سجلًا واحدًا مرتبطًا به.', 'Two barcode reads found one linked record.'),
  };
  const labels: Record<string, string> = {
    barcode: t('الباركود', 'Barcode'), text: t('النص على العلبة', 'Package text'), visual: t('تشابه الصورة', 'Visual similarity'),
    strength: t('التركيز', 'Strength'), manufacturer: t('الشركة', 'Manufacturer'), form: t('الشكل الصيدلاني', 'Dosage form'),
  };
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  const db = useSQLiteContext();
  const camera = useRef<CameraView>(null);
  const [permission, askPermission, checkPermission] = useCameraPermissions();
  const [foreground, setForeground] = useState(AppState.currentState !== 'background' && AppState.currentState !== 'inactive');
  const [focused, setFocused] = useState(false);
  const [cameraMode, setCameraMode] = useState(mode === 'camera');
  const [ready, setReady] = useState(false);
  const [torch, setTorch] = useState(false);
  const [photo, setPhoto] = useState<Photo>();
  const [previewWidth, setPreviewWidth] = useState(0);
  const [cameraWidth, setCameraWidth] = useState(0);
  const [liveBox, setLiveBox] = useState<Awaited<ReturnType<typeof detectPreview>>>();
  const frameBusy = useRef(false);
  const liveActive = useRef(false);
  const [working, setWorking] = useState(false);
  const [stage, setStage] = useState<Stage>();
  const [analysis, setAnalysis] = useState<Analysis>();
  const [error, setError] = useState('');
  const active = useRef(true);
  const latestPhoto = useRef<Photo | undefined>(undefined);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      const old = latestPhoto.current;
      if (old?.owned) {
        try { new File(old.uri).delete(); } catch { /* Cache may already be empty. */ }
      }
    };
  }, []);

  useFocusEffect(useCallback(() => {
    setFocused(true);
    return () => {
      setFocused(false);
      setReady(false);
    };
  }, []));

  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      setForeground(state === 'active');
      if (state === 'active') {
        void checkPermission().catch(() => setError(t('تعذّر التحقق من إذن الكاميرا.', 'Could not check camera permission.')));
      } else {
        setReady(false);
      }
    });
    return () => subscription.remove();
  }, [checkPermission, t]);

  const previewEnabled = Platform.OS === 'android' && hasLiveGuide && focused && foreground && cameraMode && !photo;
  useEffect(() => {
    liveActive.current = previewEnabled;
    return () => { liveActive.current = false; };
  }, [previewEnabled]);

  function receivePreview({ nativeEvent }: { nativeEvent: PreviewFrame }) {
    if (!liveActive.current || frameBusy.current) return;
    frameBusy.current = true;
    detectPreview(nativeEvent)
      .then(box => { if (liveActive.current) setLiveBox(box); })
      .catch(() => { if (liveActive.current) setLiveBox(undefined); })
      .finally(() => { frameBusy.current = false; });
  }

  function replacePhoto(next?: Photo) {
    const old = latestPhoto.current;
    if (old?.owned && old.uri !== next?.uri) {
      try { new File(old.uri).delete(); } catch { /* Cache may already be empty. */ }
    }
    latestPhoto.current = next;
    setPhoto(next);
    setAnalysis(undefined);
    setLiveBox(undefined);
    setStage(undefined);
    setReady(false);
  }

  async function choose() {
    if (working) return;
    setError('');
    setWorking(true);
    try {
      const pick = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsMultipleSelection: false });
      if (!pick.canceled && active.current && pick.assets[0]) {
        replacePhoto({ ...pick.assets[0], owned: false });
      }
    } catch {
      if (active.current) setError(t('تعذّر فتح المعرض. أعيدي المحاولة.', 'Could not open the gallery. Try again.'));
    } finally {
      if (active.current) setWorking(false);
    }
  }

  async function capture() {
    if (working || !ready || !camera.current) return;
    setWorking(true);
    setError('');
    try {
      const picture = await camera.current.takePictureAsync({ quality: .9, skipProcessing: false });
      if (picture && active.current) replacePhoto({ ...picture, owned: true });
      else if (picture) new File(picture.uri).delete();
    } catch {
      if (active.current) setError(t('تعذّر التقاط الصورة. أعيدي المحاولة.', 'Could not capture the photo. Try again.'));
    } finally {
      if (active.current) setWorking(false);
    }
  }

  async function rotatePhoto() {
    if (!photo || working) return;
    setError('');
    setWorking(true);
    try {
      const context = ImageManipulator.manipulate(photo.uri).rotate(90);
      const rotated = await (await context.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: .95 });
      if (active.current) replacePhoto({ ...rotated, owned: true });
      else new File(rotated.uri).delete();
    } catch {
      if (active.current) setError(t('تعذّر تدوير الصورة.', 'Could not rotate the photo.'));
    } finally {
      if (active.current) setWorking(false);
    }
  }

  async function analyze() {
    if (!photo || working) return;
    setWorking(true);
    setError('');
    setStage('image');
    setAnalysis(undefined);
    try {
      const result = await analyzeImage(db, photo.uri, photo.width, photo.height, s => {
        if (active.current) setStage(s);
      }, language);
      if (active.current) setAnalysis(result);
    } catch {
      if (active.current) setError(t('تعذّر تحليل الصورة محليًا. اختاري صورة أوضح أو استخدمي البحث اليدوي.', 'Could not analyze the photo. Try a clearer photo or search manually.'));
    } finally {
      if (active.current) {
        setWorking(false);
        setStage(undefined);
      }
    }
  }

  const guide = analysis?.packageGuide;
  const scale = photo ? Math.min(previewWidth / photo.width, 260 / photo.height) : 0;
  const imageWidth = photo ? photo.width * scale : 0;
  const imageHeight = photo ? photo.height * scale : 0;

  const liveScale = liveBox && cameraWidth ? Math.max(cameraWidth / liveBox.frameWidth, 330 / liveBox.frameHeight) : 0;
  const cameraGuideProps = previewEnabled ? { packageGuideEnabled: true, onPackagePreviewFrame: receivePreview } : {};

  return <ScrollView contentContainerStyle={styles.screen} accessibilityLanguage={language}>
    {!photo && cameraMode && <>
      <Text style={[styles.title, direction]}>{t('ضعي علبة واحدة داخل الإطار', 'Place one package in the frame')}</Text>
      {permission?.granted ? <>
        <View style={styles.camera} onLayout={event => setCameraWidth(event.nativeEvent.layout.width)}>
          {focused && foreground && <CameraView {...cameraGuideProps} ref={camera} style={StyleSheet.absoluteFill} facing="back" enableTorch={torch}
            onCameraReady={() => setReady(true)} onMountError={() => setError(t('تعذّر فتح الكاميرا.', 'Could not open the camera.'))}/>}
          {previewEnabled && ready && liveBox && liveScale > 0 ?
            <View pointerEvents="none" style={[styles.guide, {
              left: (cameraWidth - liveBox.frameWidth * liveScale) / 2 + liveBox.x * liveScale,
              top: (330 - liveBox.frameHeight * liveScale) / 2 + liveBox.y * liveScale,
              width: liveBox.width * liveScale, height: liveBox.height * liveScale,
            }]}/> : <View pointerEvents="none" style={styles.frame}/>}
        </View>
        <Action title={torch ? t('إطفاء الإضاءة', 'Torch off') : t('تشغيل الإضاءة', 'Torch on')} onPress={() => setTorch(!torch)} disabled={!ready || working}/>
        <Action title={t('التقاط الصورة', 'Take photo')} onPress={capture} disabled={!ready || working}/>
      </> : permission && <Action title={permission.canAskAgain ? t('السماح للكاميرا', 'Allow camera') : t('فتح أذونات التطبيق', 'Open app settings')}
        onPress={() => { if (permission.canAskAgain) void askPermission(); else void Linking.openSettings(); }}/>}
    </>}
    {!photo && <Action title={t('اختيار صورة من المعرض', 'Choose from gallery')} onPress={choose} disabled={working}/>}
    {!photo && !cameraMode && <Action title={t('فتح الكاميرا', 'Open camera')} onPress={() => setCameraMode(true)} disabled={working}/>}
    {photo && <>
      <Text accessibilityRole="header" style={[styles.title, direction]}>{analysis ? t('نتيجة التحليل', 'Analysis result') : t('معاينة الصورة', 'Photo preview')}</Text>
      <View style={styles.preview} onLayout={event => setPreviewWidth(event.nativeEvent.layout.width)}>
        <Image source={{ uri: photo.uri }} resizeMode="contain" style={StyleSheet.absoluteFill}
          accessibilityLabel={t('صورة العلبة المختارة', 'Selected package photo')} accessible />
        {guide && scale > 0 && <View pointerEvents="none" style={[styles.guide, {
          left: (previewWidth - imageWidth) / 2 + guide.x * imageWidth,
          top: (260 - imageHeight) / 2 + guide.y * imageHeight,
          width: guide.width * imageWidth, height: guide.height * imageHeight,
        }]}/>}
      </View>
      {!analysis && !stage && <>
        <Action title={t('حلّل الصورة', 'Analyze photo')} onPress={analyze} disabled={working}/>
        <Action title={t('تدوير الصورة 90 درجة', 'Rotate photo by 90°')} onPress={rotatePhoto} disabled={working}/>
      </>}
      {stage && <View style={styles.card}><ActivityIndicator color="#0F766E"/>
        <Text style={[styles.body, direction]} accessibilityLiveRegion="polite">{stages[stage]}</Text></View>}
      {analysis && <>
        <Text accessibilityRole="header" accessibilityLiveRegion="polite" style={[styles.title,
          analysis.status === 'IDENTIFIED' ? styles.success :
            analysis.status === 'NEEDS_CONFIRMATION' ? styles.warning : styles.missing]}>
          {statuses[analysis.status]}
        </Text>
        <Text style={[styles.body, direction]}>{reasons[analysis.reason]}</Text>
        {analysis.candidates.slice(0, analysis.status === 'IDENTIFIED' ? 1 : 3).map(({ product, evidence }) => (
          <View style={styles.card} key={product.id}>
            <Text style={[styles.title, direction]}>{product.brand_name_ar || product.brand_name_en}</Text>
            <Text style={[styles.body, direction]}>{[product.strength_normalized, product.manufacturer, product.country_code].filter(Boolean).join(' · ')}</Text>
            <Text style={[styles.body, direction]}>{evidence.map(e => labels[e]).join(' · ')}</Text>
            <Link style={[styles.link, direction]} href={{ pathname: '/product', params: { id: product.id } }}>
              {analysis.status === 'NEEDS_CONFIRMATION' ? t('هذه علبتي · فتح التفاصيل', 'This is my package · Open details') : t('تفاصيل السجل ومصادره', 'Record details and sources')}
            </Link>
          </View>
        ))}
        {analysis.lines.length > 0 && <>
          <Text style={[styles.body, direction]}>{t('راجع النص المقروء من الصورة', 'Review text read from the photo')}</Text>
          {analysis.lines.filter(line => line.confidence >= .65).slice(0, 10).map((line, index) =>
            <Text key={index} style={[styles.body, direction]} selectable
              accessibilityLanguage={line.language === 'arabic' ? 'ar' : 'en'}>{line.text}</Text>)}
        </>}
        {analysis.notes.map(note => <Text key={note} style={[styles.body, direction]}>{note}</Text>)}
      </>}
      <Action title={t('اختيار صورة أخرى', 'Choose another photo')} disabled={working} onPress={() => { setError(''); replacePhoto(); }}/>
    </>}
    {error ? <Text accessibilityRole="alert" style={[styles.missing, direction]}>{error}</Text> : null}
    <Link style={[styles.link, direction]} href="/">{t('البحث اليدوي', 'Search manually')}</Link>
  </ScrollView>;
}

const styles = StyleSheet.create({
  screen: { padding: 20, gap: 12, backgroundColor: '#F2FAF8', flexGrow: 1 },
  title: { fontSize: 22, fontWeight: '700', color: '#0B2545', textAlign: 'right' },
  body: { fontSize: 17, color: '#4A5D70', textAlign: 'right' },
  action: { borderRadius: 12, padding: 12, minHeight: 48, justifyContent: 'center', backgroundColor: '#0F766E' },
  actionText: { color: 'white', textAlign: 'center', fontSize: 17, fontWeight: '700' },
  disabled: { opacity: .5 },
  camera: { height: 330, backgroundColor: '#0A1B30', borderRadius: 16, overflow: 'hidden', justifyContent: 'center' },
  frame: { height: '65%', marginHorizontal: 25, borderColor: '#CCFBF1', borderWidth: 2, borderRadius: 12 },
  guide: { position: 'absolute', borderWidth: 2, borderColor: '#34D399', borderRadius: 4 },
  preview: { height: 260, overflow: 'hidden', backgroundColor: '#0A1B30', borderRadius: 16 },
  card: { backgroundColor: 'white', borderColor: '#D5E6E3', borderWidth: 1, borderRadius: 16, padding: 14, gap: 6 },
  link: { textAlign: 'right', fontSize: 17, minHeight: 48, paddingVertical: 12, color: '#0F766E', fontWeight: '700' },
  success: { color: '#15803D' },
  warning: { color: '#B45309' },
  missing: { color: '#B91C1C', fontSize: 18, textAlign: 'right' },
});
