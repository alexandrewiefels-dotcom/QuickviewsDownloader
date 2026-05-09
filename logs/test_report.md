# SASClouds Scraper — Test Report
Generated: 2026-05-08 18:44:33  |  Live tests: yes

## Summary
| Status | Count |
|--------|-------|
| ✓ PASS  | 82 |
| ✗ FAIL  | 0 |
| ! ERROR | 0 |
| ~ SKIP  | 0 |
| **Total** | **82** |

Total elapsed: 23.3s

---
## Full Results by Category

### Config & Paths
| Test | Status | ms |
|------|--------|----|
| config_json_exists | OK   PASS | 0 |
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
| creates_three_sidecar_files | OK   PASS | 421 |
| all_three_files_nonempty | OK   PASS | 16 |
| outer_ring_is_clockwise | OK   PASS | 16 |
| simplifies_dense_polygon | OK   PASS | 0 |
| rejects_empty_feature_collection | OK   PASS | 15 |
### Upload AOI
| Test | Status | ms |
|------|--------|----|
| upload_sends_single_file_field | OK   PASS | 15 |
| upload_shp_is_clockwise | OK   PASS | 15 |
| upload_returns_upload_id_on_success | OK   PASS | 16 |
| upload_raises_on_api_error | OK   PASS | 16 |
| upload_out_of_range_raises_helpful_msg | OK   PASS | 14 |
### Search Scenes
| Test | Status | ms |
|------|--------|----|
| search_returns_data_dict | OK   PASS | 0 |
| search_payload_shp_upload_id | OK   PASS | 0 |
| search_payload_null_time_fields | OK   PASS | 0 |
| search_payload_cloud_max | OK   PASS | 16 |
| search_raises_on_api_error | OK   PASS | 0 |
### Download & Georeference
| Test | Status | ms |
|------|--------|----|
| download_creates_jpg_jgw_prj | OK   PASS | 16 |
| jgw_has_six_float_lines | OK   PASS | 15 |
| prj_contains_wgs84 | OK   PASS | 15 |
| download_returns_false_on_404 | OK   PASS | 15 |
### Version Probe
| Test | Status | ms |
|------|--------|----|
| uniform_204_falls_back_to_v5 | OK   PASS | 16 |
| version_in_config_skips_probe | OK   PASS | 0 |
### AOIHandler
| Test | Status | ms |
|------|--------|----|
| load_geojson_returns_polygon | OK   PASS | 108 |
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
| sets_features_for_map | OK   PASS | 16 |
| sets_scenes_for_download | OK   PASS | 0 |
| paginates_until_total | OK   PASS | 16 |
| stops_on_empty_page | OK   PASS | 14 |
| skips_scene_with_invalid_boundary | OK   PASS | 16 |
| rewrites_quickview_domain | OK   PASS | 0 |
| no_scenes_leaves_state_clean | OK   PASS | 16 |
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
| log_aoi_upload_writes_correct_fields | OK   PASS | 16 |
| structured_log_appends_jsonl | OK   PASS | 16 |
### Live API
| Test | Status | ms |
|------|--------|----|
| homepage_reachable | OK   PASS | 1796 |
| upload_vietnam_aoi | OK   PASS | 1280 |
| search_returns_scenes | OK   PASS | 3859 |
| quickview_cdn_url_accessible | OK   PASS | 3000 |
### Quickview Diagnostic
| Test | Status | ms |
|------|--------|----|
| p1_get_real_quickview_url | OK   PASS | 2890 |
| p1_fetch_bare_no_headers | OK   PASS | 2359 |
| p1_fetch_with_referer | OK   PASS | 1875 |
| p1_fetch_with_browser_headers | OK   PASS | 2265 |
| p2_fetch_image_b64_returns_nonempty | OK   PASS | 2297 |
| p2_data_uri_has_correct_prefix | OK   PASS | 0 |
| p2_image_content_is_valid_jpeg | OK   PASS | 14 |
| p2_image_size_is_reasonable | OK   PASS | 0 |
| p3_warp_layer_class_in_header | OK   PASS | 94 |
| p3_instantiation_in_html | OK   PASS | 93 |
| p3_image_data_embedded_in_html | OK   PASS | 109 |
| p3_corners_json_is_valid | OK   PASS | 93 |
| p3_map_variable_name_consistent | OK   PASS | 108 |
| p3_class_defined_before_instantiation | OK   PASS | 110 |
| p4_order_corners_returns_four_points | OK   PASS | 0 |
| p4_corners_span_nonzero_area | OK   PASS | 14 |
| p4_corners_are_latlon_not_lonlat | OK   PASS | 0 |
