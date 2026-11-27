const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const input = path.resolve(process.argv[2] ?? '../models/mobile');
const assets = path.resolve(__dirname, '../assets/models');
const target = path.resolve(__dirname, '../src/recognition/generatedAssets.js');
const catalog = path.resolve(__dirname, '../../data/processed/build/manifest.json');
const sha = file => crypto.createHash('sha256').update(file).digest('hex');
const json = name => JSON.parse(fs.readFileSync(path.join(input, name), 'utf8'));
const exists = name => fs.existsSync(path.join(input, name));
const props = [];

function copy(name, checksum) {
  const source = path.join(input, name);
  const destination = path.join(assets, name);
  const partsDirectory = source + '.parts';
  const temporary = destination + '.' + process.pid + '.tmp';
  const files = fs.existsSync(partsDirectory)
    ? fs.readdirSync(partsDirectory).filter(part => /^part-[0-9]{2}$/.test(part)).sort()
    : null;
  if (files && (!files.length || files.some((part, i) => part !== 'part-' + String(i).padStart(2, '0')))) {
    throw new Error(`Missing or unordered model parts for ${name}`);
  }
  const paths = files ? files.map(part => path.join(partsDirectory, part)) : [source];
  const hash = crypto.createHash('sha256');
  try {
    const output = fs.openSync(temporary, 'wx');
    try {
      for (const file of paths) {
        const bytes = fs.readFileSync(file);
        hash.update(bytes);
        fs.writeFileSync(output, bytes);
      }
    } finally {
      fs.closeSync(output);
    }
    if (!checksum || hash.digest('hex') !== checksum) throw new Error(`Integrity check failed for ${name}`);
    fs.renameSync(temporary, destination);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
  return `require('../../assets/models/${name}')`;
}

fs.mkdirSync(assets, { recursive: true });
if (exists('yolo_export_report.json')) {
  const report = json('yolo_export_report.json');
  if (report.mode !== 'product_split' || !Number.isFinite(report.onnx_map50)) {
    throw new Error('Detector requires an evaluated product-disjoint export');
  }
  props.push(`detector: ${copy('yolo11n_medguide.onnx', report.onnx_sha256)}`);
}
if (process.env.MEDGUIDE_ENABLE_PILOT_YOLO === '1' && !props.length) {
  const report = json('yolo_pilot_export_report.json');
  if (report.mode !== 'pilot_publisher_split' || report.input_size !== 640 ||
      report.output_shape?.join(',') !== '1,5,8400' || report.runtime_parity !== true) {
    throw new Error('Pilot detector requires a verified 640 px ONNX export');
  }
  props.push(`pilotDetector: ${copy('yolo11n_medguide_pilot.onnx', report.onnx_sha256)}`);
}
const ocrWeights = ['detection', 'arabic', 'latin'].map(role => `ocr_${role}.onnx`);
if (ocrWeights.some(exists)) {
  const report = json('ocr_export_report.json');
  const ocr = ['detection', 'arabic', 'latin'].map(role => {
    const key = `ocr_${role}`;
    return `${role}: ${copy(`${key}.onnx`, report[key].onnx_sha256)}`;
  });
  for (const lang of ['arabic', 'latin']) {
    const name = `ocr_${lang}_alphabet.json`;
    if (!Array.isArray(json(name))) throw new Error(`Invalid alphabet: ${name}`);
    ocr.push(`${lang}Alphabet: ${copy(name, report[`ocr_${lang}`].alphabet_sha256)}`);
  }
  props.push(`ocr: { ${ocr.join(', ')} }`);
}
if (exists('package_ocr_export_report.json')) {
  const report = json('package_ocr_export_report.json');
  if (report.architecture !== 'rapidocr-db-easyocr-bilingual' || report.shape?.join(',') !== '1,1,64,width') {
    throw new Error('Unsupported package OCR export');
  }
  const detector = copy('package_ocr_detector.onnx', report.detector_sha256);
  const recognizers = ['arabic', 'latin'].map(language => {
    const row = report.recognizers[language];
    const model = copy(`package_ocr_${language}.onnx`, row.onnx_sha256);
    const alphabet = copy(`package_ocr_${language}_alphabet.json`, row.alphabet_sha256);
    return `${language}: { model: ${model}, alphabet: ${alphabet} }`;
  });
  props.push(`packageOcr: { detector: ${detector}, ${recognizers.join(', ')} }`);
}
if (exists('visual_manifest.json')) {
  const manifest = json('visual_manifest.json');
  const database = JSON.parse(fs.readFileSync(catalog, 'utf8'));
  if (manifest.catalog_sha256 !== database.sha256 || manifest.model !== 'dinov2_vits14_rgb224_cls_l2' ||
      manifest.dim !== 384 || !Number.isSafeInteger(manifest.rows) || manifest.rows <= 0) {
    throw new Error('Reference index is incompatible with the bundled catalog');
  }
  const mappingBytes = fs.readFileSync(path.join(input, 'visual_mapping.json'));
  const mapping = JSON.parse(mappingBytes);
  const vectors = fs.statSync(path.join(input, 'visual.f32'));
  if (sha(mappingBytes) !== manifest.files['visual_mapping.json'] || mapping.length !== manifest.rows ||
      vectors.size !== manifest.rows * manifest.dim * 4 ||
      mapping.some(row => !Number.isSafeInteger(row.product_id) || row.product_id <= 0 || !row.identity_source)) {
    throw new Error('Invalid visual vectors or product mapping');
  }
  const modelHash = json('dino_export_report.json').onnx_sha256;
  if (!modelHash || manifest.embedding_onnx_sha256 !== modelHash) {
    throw new Error('Build the visual index with the same DINOv2 ONNX weights as Android');
  }
  const model = copy('dinov2_int8.onnx', modelHash);
  const vectorAsset = copy('visual.f32', manifest.files['visual.f32']);
  props.push(`visual: { model: ${model}, vectors: ${vectorAsset}, ids: ${JSON.stringify(mapping.map(row => row.product_id))} }`);
}

const tmp = target + '.tmp';
fs.writeFileSync(tmp, `// Generated by npm run models:setup.\nexport const assets = {\n  ${props.join(',\n  ')}\n};\n`);
fs.renameSync(tmp, target);
console.log('Model stages bundled:', props.map(prop => prop.split(':')[0]).join(', ') || 'none');
