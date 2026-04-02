/**
 * Preview scraped images before upload
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_FOLDER = process.env.R2_BASE_FOLDER || 'wallpaper';

function slugifyCategory(category) {
  return category
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim() || 'unknown';
}

const dataPath = path.join(__dirname, 'scraped-data.json');
if (!fs.existsSync(dataPath)) {
  console.error('No scraped-data.json found. Run scraper.js first.');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));

console.log('='.repeat(70));
console.log('PREVIEW - Wallpapers to Upload');
console.log('='.repeat(70));
console.log(`Total: ${data.length} images\n`);

// Group by category
const byCategory = {};
data.forEach(item => {
  const cat = item.category || 'Unknown';
  if (!byCategory[cat]) byCategory[cat] = [];
  byCategory[cat].push(item);
});

// Summary table
console.log('Category Summary:');
console.log('-'.repeat(40));
Object.entries(byCategory)
  .sort((a, b) => b[1].length - a[1].length)
  .forEach(([cat, items]) => {
    const catSlug = slugifyCategory(cat);
    console.log(`  ${cat.padEnd(15)} ${items.length} images → wallpaper/${catSlug}/`);
  });

console.log('\n');

// Detailed list
Object.entries(byCategory).forEach(([cat, items]) => {
  const catSlug = slugifyCategory(cat);
  console.log(`\n📁 ${cat} (${items.length} images)`);
  console.log('-'.repeat(60));

  items.forEach((item, i) => {
    const targetPath = `${BASE_FOLDER}/${catSlug}/${item.slug}.webp`;
    console.log(`${(i + 1).toString().padStart(2)}. ${item.title}`);
    console.log(`    Source: ${item.imageUrl}`);
    console.log(`    Target: ${targetPath}`);
    if (item.episodeInfo) {
      console.log(`    Info: ${item.episodeInfo}`);
    }
  });
});

console.log('\n' + '='.repeat(70));
console.log('To upload all images, run:');
console.log('  node uploader.js');
console.log('\nTo upload specific category:');
console.log('  node uploader.js --category=tu-tien');
console.log('='.repeat(70));
