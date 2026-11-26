const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const build = path.resolve(__dirname, '../../data/processed/build');
const manifest = JSON.parse(fs.readFileSync(path.join(build, 'manifest.json'), 'utf8'));
const bytes = fs.readFileSync(path.join(build, 'medguide.db'));
const sha = crypto.createHash('sha256').update(bytes).digest('hex');
if (sha !== manifest.sha256 || bytes.length !== manifest.size_bytes) {
  throw new Error('Catalog database does not match its manifest');
}
const assets = path.resolve(__dirname, '../assets/db');
fs.mkdirSync(assets, { recursive: true });
fs.writeFileSync(path.join(assets, 'medguide.db'), bytes);
fs.writeFileSync(path.join(assets, 'version.json'), JSON.stringify({ databaseName: `medguide-${sha.slice(0, 16)}.db` }) + '\n');
console.log(`Prepared catalog ${manifest.db_version} (${sha.slice(0, 16)})`);
