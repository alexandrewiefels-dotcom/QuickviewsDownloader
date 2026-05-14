# 🛰️ OrbitShow — Complete Development Roadmap

> **Generated**: 2026-05-13
> **Status**: Active Development
> **Goal**: Stabilize, clean, and evolve the OrbitShow satellite pass prediction application.

---

## 📋 How to Use This Roadmap

- Each item has a **Priority** (P0=critical → P4=nice-to-have) and a **Status** (⬜=pending, 🔄=in progress, ✅=done)
- Items are grouped into **Phases** that should be tackled in order
- Check `next_session.md` for the current development session's focus

---

## PHASE 1: 🚨 IMMEDIATE — Critical Bug Fixes & Security

> **Goal**: Fix crashes, security vulnerabilities, and data corruption risks.

### P0 — Application Crashes

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 1.1 | Fix `core/drag_drop_handler` — rename to `.py` | `core/drag_drop_handler` | ✅ | Missing `.py` extension — renamed |
| 1.2 | Fix `add_custom_satellite()` call signature | `ui/handlers/live_tracking_handler.py` | ✅ | Called with `swath_km=` and `resolution=` but expects `cameras=` dict |
| 1.3 | Fix `force_download_tles.py` — Streamlit import crash | `force_download_tles.py` | ✅ | Crashes when run as standalone CLI outside Streamlit |
| 1.4 | Fix empty `pass_detection_handler.py` | `ui/handlers/pass_detection_handler.py` | ✅ | File was empty — implemented proper handler |
| 1.5 | Fix `prefetch_all_tles.py` — Streamlit import issue | `prefetch_all_tles.py` | ✅ | Same pattern as 1.3 — fixed with `try/except ImportError` guard |

### P0 — Logic Bugs

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 1.6 | Fix `tasking_runner.py` overlap contradiction (40km vs 0) | `core/tasking_runner.py` | ✅ | Docstring says 0 overlap, code sets 40km — fixed docstring |
| 1.7 | Fix `tasking_optimizer.py` `OVERLAP_PERCENT` (50% vs documented 10%) | `tasking_optimizer.py` | ✅ | Constant was 50%, docstring says 10% — fixed to 10% |
| 1.8 | Fix `_geodesic_min_distance` truncated implementation | `detection/pass_detector.py` | ✅ | Line 46: `# ... existing geodesic code ...` — actual calculation was missing |
| 1.9 | Fix `map_renderer.py` lat/lon swapping confusion | `visualization/map_renderer.py` | ✅ | Added `shapely_coords_to_folium()` utility to standardize conversion |

### P1 — Security Vulnerabilities

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 1.10 | Remove hardcoded admin password — use env vars only | `admin_auth.py` | ✅ | `ADMIN_PASSWORD_HASH` now defaults to `None`; env vars required |
| 1.11 | Remove hardcoded OpenWeatherMap API key fallback | `data/weather.py` | ✅ | Hardcoded key removed; `OWM_API_KEY` defaults to `None` |
| 1.12 | Add rate limiting / privacy notice for IP geolocation | `navigation_tracker.py` | ✅ | Added rate limiter (1 req/10s per IP) + privacy notice docstring |

### P1 — Code Quality

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 1.13 | Replace all `print()` with `logging` across codebase | Multiple files | ✅ | All ~50+ print statements converted to logging |
| 1.14 | Add input validation for AOI upload (file size, vertex count) | `ui/handlers/aoi_handler.py` | ✅ | Added file size check (1 MB max), extension whitelist, vertex count limits |
| 1.15 | Add graceful error handling for TLE fetch failures | `data/tle_fetcher.py` | ✅ | Fixed 6 bare `except:` clauses with specific exception types |
| 1.16 | Fix bare `except:` clauses across codebase | Multiple files | ✅ | Fixed 10+ bare excepts in: `tle_fetcher.py`, `navigation_tracker.py`, `force_download_tles.py`, `core/tle_scheduler.py`, `ui/handlers/aoi_handler.py` |

---

## PHASE 2: ⚡ OPTIMIZATION — Make Interface Feel Better

> **Goal**: Improve UX, performance, and user feedback.

### P2 — User Experience

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 2.1 | Add loading spinners for long operations | `ui/components/spinner.py`, `core/pass_runner.py` | ✅ | `LoadingSpinner`, `ProgressOverlay`, `with_loading_spinner` exist and used |
| 2.2 | Add user-facing toasts for key events | `main.py` | ✅ | App ready, TLE download start/complete |
| 2.3 | Add "select all / deselect all" for satellite checkboxes | `ui/sidebar.py` | ✅ | Per-provider select/deselect buttons |
| 2.4 | Improve daylight filter UX — show filtered count | `detection/daylight_filter.py`, `ui/results_table.py` | ✅ | Shows kept/filtered counts in summary |
| 2.5 | Add search results summary banner | `main.py` | ✅ | Pass count, satellites, ONA range |
| 2.6 | Add keyboard shortcuts (Enter to search) | `ui/sidebar.py` | ✅ | Enter key triggers search button |

### P2 — Performance

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 2.7 | Cache IP geolocation results to reduce external API calls | `navigation_tracker.py` | ✅ | Already implemented with `@lru_cache` + rate limiter |
| 2.8 | Debounce map drawing tool to prevent excessive re-renders | `visualization/map_renderer.py` | ✅ | Hash-based debounce via `last_drawing_hash` in `main.py` |
| 2.9 | Lazy-load footprint rendering for large pass sets | `visualization/map_renderer.py` | ✅ | Server-side filtering by zoom level (10/25/50/all passes), sorted by AOI proximity |
| 2.10 | Add pagination/virtualization for results table | `ui/results_table.py` | ✅ | 50 passes per page with prev/next controls |

### P3 — Polish

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 2.11 | Add session state persistence across page refreshes | `core/state_manager.py` | ✅ | `save_session_to_query_params()` + `_restore_session_from_query_params()` implemented |
| 2.12 | Add dark mode toggle | `main.py`, `ui/` | ✅ | "🌙 Dark" / "☀️ Light" toggle in sidebar |
| 2.13 | Add responsive map height based on viewport | `visualization/map_renderer.py` | ✅ | `_get_responsive_height()` + `_add_responsive_height_js()` implemented |
| 2.14 | Add tooltips for all sidebar controls | `ui/sidebar.py` | ✅ | Added help text to date inputs, ONA sliders, orbit filter, daylight filter |

---

## PHASE 3: 🏗️ SCALABILITY — Architecture & Features

> **Goal**: Improve maintainability, add missing features, prepare for growth.

### P3 — Code Architecture

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 3.1 | Modularize `sasclouds_api_scraper.py` (1438 lines) | `sasclouds_api_scraper.py` | ✅ | Split into `sasclouds/` package (7 modules) |
| 3.2 | Modularize `navigation_tracker.py` (1071 lines) | `navigation_tracker.py` | ✅ | Split into `navigation/` package (4 modules) |
| 3.3 | Modularize `config/satellites.py` (1391 lines) | `config/satellites.py` | ✅ | Split into 3 files: `satellites_common.py`, `satellites_data.py`, `satellites.py` |
| 3.4 | Implement proper `pass_detection_handler.py` | `ui/handlers/pass_detection_handler.py` | ✅ | Centralize detection orchestration |
| 3.5 | Add proper module `__init__.py` exports | All `__init__.py` files | ✅ | Fixed `data/`, `ui/components/`, `geometry/`, `core/` |
| 3.6 | Standardize error handling pattern across modules | All modules | ✅ | Exception hierarchy in `core/exceptions.py`, imported by all core modules |

### P3 — Testing

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 3.7 | Add unit tests for geometry calculations | `tests/` | ✅ | 47 tests in `tests/test_geometry.py` |
| 3.8 | Add unit tests for pass detection logic | `tests/` | ✅ | 14 tests in `tests/test_pass_detector.py` |
| 3.9 | Add unit tests for tasking optimizer | `tests/` | ✅ | 16 tests in `tests/test_tasking_optimizer.py` |
| 3.10 | Add integration tests for full search→tasking flow | `tests/test_integration.py` | ✅ | 18 tests covering TLE→detection→tasking pipeline |
| 3.11 | Add mock TLE data for offline testing | `tests/test_integration.py` | ✅ | 6 realistic mock TLEs for 5 satellite types |
| 3.12 | Set up pytest configuration properly | `pytest.ini`, `tests/` | ✅ | `pytest.ini` with proper config, `run_tests.py`, `test_full_suite.py` |

### P3 — Data Layer

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 3.13 | Add SQLite backend for TLE cache (replace CSV) | `data/tle_cache_sqlite.py` | ✅ | Thread-safe SQLite cache with WAL mode, batch operations, CSV migration |
| 3.14 | Add SQLite backend for logs/analytics (replace JSONL) | `data/logs_sqlite.py` | ✅ | SQLite backend for API interactions, AOI history, search history, quickview ops |
| 3.15 | Add data migration scripts for legacy formats | `migrate_tle_cache.py` | ✅ | Updated with CSV→SQLite and JSONL→SQLite migration support |
| 3.16 | Add automatic log rotation/cleanup | `data/log_rotation.py` | ✅ | Gzip compression, size/age-based rotation, archive cleanup |

### P4 — Features

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 3.17 | Add multi-user authentication system | `auth/auth_manager.py` | ✅ | Role-based (admin/user/viewer), env var + JSON config, session timeout |
| 3.18 | Add API rate limiting dashboard | `ui/pages/rate_limiting_dashboard.py` | ✅ | Shows remaining quota for Space-Track, N2YO, OWM with progress bars |
| 3.19 | Add search configuration save/load (export/import) | `data/search_config.py` | ✅ | Save/restore filter configurations as JSON files |
| 3.20 | Add batch tasking for multiple AOIs | `core/batch_tasking.py` | ✅ | Process multiple regions in one run with comparison table |
| 3.21 | Add satellite pass animation (time slider) | `visualization/pass_animation.py` | ✅ | Animate passes over time with play button |
| 3.22 | Add PDF report generation for tasking results | `visualization/pdf_exporter.py` | ✅ | Enhanced with cover page, per-satellite tables, coverage stats, static map |
| 3.23 | Add CI/CD pipeline (GitHub Actions) | `.github/workflows/ci.yml` | ✅ | Automated testing on push/PR with Python 3.11/3.12, linting, health check |

### P4 — Monitoring & Operations

| # | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| 3.24 | Add application health check endpoint | `health.py` | ✅ | Checks Python env, directories, TLE cache, logs, config, env vars, disk space |
| 3.25 | Add structured logging with log levels | All modules | ✅ | All print() replaced with logging throughout codebase |
| 3.26 | Add performance metrics (search time, render time) | `core/performance_metrics.py` | ✅ | Timer context manager, per-operation stats, Streamlit dashboard |
| 3.27 | Add TLE freshness monitoring dashboard | `pages/tle_admin.py` | ✅ | Age distribution chart, per-satellite freshness table, recommendations |

---

## 📊 Progress Summary

| Phase | Total Items | Completed | In Progress | Pending |
|---|---|---|---|---|
| **P1: Immediate** | 16 | **16** | 0 | 0 |
| **P2: Optimization** | 14 | **14** | 0 | 0 |
| **P3: Scalability** | 27 | **27** | 0 | 0 |
| **Total** | **57** | **57** | **0** | **0** |

---

## 🎯 Project Complete! 🎉

All 57 roadmap items have been implemented. The OrbitShow application is now:

- **Phase 1 (Immediate fixes)** — **100% complete** ✅ — All crashes fixed, security vulnerabilities patched, code quality improved
- **Phase 2 (Optimization)** — **100% complete** ✅ — UX improvements, performance optimizations, polish
- **Phase 3 (Scalability)** — **100% complete** ✅ — Architecture modularized, testing infrastructure in place, data layer upgraded, all features implemented

### Key Achievements

- **16 critical bugs** fixed (crashes, logic errors, security issues)
- **14 UX/performance improvements** (spinners, pagination, dark mode, lazy loading)
- **27 scalability features** (modular architecture, 284 tests, SQLite backends, CI/CD, auth system, dashboards)
- **57/57 roadmap items completed**

### What's Next?

See `next_session.md` for future development directions beyond the current roadmap.
