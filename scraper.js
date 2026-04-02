/**
 * Wallpaper Scraper - Scrapes anime posters from hhkungfu.ee
 * Extracts: title, image URL, category, episode info
 */

import fetch from 'node-fetch';
import * as cheerio from 'cheerio';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const BASE_URL = 'https://hhkungfu.ee';
const CATEGORIES = {
  'tu-tien': 'Tu Tiên',
  'luyen-cap': 'Luyện Cấp',
  'trung-sinh': 'Trùng Sinh',
  'kiem-hiep': 'Kiếm Hiệp',
  'xuyen-khong': 'Xuyên Không',
  'hai-huoc': 'Hài Hước',
  'hien-dai': 'Hiện Đại',
  'ova': 'OVA'
};

// Parse command line args
const args = process.argv.slice(2);
const categoryArg = args.find(a => a.startsWith('--category='));
const targetCategory = categoryArg ? categoryArg.split('=')[1] : null;
const maxPages = parseInt(args.find(a => a.startsWith('--pages='))?.split('=')[1] || '5');

async function fetchPage(url, retries = 3) {
  console.log(`[Fetch] ${url}`);

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      // Random delay to avoid rate limiting (2-5 seconds)
      const delay = 2000 + Math.random() * 3000;
      await new Promise(r => setTimeout(r, delay));

      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
          'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
          'Accept-Encoding': 'gzip, deflate, br',
          'Connection': 'keep-alive',
          'Cache-Control': 'max-age=0',
          'Referer': 'https://hhkungfu.ee/'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.text();
    } catch (error) {
      console.error(`[Attempt ${attempt}/${retries}] Failed: ${error.message}`);
      if (attempt < retries) {
        console.log(`[Retry] Waiting 5s before retry...`);
        await new Promise(r => setTimeout(r, 5000));
      }
    }
  }
  return null;
}

function extractAnimeFromPage(html, category) {
  const $ = cheerio.load(html);
  const animes = [];

  // Find all anime items - typically in article or div with specific classes
  $('article, .item, .movie-item, .post-item, .TPostMv').each((i, el) => {
    const $el = $(el);

    // Try to find the image
    const $img = $el.find('img').first();
    let imageUrl = $img.attr('data-src') || $img.attr('src') || $img.attr('data-lazy-src');

    // Try to find title
    let title = $el.find('.Title, .entry-title, h2, h3, .post-title').first().text().trim();
    if (!title) {
      title = $img.attr('alt') || $img.attr('title') || '';
    }

    // Try to find link
    const link = $el.find('a').first().attr('href') || '';

    // Extract episode info if present
    let episodeInfo = '';
    const epMatch = $el.text().match(/Tập\s*(\d+(?:\/\d+)?)/i);
    if (epMatch) {
      episodeInfo = epMatch[0];
    }

    // Clean and validate
    if (imageUrl && title && imageUrl.includes('wp-content/uploads')) {
      // Ensure full URL
      if (!imageUrl.startsWith('http')) {
        imageUrl = BASE_URL + imageUrl;
      }

      animes.push({
        title: title.trim(),
        imageUrl,
        link,
        category,
        episodeInfo,
        slug: slugify(title)
      });
    }
  });

  return animes;
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

async function scrapeCategory(categorySlug, categoryName, pages = 5) {
  console.log(`\n[Scrape] Category: ${categoryName} (${categorySlug})`);
  const allAnimes = [];

  for (let page = 1; page <= pages; page++) {
    const url = page === 1
      ? `${BASE_URL}/the-loai/${categorySlug}/`
      : `${BASE_URL}/the-loai/${categorySlug}/page/${page}/`;

    const html = await fetchPage(url);
    if (!html) break;

    const animes = extractAnimeFromPage(html, categoryName);
    if (animes.length === 0) {
      console.log(`[Info] No more items at page ${page}`);
      break;
    }

    allAnimes.push(...animes);
    console.log(`[Page ${page}] Found ${animes.length} items (total: ${allAnimes.length})`);

    // Small delay to be respectful
    await new Promise(r => setTimeout(r, 500));
  }

  return allAnimes;
}

async function scrapeHomepage() {
  console.log('\n[Scrape] Homepage');
  const html = await fetchPage(BASE_URL);
  if (!html) return [];

  const $ = cheerio.load(html);
  const animes = [];

  // Scrape various sections on homepage
  $('.TPostMv, .item, article').each((i, el) => {
    const $el = $(el);
    const $img = $el.find('img').first();
    const $link = $el.find('a').first();

    let imageUrl = $img.attr('data-src') || $img.attr('src') || $img.attr('data-lazy-src');
    let title = $el.find('.Title, h2, h3').first().text().trim() || $img.attr('alt') || '';

    if (imageUrl && title && imageUrl.includes('wp-content/uploads')) {
      if (!imageUrl.startsWith('http')) {
        imageUrl = BASE_URL + imageUrl;
      }

      // Try to detect category from badges or labels
      let category = 'Unknown';
      const $badge = $el.find('.Qlty, .badge, .genre');
      if ($badge.length) {
        category = $badge.first().text().trim();
      }

      animes.push({
        title: title.trim(),
        imageUrl,
        link: $link.attr('href') || '',
        category,
        slug: slugify(title)
      });
    }
  });

  return animes;
}

async function main() {
  console.log('='.repeat(50));
  console.log('Wallpaper Scraper - hhkungfu.ee');
  console.log('='.repeat(50));

  let allAnimes = [];

  if (targetCategory) {
    // Scrape specific category
    if (!CATEGORIES[targetCategory]) {
      console.error(`[Error] Invalid category: ${targetCategory}`);
      console.log('Available categories:', Object.keys(CATEGORIES).join(', '));
      process.exit(1);
    }

    const animes = await scrapeCategory(targetCategory, CATEGORIES[targetCategory], maxPages);
    allAnimes = animes;
  } else {
    // Scrape all categories
    for (const [slug, name] of Object.entries(CATEGORIES)) {
      const animes = await scrapeCategory(slug, name, maxPages);
      allAnimes.push(...animes);
    }
  }

  // Also scrape homepage for any additional items
  const homepageAnimes = await scrapeHomepage();

  // Merge and deduplicate by image URL
  const seen = new Set();
  const uniqueAnimes = [];

  for (const anime of [...allAnimes, ...homepageAnimes]) {
    if (!seen.has(anime.imageUrl)) {
      seen.add(anime.imageUrl);
      uniqueAnimes.push(anime);
    }
  }

  // Save results
  const outputPath = path.join(__dirname, 'scraped-data.json');
  fs.writeFileSync(outputPath, JSON.stringify(uniqueAnimes, null, 2));

  console.log('\n' + '='.repeat(50));
  console.log(`[Done] Scraped ${uniqueAnimes.length} unique items`);
  console.log(`[Saved] ${outputPath}`);
  console.log('='.repeat(50));

  // Print category summary
  const categoryCounts = {};
  uniqueAnimes.forEach(a => {
    categoryCounts[a.category] = (categoryCounts[a.category] || 0) + 1;
  });

  console.log('\nCategory breakdown:');
  Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])
    .forEach(([cat, count]) => {
      console.log(`  ${cat}: ${count}`);
    });
}

main().catch(console.error);
