# Wallpaper Scraper

Scrape anime wallpapers from hhkungfu.ee and upload to Cloudflare R2.

## Features

- Scrape anime posters with metadata (title, category, episode info)
- Support multiple categories: Tu Tiên, Luyện Cấp, Trùng Sinh, Kiếm Hiệp, Xuyên Không, Hài Hước, Hiện Đại, OVA
- Upload to Cloudflare R2 with organized folder structure
- Skip duplicate uploads
- Vietnamese metadata support (base64 encoded)

## Setup

1. Copy environment variables:
```bash
cp .env.example .env.local
```

2. Configure R2 credentials in `.env.local`:
```
CLOUDFLARE_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=your_bucket_name
R2_PUBLIC_URL=https://your-public-url.r2.dev
```

3. Install dependencies:
```bash
npm install
```

## Usage

### Scrape Images

```bash
# Scrape all categories (5 pages each)
npm run scrape

# Scrape specific category
node scraper.js --category=tu-tien --pages=10

# Available categories:
# tu-tien, luyen-cap, trung-sinh, kiem-hiep, xuyen-khong, hai-huoc, hien-dai, ova
```

### Upload to R2

```bash
# Upload all scraped images
npm run upload

# Dry run (preview without uploading)
node uploader.js --dry-run

# Upload specific category
node uploader.js --category=tu-tien

# Limit number of uploads
node uploader.js --limit=10

# Force re-upload existing images
node uploader.js --force
```

### List Uploaded Images

```bash
# List all images
npm run list

# Filter by category
node list-images.js --category=tu-tien

# Output as JSON
node list-images.js --json
```

## R2 Folder Structure

```
wallpaper/
├── tu-tien/
│   ├── tien-nghich.webp
│   ├── dau-pha-thuong-khung-phan-5.webp
│   └── ...
├── luyen-cap/
│   └── ...
├── kiem-hiep/
│   └── ...
└── ...
```

## Metadata

Each uploaded image includes:
- `title`: Vietnamese title (base64 encoded)
- `category`: Category name (base64 encoded)
- `categoryslug`: URL-safe category slug
- `source`: Source website (hhkungfu.ee)
- `sourceurl`: Original image URL
- `uploadedat`: Upload timestamp

## Public URLs

Images are accessible at:
```
https://your-r2-domain/wallpaper/{category-slug}/{anime-slug}.webp
```

Example:
```
https://pub-xxx.r2.dev/wallpaper/tu-tien/tien-nghich.webp
```
