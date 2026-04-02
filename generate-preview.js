/**
 * Generate HTML preview with scraped data
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const dataPath = path.join(__dirname, 'scraped-data.json');
const templatePath = path.join(__dirname, 'preview.html');
const outputPath = path.join(__dirname, 'preview-generated.html');

if (!fs.existsSync(dataPath)) {
  console.error('No scraped-data.json found. Run scraper.js first.');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
let template = fs.readFileSync(templatePath, 'utf-8');

// Inject data into template
template = template.replace('SCRAPED_DATA_PLACEHOLDER', JSON.stringify(data, null, 2));

fs.writeFileSync(outputPath, template);

console.log(`Generated preview: ${outputPath}`);
console.log(`Total images: ${data.length}`);

// Try to open in browser
const platform = process.platform;
const openCmd = platform === 'darwin' ? 'open' : platform === 'win32' ? 'start' : 'xdg-open';

exec(`${openCmd} "${outputPath}"`, (err) => {
  if (err) {
    console.log('\nOpen manually in browser:');
    console.log(`file://${outputPath}`);
  } else {
    console.log('\nOpened in browser!');
  }
});
