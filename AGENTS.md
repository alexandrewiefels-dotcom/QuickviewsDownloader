# Repository Guidelines

## Project Structure & Module Organization
This repository contains a modular Streamlit application for satellite pass prediction and Earth Observation (EO) tasking. The architecture is designed for scalability and maintainability, separating core logic from UI and data handling.

- **`config/`**: Centralized configuration, including satellite definitions (`satellites.py`) and application constants (`constants.py`).
- **`core/`**: Orchestrates high-level application flows. `pass_runner.py` handles standard pass prediction, while `tasking_runner.py` manages optimized EO tasking sessions.
- **`data/`**: Manages external data sources and persistent caches. Key files include `tle_fetcher.py` for orbital data and `aoi_handler.py` for Area of Interest management.
- **`detection/`**: Core computational logic for satellite observability. `pass_detector.py` calculates visibility windows, and `daylight_filter.py` ensures acquisitions occur during lighting conditions.
- **`geometry/`**: Low-level orbital mechanics, great-circle calculations, and sensor footprint generation.
- **`ui/`**: Streamlit-specific components, organized into `components/` (widgets), `pages/` (views), and `handlers/` (UI-specific state transitions).
- **`visualization/`**: Handles data exports and map rendering. Supports PDF (`pdf_exporter.py`), KML (`kml_exporter.py`), and CSV formats, with `map_renderer.py` utilizing Folium for interactive maps.

## Build, Test, and Development Commands
The project is built on Streamlit and requires a Python environment with the dependencies listed in `requirements.txt`.

- **Run Application**: `streamlit run main.py`
- **TLE Management**:
  - `python prefetch_all_tles.py`: Pre-populates the TLE cache for all satellites.
  - `python update_tles.py`: Triggers an incremental TLE update.
  - `python force_download_tles.py`: Forces a complete re-download of the TLE database.
- **Utility Scripts**:
  - `python cleanup_tle_cache.py`: Maintenance script for the local TLE storage.
  - `python migrate_tle_cache.py`: Handles schema changes in the TLE cache.

## Coding Style & Naming Conventions
- Follow **PEP 8** standards for Python code.
- Use **Streamlit session state** (`st.session_state`) for all cross-component communication, managed primarily through `core/state_manager.py`.
- Prefer modular UI components in `ui/components/` over monolithic page scripts.

## Testing Guidelines
Testing is currently performed via ad-hoc scripts in the project root:
- `python test.py`: Tests the static map exporter and footprint generation.
- `python test_tle.py`: Verifies TLE fetching and parsing logic.

## Commit & Pull Request Guidelines
Commit messages typically follow a timestamped pattern or a direct description:
- `YYYYMMDD-HH:MM - [Description]` (e.g., `20260415-11:46 - Two tasking modes, animation`)
- Clear, concise descriptions for bug fixes and feature additions (e.g., `Fix many bugs`, `More satellites`).

