/**
 * List Images - View uploaded wallpapers in R2
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { S3Client, ListObjectsV2Command, HeadObjectCommand } from '@aws-sdk/client-s3';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({ path: path.join(__dirname, '.env.local') });
dotenv.config({ path: path.join(__dirname, '.env') });

const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID;
const R2_ACCESS_KEY_ID = process.env.R2_ACCESS_KEY_ID;
const R2_SECRET_ACCESS_KEY = process.env.R2_SECRET_ACCESS_KEY;
const R2_BUCKET_NAME = process.env.R2_BUCKET_NAME;
const R2_PUBLIC_URL = process.env.R2_PUBLIC_URL;
const BASE_FOLDER = process.env.R2_BASE_FOLDER || 'wallpaper';

// Parse args
const args = process.argv.slice(2);
const outputJson = args.includes('--json');
const categoryFilter = args.find(a => a.startsWith('--category='))?.split('=')[1];

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
}

// Decode base64 metadata (reverse of uploader encoding)
function decodeMetadata(value) {
  if (!value) return '';
  try {
    return Buffer.from(value, 'base64').toString('utf-8');
  } catch {
    return value; // Return as-is if not base64
  }
}

async function listImages() {
  if (!r2Client) {
    console.error('[Error] R2 not configured');
    process.exit(1);
  }

  const prefix = categoryFilter
    ? `${BASE_FOLDER}/${categoryFilter}/`
    : `${BASE_FOLDER}/`;

  console.log(`[R2] Listing objects from: ${prefix}`);

  const command = new ListObjectsV2Command({
    Bucket: R2_BUCKET_NAME,
    Prefix: prefix,
    MaxKeys: 1000
  });

  const response = await r2Client.send(command);

  if (!response.Contents || response.Contents.length === 0) {
    console.log('[Info] No images found');
    return;
  }

  const images = [];

  for (const obj of response.Contents) {
    // Skip manifest.json
    if (obj.Key.endsWith('.json')) continue;

    let metadata = {};
    try {
      const headResponse = await r2Client.send(new HeadObjectCommand({
        Bucket: R2_BUCKET_NAME,
        Key: obj.Key
      }));
      metadata = headResponse.Metadata || {};
    } catch (err) {
      // Ignore metadata fetch errors
    }

    const publicUrl = R2_PUBLIC_URL
      ? `${R2_PUBLIC_URL}/${obj.Key}`
      : `https://pub-${CF_ACCOUNT_ID}.r2.dev/${obj.Key}`;

    const pathParts = obj.Key.split('/');
    const category = pathParts.length > 1 ? pathParts[1] : 'unknown';

    // Decode base64 encoded metadata
    const decodedTitle = decodeMetadata(metadata.title) || pathParts[pathParts.length - 1].replace(/\.\w+$/, '');
    const decodedCategory = decodeMetadata(metadata.category) || category;

    images.push({
      key: obj.Key,
      url: publicUrl,
      title: decodedTitle,
      category: decodedCategory,
      categorySlug: metadata.categoryslug || category,
      source: metadata.source || 'hhkungfu.ee',
      uploadedAt: obj.LastModified?.toISOString(),
      size: obj.Size
    });
  }

  if (outputJson) {
    console.log(JSON.stringify(images, null, 2));
    return;
  }

  // Print summary
  console.log(`\n[Found] ${images.length} images\n`);

  // Group by category
  const byCategory = {};
  images.forEach(img => {
    if (!byCategory[img.category]) {
      byCategory[img.category] = [];
    }
    byCategory[img.category].push(img);
  });

  console.log('Categories:');
  Object.entries(byCategory)
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([cat, imgs]) => {
      console.log(`  ${cat}: ${imgs.length} images`);
    });

  console.log('\nRecent uploads:');
  images
    .sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt))
    .slice(0, 10)
    .forEach(img => {
      console.log(`  - ${img.title} (${img.category})`);
      console.log(`    ${img.url}`);
    });

  // Save to file
  const outputPath = path.join(__dirname, 'r2-images.json');
  fs.writeFileSync(outputPath, JSON.stringify(images, null, 2));
  console.log(`\n[Saved] ${outputPath}`);
}

listImages().catch(console.error);
