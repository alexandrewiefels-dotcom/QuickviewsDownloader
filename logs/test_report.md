# SASClouds Scraper — Test Report
Generated: 2026-05-12 14:38:54  |  Live tests: no

## Summary
| Status | Count |
|--------|-------|
| ✓ PASS  | 61 |
| ✗ FAIL  | 0 |
| ! ERROR | 0 |
| ~ SKIP  | 0 |
| **Total** | **61** |

Total elapsed: 1.0s

---
## Full Results by Category

### Config & Paths
| Test | Status | ms |
|------|--------|----|
| config_json_exists | OK   PASS | 16 |
| config_api_version_is_v5 | OK   PASS | 0 |
| module_app_dir_is_absolute | OK   PASS | 0 |
| log_dir_exists | OK   PASS | 0 |
| structured_log_path_absolute | OK   PASS | 0 |
### Satellite Groups
| Test | Status | ms |
|------|--------|----|
| groups_not_empty | OK   PASS | 0 |
| all_entries_have_satellite_id | OK   PASS | 0 |
| all_entries_have_sensor_ids | OK   PASS | 0 |
### Shapefile Creation
| Test | Status | ms |
|------|--------|----|
| creates_three_sidecar_files | OK   PASS | 405 |
| all_three_files_nonempty | OK   PASS | 15 |
| outer_ring_is_clockwise | OK   PASS | 0 |
| simplifies_dense_polygon | OK   PASS | 15 |
| rejects_empty_feature_collection | OK   PASS | 0 |
### Upload AOI
| Test | Status | ms |
|------|--------|----|
| upload_sends_single_file_field | OK   PASS | 16 |
| upload_shp_is_clockwise | OK   PASS | 15 |
| upload_returns_upload_id_on_success | OK   PASS | 15 |
| upload_raises_on_api_error | OK   PASS | 16 |
| upload_out_of_range_raises_helpful_msg | OK   PASS | 15 |
### Search Scenes
| Test | Status | ms |
|------|--------|----|
| search_returns_data_dict | OK   PASS | 0 |
| search_payload_shp_upload_id | OK   PASS | 0 |
| search_payload_null_time_fields | OK   PASS | 0 |
| search_payload_cloud_max | OK   PASS | 15 |
| search_raises_on_api_error | OK   PASS | 0 |
### Download & Georeference
| Test | Status | ms |
|------|--------|----|
| download_creates_jpg_jgw_prj | OK   PASS | 15 |
| jgw_has_six_float_lines | OK   PASS | 0 |
| prj_contains_wgs84 | OK   PASS | 15 |
| download_returns_false_on_404 | OK   PASS | 0 |
### Version Probe
| Test | Status | ms |
|------|--------|----|
| uniform_204_falls_back_to_v5 | OK   PASS | 16 |
| version_in_config_skips_probe | OK   PASS | 0 |
### AOIHandler
| Test | Status | ms |
|------|--------|----|
| load_geojson_returns_polygon | OK   PASS | 93 |
| load_kml_returns_polygon | OK   PASS | 0 |
| load_shapefile_zip_returns_polygon | OK   PASS | 78 |
| unsupported_format_returns_none | OK   PASS | 46 |
| calculate_area_polygon_positive | OK   PASS | 0 |
| calculate_area_none_returns_zero | OK   PASS | 0 |
### map_utils
| Test | Status | ms |
|------|--------|----|
| normalize_longitude_overflow_positive | OK   PASS | 0 |
| normalize_longitude_overflow_negative | OK   PASS | 0 |
| normalize_longitude_at_180 | OK   PASS | 0 |
| normalize_longitude_normal_values | OK   PASS | 0 |
| split_no_cross | OK   PASS | 0 |
| split_empty_polygon | OK   PASS | 0 |
| split_regular_polygon_valid | OK   PASS | 0 |
| split_spanning_180_normalised | OK   PASS | 0 |
| handle_drawing_valid_polygon | OK   PASS | 0 |
| handle_drawing_empty_dict | OK   PASS | 0 |
| handle_drawing_none | OK   PASS | 0 |
| handle_drawing_wrong_geometry_type | OK   PASS | 0 |
### search_logic / run_search
| Test | Status | ms |
|------|--------|----|
| sets_features_for_map | OK   PASS | 15 |
| sets_scenes_for_download | OK   PASS | 16 |
| paginates_until_total | OK   PASS | 15 |
| stops_on_empty_page | OK   PASS | 0 |
| skips_scene_with_invalid_boundary | OK   PASS | 15 |
| rewrites_quickview_domain | OK   PASS | 16 |
| no_scenes_leaves_state_clean | OK   PASS | 0 |
### search_logic / create_download_zip
| Test | Status | ms |
|------|--------|----|
| preserves_features_for_map | OK   PASS | 15 |
| skips_when_no_scenes | OK   PASS | 0 |
| skips_when_button_not_clicked | OK   PASS | 0 |
### Logging helpers
| Test | Status | ms |
|------|--------|----|
| log_search_writes_correct_fields | OK   PASS | 15 |
| log_search_appends_multiple | OK   PASS | 15 |
| log_aoi_upload_writes_correct_fields | OK   PASS | 15 |
| structured_log_appends_jsonl | OK   PASS | 16 |
