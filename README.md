# CurseForge Modpack Downloader

A fast, dependency‑free Python tool that downloads complete CurseForge modpacks — including all mods, configs, and overrides — directly from a URL or an exported ZIP file.

## Features
- Download modpacks from a **CurseForge URL** or a **local ZIP export**
- Fetch all mod `.jar` files using the official CurseForge API
- Automatic fallback to CDN when direct download URLs are blocked
- Multithreaded downloads (8 workers)
- Merges overrides into the final output directory
- No external Python packages required

## Requirements
- Python 3.8+
- Internet connection

## Usage

### Download from a CurseForge URL
```bash
python cf_downloader.py https://www.curseforge.com/minecraft/modpacks/beyond-depth ./BeyondDepth

### Download from a local exported ZIP
```bash
python cf_downloader.py "Beyond Depth-Ver12.7.0.zip" ./BeyondDepth
