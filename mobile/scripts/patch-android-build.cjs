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
