import fs from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '..');
const srcDir = path.join(repoRoot, 'questionnaires');
const dstDir = path.join(process.cwd(), 'public', 'questionnaires');

const files = [
  '16Personalities.json',
  'BFI.json',
  'PVQ.json',
  'EIS.json',
  'LMS.json'
];

await fs.mkdir(dstDir, { recursive: true });

for (const name of files) {
  const src = path.join(srcDir, name);
  const dst = path.join(dstDir, name);
  const buf = await fs.readFile(src);
  await fs.writeFile(dst, buf);
}

console.log(`[copy_questionnaires] Copied ${files.length} files to ${dstDir}`);
