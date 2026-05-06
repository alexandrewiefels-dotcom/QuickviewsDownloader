# SASClouds Satellite Image Scraper

A **Streamlit** application that automates the extraction of satellite image footprints, full‑size quickviews, and georeferenced images from the [SASClouds](https://www.sasclouds.com/english/normal/) catalog.

## Features

- 🔐 Password‑protected access (via Streamlit secrets)
- 🌐 Automated browser control (Playwright) – you log in and apply filters manually once
- 🗺️ Extracts footprint polygons (4 corners) and metadata
- 🖼️ Downloads full‑size quickview images and creates **world files (.jgw)** with rotation support
- 📁 Timestamped output folders for each scraping session
- 📤 Export any session as ZIP file, preview footprints on a map

## Prerequisites

- Python 3.9+
- [Playwright browsers](https://playwright.dev/python/docs/intro) (installed automatically via script)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/sasclouds-scraper.git
   cd sasclouds-scraper


## For developer:
Create a virtual environment (recommended)
- bash
- python -m venv venv
- source venv/bin/activate   # Linux/Mac
- venv\Scripts\activate      # Windows

## Run the Streamlit app
- bash
- streamlit run main.py