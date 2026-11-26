// Lets the app import shared/dictionaries/*.json (single source of truth with the Python engine).
const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
config.resolver.assetExts.push('db', 'onnx', 'f32');
config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, '..', 'shared')];

module.exports = config;
