/**
 * Wallpaper Uploader - Upload scraped images to Cloudflare R2
 * Reads from scraped-data.json and uploads with metadata
 */

import fetch from 'node-fetch';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { S3Client, PutObjectCommand, HeadObjectCommand } from '@aws-sdk/client-s3';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load environment variables
dotenv.config({ path: path.join(__dirname, '.env.local') });
dotenv.config({ path: path.join(__dirname, '.env') });

const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID;
const R2_ACCESS_KEY_ID = process.env.R2_ACCESS_KEY_ID;
const R2_SECRET_ACCESS_KEY = process.env.R2_SECRET_ACCESS_KEY;
const R2_BUCKET_NAME = process.env.R2_BUCKET_NAME;
const R2_PUBLIC_URL = process.env.R2_PUBLIC_URL;
const BASE_FOLDER = process.env.R2_BASE_FOLDER || 'wallpaper';

// Parse command line args
const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const limit = parseInt(args.find(a => a.startsWith('--limit='))?.split('=')[1] || '0');
const categoryFilter = args.find(a => a.startsWith('--category='))?.split('=')[1];
const skipExisting = !args.includes('--force');

// Initialize R2 client
let r2Client = null;
if (R2_ACCESS_KEY_ID && R2_SECRET_ACCESS_KEY && CF_ACCOUNT_ID) {
  r2Client = new S3Client({
    region: 'auto',
    endpoint: `https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: R2_ACCESS_KEY_ID,
      secretAccessKey: R2_SECRET_ACCESS_KEY,
    },
  });
  console.log('[R2] Client initialized');
} else {
  console.error('[Error] R2 credentials not configured');
  console.log('Required env vars: CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME');
  process.exit(1);
}

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

async function checkExists(key) {
  try {
    await r2Client.send(new HeadObjectCommand({
      Bucket: R2_BUCKET_NAME,
      Key: key
    }));
    return true;
  } catch (err) {
    if (err.name === 'NotFound' || err.$metadata?.httpStatusCode === 404) {
      return false;
    }
    throw err;
  }
}

async function downloadImage(url) {
  const response = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
      'Accept': 'image/*',
      'Referer': 'https://hhkungfu.ee/'
    }
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  // Use arrayBuffer instead of deprecated buffer()
  const arrayBuffer = await response.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  const contentType = response.headers.get('content-type') || 'image/webp';

  return { buffer, contentType };
}

// Encode non-ASCII characters for S3/R2 metadata (must be ASCII-safe)
function encodeMetadata(value) {
  if (!value) return '';
  // Use base64 encoding for non-ASCII strings
  return Buffer.from(value, 'utf-8').toString('base64');
}

async function uploadToR2(anime, buffer, contentType) {
  const categorySlug = slugifyCategory(anime.category);
  const ext = contentType.split('/')[1] || 'webp';
  const key = `${BASE_FOLDER}/${categorySlug}/${anime.slug}.${ext}`;

  const command = new PutObjectCommand({
    Bucket: R2_BUCKET_NAME,
    Key: key,
    Body: buffer,
    ContentType: contentType,
    Metadata: {
      // Encode non-ASCII values to base64 for R2 compatibility
      title: encodeMetadata(anime.title.slice(0, 200)),
      category: encodeMetadata(anime.category),
      categoryslug: categorySlug, // ASCII-safe slug
      source: 'hhkungfu.ee',
      sourceurl: anime.imageUrl,
      episodeinfo: anime.episodeInfo || '',
      uploadedat: new Date().toISOString()
    }
  });

  await r2Client.send(command);

  const publicUrl = R2_PUBLIC_URL
    ? `${R2_PUBLIC_URL}/${key}`
    : `https://pub-${CF_ACCOUNT_ID}.r2.dev/${key}`;

  return { key, publicUrl };
}

async function main() {
  console.log('='.repeat(50));
  console.log('Wallpaper Uploader - R2 Upload');
  console.log('='.repeat(50));

  if (dryRun) {
    console.log('[Mode] DRY RUN - No actual uploads');
  }

  // Load scraped data
  const dataPath = path.join(__dirname, 'scraped-data.json');
  if (!fs.existsSync(dataPath)) {
    console.error('[Error] No scraped-data.json found. Run scraper.js first.');
    process.exit(1);
  }

  let animes = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
  console.log(`[Data] Loaded ${animes.length} items`);

  // Apply filters
  if (categoryFilter) {
    animes = animes.filter(a =>
      slugifyCategory(a.category) === slugifyCategory(categoryFilter)
    );
    console.log(`[Filter] Category "${categoryFilter}": ${animes.length} items`);
  }

  if (limit > 0) {
    animes = animes.slice(0, limit);
    console.log(`[Limit] Processing first ${limit} items`);
  }

  // Upload stats
  const stats = {
    total: animes.length,
    uploaded: 0,
    skipped: 0,
    failed: 0
  };

  const results = [];

  for (let i = 0; i < animes.length; i++) {
    const anime = animes[i];
    const categorySlug = slugifyCategory(anime.category);
    const ext = anime.imageUrl.split('.').pop().split('?')[0] || 'webp';
    const key = `${BASE_FOLDER}/${categorySlug}/${anime.slug}.${ext}`;

    process.stdout.write(`\r[${i + 1}/${animes.length}] ${anime.title.slice(0, 40)}...`);

    try {
      // Check if already exists
      if (skipExisting && !dryRun) {
        const exists = await checkExists(key);
        if (exists) {
          stats.skipped++;
          results.push({ ...anime, status: 'skipped', key });
          continue;
        }
      }

      if (dryRun) {
        stats.uploaded++;
        results.push({ ...anime, status: 'dry-run', key });
        continue;
      }

      // Download and upload
      const { buffer, contentType } = await downloadImage(anime.imageUrl);
      const { key: uploadedKey, publicUrl } = await uploadToR2(anime, buffer, contentType);

      stats.uploaded++;
      results.push({ ...anime, status: 'uploaded', key: uploadedKey, publicUrl });

      // Small delay to be respectful
      await new Promise(r => setTimeout(r, 200));
    } catch (error) {
      stats.failed++;
      results.push({ ...anime, status: 'failed', error: error.message });
      console.log(`\n[Error] ${anime.title}: ${error.message}`);
    }
  }

  console.log('\n');
  console.log('='.repeat(50));
  console.log('[Done] Upload complete');
  console.log(`  Total: ${stats.total}`);
  console.log(`  Uploaded: ${stats.uploaded}`);
  console.log(`  Skipped: ${stats.skipped}`);
  console.log(`  Failed: ${stats.failed}`);
  console.log('='.repeat(50));

  // Save results
  const resultsPath = path.join(__dirname, 'upload-results.json');
  fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));
  console.log(`[Saved] ${resultsPath}`);
}

main().catch(console.error);
