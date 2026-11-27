const fs = require('node:fs');
const path = require('node:path');

const packageFile = require.resolve('onnxruntime-react-native/package.json');
const { version } = require(packageFile);
const file = path.join(path.dirname(packageFile), 'android/build.gradle');
if (version !== '1.24.3') throw new Error('Review the ONNX Runtime Android compatibility patch for ' + version);
const oldCondition = 'VersionNumber.parse(REACT_NATIVE_VERSION) < VersionNumber.parse("0.71")';
const newCondition = 'REACT_NATIVE_MINOR_VERSION < 71';
const oldArtifact = 'onnxruntime-android:latest.integration@aar';
const newArtifact = 'onnxruntime-android:1.24.3@aar';
let code = fs.readFileSync(file, 'utf8');
if (!code.includes(oldCondition) && !code.includes(newCondition)) throw new Error('Unexpected ONNX Runtime Gradle source');
if (!code.includes(oldArtifact) && !code.includes(newArtifact)) throw new Error('Unexpected ONNX Runtime Android dependency');
const updated = code.replace(oldCondition, newCondition).replace(oldArtifact, newArtifact);
if (updated !== code) fs.writeFileSync(file, updated);

const cameraPackage = require.resolve('expo-camera/package.json');
if (require(cameraPackage).version !== '58.0.14') throw new Error('Review the CameraX preview frame patch for this Expo Camera version');
const cameraRoot = path.join(path.dirname(cameraPackage), 'android/src/main/java/expo/modules/camera');

function patchCamera(name, changes) {
  const destination = path.join(cameraRoot, name);
  const original = fs.readFileSync(destination, 'utf8');
  let patched = original;
  for (const [before, after] of changes) {
    if (!patched.includes(after)) {
      if (!patched.includes(before)) throw new Error(`Unexpected Expo Camera source in ${name}`);
      patched = patched.replace(before, after);
    }
  }
  if (patched !== original) fs.writeFileSync(destination, patched);
}

patchCamera('CameraViewModule.kt', [
  ['  "onCameraReady",', '  "onCameraReady",\n  "onPackagePreviewFrame",'],
  ['      Events(cameraEvents)', `      Events(cameraEvents)

      Prop("packageGuideEnabled") { view, enabled: Boolean? ->
        view.setPackageGuideEnabled(enabled == true)
      }`],
]);

patchCamera('ExpoCameraView.kt', [
  ['  private val onCameraReady by EventDispatcher<Unit>()', `  private val onCameraReady by EventDispatcher<Unit>()
  private val onPackagePreviewFrame by EventDispatcher<Map<String, Any>>()
  private var packageGuideEnabled = false`],
  ['    imageAnalysisUseCase = if (shouldScanBarcodes) {', '    imageAnalysisUseCase = if (shouldScanBarcodes || packageGuideEnabled) {'],
  ['    val useCases = UseCaseGroup.Builder().apply {\n      addUseCase(preview)', `    val useCases = UseCaseGroup.Builder().apply {
      if (packageGuideEnabled) previewView.viewPort?.let { setViewPort(it) }
      addUseCase(preview)`],
  ['      .also { analyzer ->\n        if (shouldScanBarcodes', `      .also { analyzer ->
        if (packageGuideEnabled && !shouldScanBarcodes) {
          analyzer.setAnalyzer(
            ContextCompat.getMainExecutor(context),
            expo.modules.camera.analyzers.PackageGuideAnalyzer { onPackagePreviewFrame(it) }
          )
        }
        if (shouldScanBarcodes`],
  ['  fun setShouldScanBarcodes(shouldScanBarcodes: Boolean) {', `  fun setPackageGuideEnabled(enabled: Boolean) {
    if (packageGuideEnabled != enabled) {
      packageGuideEnabled = enabled
      shouldCreateCamera = true
    }
  }

  fun setShouldScanBarcodes(shouldScanBarcodes: Boolean) {`],
]);
fs.copyFileSync(path.join(__dirname, 'android/PackageGuideAnalyzer.kt'), path.join(cameraRoot, 'analyzers/PackageGuideAnalyzer.kt'));
