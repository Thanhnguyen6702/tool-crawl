/**
 * Sitemap-based Scraper - Scrapes ALL anime from sitemap
 * Supports multiple categories per anime
 */

import fetch from 'node-fetch';
import * as cheerio from 'cheerio';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const BASE_URL = 'https://hhkungfu.ee';
const SITEMAP_URL = 'https://hhkungfu.ee/post-sitemap.xml';

// Parse command line args
const args = process.argv.slice(2);
const limit = parseInt(args.find(a => a.startsWith('--limit='))?.split('=')[1] || '0');
const startFrom = parseInt(args.find(a => a.startsWith('--start='))?.split('=')[1] || '0');
const delayMs = parseInt(args.find(a => a.startsWith('--delay='))?.split('=')[1] || '1500');

async function fetchWithRetry(url, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      // Random delay to avoid rate limiting
      const delay = delayMs + Math.random() * 1000;
      await new Promise(r => setTimeout(r, delay));

      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
          'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
          'Referer': 'https://hhkungfu.ee/',
          'Connection': 'keep-alive'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.text();
    } catch (error) {
      if (attempt < retries) {
        console.log(`  [Retry ${attempt}/${retries}] ${error.message}`);
        await new Promise(r => setTimeout(r, 3000));
      } else {
        throw error;
      }
    }
  }
}

async function getSitemapUrls() {
  console.log('[Sitemap] Fetching post-sitemap.xml...');
  const xml = await fetchWithRetry(SITEMAP_URL);
  const $ = cheerio.load(xml, { xmlMode: true });

  const urls = [];
  $('url loc').each((i, el) => {
    const url = $(el).text().trim();
    // Filter out non-anime pages
    if (url && !url.includes('/page/') && !url.includes('/tag/') && !url.includes('/author/')) {
      urls.push(url);
    }
  });

  console.log(`[Sitemap] Found ${urls.length} anime URLs`);
  return urls;
}

function slugify(text) {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

async function scrapeAnimePage(url) {
  try {
    const html = await fetchWithRetry(url);
    const $ = cheerio.load(html);

    // Get title
    let title = $('h1.Title, .entry-title, h1').first().text().trim();
    if (!title) {
      title = $('title').text().split('|')[0].trim();
    }

    // Get poster image - prefer full resolution
    let imageUrl = null;
    let thumbnailUrl = null;

    // First try og:image which often has full resolution
    const ogImage = $('meta[property="og:image"]').attr('content');
    if (ogImage && ogImage.includes('wp-content/uploads')) {
      imageUrl = ogImage;
    }

    // Try multiple selectors for images
    const imgSelectors = [
      '.Image img',
      '.TPostMv img',
      '.poster img',
      '.wp-post-image',
      'article img',
      '.entry-content img'
    ];

    for (const selector of imgSelectors) {
      const $img = $(selector).first();
      const src = $img.attr('data-src') || $img.attr('src') || $img.attr('data-lazy-src');
      if (src && src.includes('wp-content/uploads')) {
        thumbnailUrl = src.startsWith('http') ? src : BASE_URL + src;
        if (!imageUrl) imageUrl = thumbnailUrl;
        break;
      }
    }

    // Try to convert thumbnail to full resolution
    // Pattern: filename-300x450.webp -> filename.jpg
    if (imageUrl) {
      const fullResUrl = imageUrl
        .replace(/-\d+x\d+\.webp$/i, '.jpg')
        .replace(/-\d+x\d+\.png$/i, '.png')
        .replace(/-\d+x\d+\.jpeg$/i, '.jpeg');

      // If URL changed, we found a potential full-res version
      if (fullResUrl !== imageUrl) {
        imageUrl = fullResUrl;
      }
    }

    // Get categories - multiple categories supported
    const categories = [];
    const categorySelectors = [
      '.genres a',
      '.Genre a',
      '.cat-links a',
      '.entry-categories a',
      'a[rel="tag"]',
      '.InfoList a[href*="the-loai"]'
    ];

    // Categories to exclude (website tags, not genres)
    const excludeCategories = [
      'hhkungfu', 'hhkungfu tv', 'hoạt hình kungfu', 'hoat hinh kungfu',
      'vietsub', 'full hd', '4k', 'hd', 'anime', 'donghua'
    ];

    for (const selector of categorySelectors) {
      $(selector).each((i, el) => {
        const cat = $(el).text().trim();
        const catLower = cat.toLowerCase();
        // Only add valid genre categories
        if (cat && !categories.includes(cat) && !excludeCategories.some(ex => catLower.includes(ex))) {
          categories.push(cat);
        }
      });
    }

    // Get episode info
    let episodeInfo = '';
    const epMatch = $('body').text().match(/Tập\s*(\d+(?:\/\d+)?)/i);
    if (epMatch) {
      episodeInfo = epMatch[0];
    }

    if (!imageUrl || !title) {
      return null;
    }

    return {
      title,
      imageUrl,
      link: url,
      categories: categories.length > 0 ? categories : ['Unknown'],
      episodeInfo,
      slug: slugify(title)
    };
  } catch (error) {
    console.log(`  [Error] ${error.message}`);
    return null;
  }
}

async function main() {
  console.log('='.repeat(60));
  console.log('Sitemap-based Wallpaper Scraper');
  console.log('='.repeat(60));
  console.log(`Delay: ${delayMs}ms | Start: ${startFrom} | Limit: ${limit || 'all'}`);
  console.log('');

  // Get all URLs from sitemap
  let urls = await getSitemapUrls();

  // Apply start and limit
  if (startFrom > 0) {
    urls = urls.slice(startFrom);
    console.log(`[Skip] Starting from index ${startFrom}`);
  }

  if (limit > 0) {
    urls = urls.slice(0, limit);
    console.log(`[Limit] Processing ${limit} URLs`);
  }

  console.log(`\n[Scraping] ${urls.length} anime pages...\n`);

  const animes = [];
  let successCount = 0;
  let failCount = 0;

  // Load existing data to continue
  const outputPath = path.join(__dirname, 'scraped-data.json');
  let existingData = [];
  if (fs.existsSync(outputPath)) {
    existingData = JSON.parse(fs.readFileSync(outputPath, 'utf-8'));
    console.log(`[Resume] Found ${existingData.length} existing items`);
  }

  const existingUrls = new Set(existingData.map(a => a.link));

  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    const progress = `[${i + 1}/${urls.length}]`;

    // Skip if already scraped
    if (existingUrls.has(url)) {
      process.stdout.write(`\r${progress} Skipped (exists): ${url.slice(0, 50)}...`);
      continue;
    }

    process.stdout.write(`\r${progress} Scraping: ${url.slice(0, 50)}...                    `);

    const anime = await scrapeAnimePage(url);

    if (anime) {
      animes.push(anime);
      successCount++;

      // Save progress every 10 items
      if (animes.length % 10 === 0) {
        const allData = [...existingData, ...animes];
        fs.writeFileSync(outputPath, JSON.stringify(allData, null, 2));
        process.stdout.write(` [Saved: ${allData.length}]`);
      }
    } else {
      failCount++;
    }
  }

  // Final save
  const allData = [...existingData, ...animes];

  // Deduplicate by image URL
  const seen = new Set();
  const uniqueData = allData.filter(a => {
    if (seen.has(a.imageUrl)) return false;
    seen.add(a.imageUrl);
    return true;
  });

  fs.writeFileSync(outputPath, JSON.stringify(uniqueData, null, 2));

  console.log('\n\n' + '='.repeat(60));
  console.log('[Done] Scraping complete');
  console.log(`  New: ${successCount} | Failed: ${failCount}`);
  console.log(`  Total unique: ${uniqueData.length}`);
  console.log(`  Saved: ${outputPath}`);
  console.log('='.repeat(60));

  // Category summary
  const categoryCounts = {};
  uniqueData.forEach(a => {
    (a.categories || [a.category]).forEach(cat => {
      categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
    });
  });

  console.log('\nCategories:');
  Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .forEach(([cat, count]) => {
      console.log(`  ${cat}: ${count}`);
    });
}

main().catch(console.error);
