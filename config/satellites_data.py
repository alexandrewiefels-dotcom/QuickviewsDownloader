"""
Satellite data definitions — extracted from config/satellites.py.

Contains the raw satellite lists organized by constellation/provider.
The _create_satellite helper is in config/satellites_common.py.
"""

from config.satellites_common import _create_satellite

JILIN_SATELLITES = [
    # ============== KUANFU (KF) SERIES – Wide swath optical ==============
    _create_satellite(
        norad=45016, name="JL1KF 01 (75cm)", provider="JILIN", sat_type="Optical",
        series="KF 75cm", launch="2020-01-15", alt_name="EC1",
        cameras={"Wide (0.75m)": {"swath_km": 136, "resolution_m": 0.75}},
        period_min=95.35, inclination=97.507, color="#9370DB"
    ),
    _create_satellite(
        norad=49003, name="JL1KF 01B", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2021-07-03", alt_name="EC2",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.90, inclination=97.522, color="#9370DB"
    ),
    _create_satellite(
        norad=52443, name="JL1KF 01C", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2022-05-05", alt_name="EC3",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=95.10, inclination=97.527, color="#9370DB"
    ),
    _create_satellite(
        norad=57696, name="JL1KF 02A", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-01-11", alt_name="SL1",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.95, inclination=97.56, color="#9370DB"
    ),
    _create_satellite(
        norad=61189, name="JL1KF 02B 1", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-08-16", alt_name="EC4",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.93, inclination=97.53, color="#9370DB"
    ),
    _create_satellite(
        norad=61190, name="JL1KF 02B 2", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-08-16", alt_name="EC5",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.92, inclination=97.53, color="#9370DB"
    ),
    _create_satellite(
        norad=61191, name="JL1KF 02B 3", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-08-16", alt_name="EC6",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.94, inclination=97.53, color="#9370DB"
    ),
    _create_satellite(
        norad=61192, name="JL1KF 02B 4", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-08-16", alt_name="EC7",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.91, inclination=97.53, color="#9370DB"
    ),
    _create_satellite(
        norad=61193, name="JL1KF 02B 5", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-08-16", alt_name="EC8",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.93, inclination=97.53, color="#9370DB"
    ),
    _create_satellite(
        norad=61194, name="JL1KF 02B 6", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2024-08-16", alt_name="EC9",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.92, inclination=97.53, color="#9370DB"
    ),
    _create_satellite(
        norad=66997, name="JL1KF 02B 7", provider="JILIN", sat_type="Optical",
        series="KF 50cm", launch="2026-01-20", alt_name="EC10",
        cameras={"Wide (0.5m)": {"swath_km": 150, "resolution_m": 0.5}},
        period_min=94.94, inclination=97.53, color="#9370DB"
    ),

    # ============== GF-02 SERIES – Video satellites ==============
    _create_satellite(
        norad=44713, name="JL1GF02A", provider="JILIN", sat_type="Optical (Video)",
        series="GF-02", launch="2018-12-22", alt_name="DW1",
        cameras={"Video (0.9m)": {"swath_km": 19, "resolution_m": 0.9}},
        period_min=95.06, inclination=97.50, color="#FFA500"
    ),
    _create_satellite(
        norad=44836, name="JL1GF02B", provider="JILIN", sat_type="Optical (Video)",
        series="GF-02", launch="2019-01-21", alt_name="DW2",
        cameras={"Video (0.9m)": {"swath_km": 19, "resolution_m": 0.9}},
        period_min=95.21, inclination=97.490, color="#FFA500"
    ),
    _create_satellite(
        norad=49255, name="JL1GF02D", provider="JILIN", sat_type="Optical (Video)",
        series="GF-02", launch="2021-09-27", alt_name="DW3",
        cameras={"Video (0.9m)": {"swath_km": 19, "resolution_m": 0.9}},
        period_min=95.15, inclination=97.52, color="#FFA500"
    ),
    _create_satellite(
        norad=49338, name="JL1GF02F", provider="JILIN", sat_type="Optical (Video)",
        series="GF-02", launch="2021-09-27", alt_name="DW4",
        cameras={"Video (0.9m)": {"swath_km": 19, "resolution_m": 0.9}},
        period_min=95.07, inclination=97.662, color="#FFA500"
    ),

    # ============== EARLY OPTICAL SERIES ==============
    _create_satellite(
        norad=40958, name="JL101A (Optical-A)", provider="JILIN", sat_type="Optical",
        series="Jilin-1", launch="2015-10-07", alt_name="DV85",
        cameras={"High Res (0.7m)": {"swath_km": 11, "resolution_m": 0.7}},
        period_min=97.50, inclination=97.668, color="#9370DB"
    ),
    _create_satellite(
        norad=40961, name="JL1GF03A", provider="JILIN", sat_type="Optical",
        series="GF-03 0.7m", launch="2015-10-07", alt_name="DV1-00",
        cameras={"VHR (0.7m)": {"swath_km": 11, "resolution_m": 0.7}},
        period_min=97.65, inclination=97.652, color="#9370DB"
    ),

    # ============== GF-03B SERIES ==============
    _create_satellite(
        norad=46454, name="JL1GF 03B 01", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 1m", launch="2020-09-15", alt_name="DV1-01",
        cameras={"Night (1m)": {"swath_km": 17, "resolution_m": 1.0}},
        period_min=94.47, inclination=97.36, color="#FFA500"
    ),
    _create_satellite(
        norad=46455, name="JL1GF 03B 02", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 1m", launch="2020-09-15", alt_name="DV1-02",
        cameras={"Night (1m)": {"swath_km": 17, "resolution_m": 1.0}}
    ),
    _create_satellite(
        norad=46456, name="JL1GF 03B 03", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 1m", launch="2020-09-15", alt_name="DV1-03",
        cameras={"Night (1m)": {"swath_km": 17, "resolution_m": 1.0}}
    ),
    _create_satellite(
        norad=46460, name="JL1GF 03B 04", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 1m", launch="2020-09-15", alt_name="DV1-04",
        cameras={"Night (1m)": {"swath_km": 17, "resolution_m": 1.0}}
    ),
    _create_satellite(
        norad=46461, name="JL1GF 03B 05", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 1m", launch="2020-09-15", alt_name="DV1-05",
        cameras={"Night (1m)": {"swath_km": 17, "resolution_m": 1.0}}
    ),
    _create_satellite(
        norad=46462, name="JL1GF 03B 06", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 1m", launch="2020-09-15", alt_name="DV1-06",
        cameras={"Night (1m)": {"swath_km": 17, "resolution_m": 1.0}}
    ),

    # ============== GF-03C SERIES ==============
    _create_satellite(
        norad=46457, name="JL1GF 03C 01", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 Night 1.2m", launch="2020-09-15", alt_name="NV09",
        cameras={"Night (1.2m)": {"swath_km": 14, "resolution_m": 1.2}}
    ),
    _create_satellite(
        norad=46458, name="JL1GF 03C 02", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 Night 1.2m", launch="2020-09-15", alt_name="NV10",
        cameras={"Night (1.2m)": {"swath_km": 14, "resolution_m": 1.2}}
    ),
    _create_satellite(
        norad=46459, name="JL1GF 03C 03", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03 Night 1.2m", launch="2020-09-15", alt_name="NV11",
        cameras={"Night (1.2m)": {"swath_km": 14, "resolution_m": 1.2}}
    ),

    # ============== GF-03D SERIES (DV1 – DV54) ==============
    # Partial list – full series available in original source
    _create_satellite(
        norad=49004, name="JL1GF03D01", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2021-07-03", alt_name="DV1",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=49005, name="JL1GF03D02", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2021-07-03", alt_name="DV2",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=49006, name="JL1GF03D03", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2021-07-03", alt_name="DV3",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
    norad=52389, name="JL1GF03D04", provider="JILIN", sat_type="Optical (Video)",
    series="GF-03", launch="2022-04-30", alt_name="DV4",
    cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}},
    period_min=94.5, inclination=97.5, color="#FFA500"
    ),
    _create_satellite(
        norad=52390, name="JL1GF03D05", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-04-30", alt_name="DV5",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=52391, name="JL1GF03D06", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-04-30", alt_name="DV6",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=52392, name="JL1GF03D07", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-04-30", alt_name="DV7",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV8 – DV9 (launched 2022-05-05)
    _create_satellite(
        norad=52444, name="JL1GF03D08", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-05-05", alt_name="DV8",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=52445, name="JL1GF03D09", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-05-05", alt_name="DV9",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV10 – DV18 (launched 2022-02-27)
    _create_satellite(
        norad=51834, name="JL1GF03D10", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV10",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51835, name="JL1GF03D11", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV11",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51836, name="JL1GF03D12", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV12",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51837, name="JL1GF03D13", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV13",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51838, name="JL1GF03D14", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV14",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51839, name="JL1GF03D15", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV15",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51840, name="JL1GF03D16", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV16",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51841, name="JL1GF03D17", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV17",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=51842, name="JL1GF03D18", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-02-27", alt_name="DV18",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV19 – DV26 (launched 2023-12-09)
    _create_satellite(
        norad=57004, name="JL1GF03D19", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV19",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57005, name="JL1GF03D20", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV20",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57006, name="JL1GF03D21", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV21",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57007, name="JL1GF03D22", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV22",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57008, name="JL1GF03D23", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV23",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57009, name="JL1GF03D24", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV24",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57010, name="JL1GF03D25", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV25",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=57011, name="JL1GF03D26", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-12-09", alt_name="DV26",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV27 – DV29 (launched 2023-01-15)
    _create_satellite(
        norad=53457, name="JL1GF03D27", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV27",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=53458, name="JL1GF03D28", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV28",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=53459, name="JL1GF03D29", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV29",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV30 – DV33 (launched 2022-05-05)
    _create_satellite(
        norad=52447, name="JL1GF03D30", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-05-05", alt_name="DV30",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=52448, name="JL1GF03D31", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-05-05", alt_name="DV31",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=52449, name="JL1GF03D32", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-05-05", alt_name="DV32",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=52450, name="JL1GF03D33", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2022-05-05", alt_name="DV33",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV34 – DV36 (launched 2023-06-15)
    _create_satellite(
        norad=54252, name="JL1GF03D34", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV34",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54253, name="DP01 (03D35)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV35",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54254, name="DP02 (03D36)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV36",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV37 – DV41 (launched 2023-01-15)
    _create_satellite(
        norad=53460, name="DP03 (03D37)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV37",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=53461, name="DP04 (03D38)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV38",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=53462, name="DP05 (03D39)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV39",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=53463, name="DP06 (03D40)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV40",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=53464, name="DP07 (03D41)", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-01-15", alt_name="DV41",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV42 – DV43 (launched 2023-08-10)
    _create_satellite(
        norad=54682, name="JL1GF03D42", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-08-10", alt_name="DV42",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54683, name="JL1GF03D43", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-08-10", alt_name="DV43",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV47 – DV50 (launched 2023-08-10)
    _create_satellite(
        norad=54687, name="JL1GF03D47", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-08-10", alt_name="DV47",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54688, name="JL1GF03D48", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-08-10", alt_name="DV48",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54689, name="JL1GF03D49", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-08-10", alt_name="DV49",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54690, name="JL1GF03D50", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-08-10", alt_name="DV50",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # DV51 – DV54 (launched 2023-06-15)
    _create_satellite(
        norad=54255, name="JL1GF03D51", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV51",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54256, name="JL1GF03D52", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV52",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54257, name="JL1GF03D53", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV53",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    _create_satellite(
        norad=54258, name="JL1GF03D54", provider="JILIN", sat_type="Optical (Video)",
        series="GF-03", launch="2023-06-15", alt_name="DV54",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),

    # ============== GF-04 (Optical VHR) ==============
    _create_satellite(
        norad=52388, name="JL1GF 04A", provider="JILIN", sat_type="Optical",
        series="GF-04", launch="2022-04-30", alt_name="SL1",
        cameras={"VHR (0.5m)": {"swath_km": 15, "resolution_m": 0.5}},
        period_min=95.42, inclination=97.44, color="#00CED1"
    ),

    # ============== GF-06A SERIES (DV55 – DV84) ==============
    _create_satellite(
        norad=57012, name="JL1GF06A01", provider="JILIN", sat_type="Optical (Video)",
        series="GF-06", launch="2023-12-09", alt_name="DV55",
        cameras={"Video (0.75m)": {"swath_km": 17, "resolution_m": 0.75}}
    ),
    # ... (remaining DV56–DV84 follow the same pattern)

    # ============== GF-07 SERIES (Optical VHR) ==============
    _create_satellite(
        norad=66996, name="JL1GF 07A", provider="JILIN", sat_type="Optical",
        series="GF-07", launch="2026-01-20",
        cameras={"VHR (0.5m)": {"swath_km": 15, "resolution_m": 0.5}},
        period_min=95.40, inclination=97.45, color="#00CED1"
    ),
    _create_satellite(
        norad=66993, name="JL1GF 07B", provider="JILIN", sat_type="Optical",
        series="GF-07", launch="2026-01-20",
        cameras={"VHR (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=66995, name="JL1GF 07C", provider="JILIN", sat_type="Optical",
        series="GF-07", launch="2026-01-20",
        cameras={"VHR (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=66994, name="JL1GF 07D", provider="JILIN", sat_type="Optical",
        series="GF-07", launch="2026-01-20",
        cameras={"VHR (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),

    # ============== JILIN-GP (Multispectral) ==============
    _create_satellite(
        norad=61236, name="JL1GP01", provider="JILIN", sat_type="Optical",
        series="Jilin-GP", launch="2024-09-24", alt_name="HS1",
        cameras={"Multispectral (2m)": {"swath_km": 50, "resolution_m": 2}},
        color="#00FF00"
    ),
    _create_satellite(
        norad=61237, name="JL1GP02", provider="JILIN", sat_type="Optical",
        series="Jilin-GP", launch="2024-09-24", alt_name="HS2",
        cameras={"Multispectral (2m)": {"swath_km": 50, "resolution_m": 2}}
    ),

    # ============== JILIN-B (High Res Optical) ==============
    _create_satellite(
        norad=61234, name="JL103B", provider="JILIN", sat_type="Optical",
        series="Jilin-B", launch="2024-09-24", alt_name="NV03",
        cameras={"High Res (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=61235, name="JL104B", provider="JILIN", sat_type="Optical",
        series="Jilin-B", launch="2024-09-24", alt_name="NV04",
        cameras={"High Res (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=62337, name="JL105B", provider="JILIN", sat_type="Optical",
        series="Jilin-B", launch="2024-12-16", alt_name="NV05",
        cameras={"High Res (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=62338, name="JL106B", provider="JILIN", sat_type="Optical",
        series="Jilin-B", launch="2024-12-16", alt_name="NV06",
        cameras={"High Res (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=62339, name="JL107B", provider="JILIN", sat_type="Optical",
        series="Jilin-B", launch="2024-12-16", alt_name="NV07",
        cameras={"High Res (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),
    _create_satellite(
        norad=62340, name="JL108B", provider="JILIN", sat_type="Optical",
        series="Jilin-B", launch="2024-12-16", alt_name="NV08",
        cameras={"High Res (0.5m)": {"swath_km": 15, "resolution_m": 0.5}}
    ),

    # ============== JILIN-1 SAR ==============
    _create_satellite(
        norad=61240, name="JL1 SAR-01A", provider="JILIN", sat_type="SAR",
        series="Jilin-SAR", launch="2024-09-24",
        cameras={
            "Spotlight (X-band)": {"swath_km": 5, "resolution_m": 1},
            "Stripmap (X-band)": {"swath_km": 20, "resolution_m": 3},
            "ScanSAR (X-band)": {"swath_km": 100, "resolution_m": 15}
        },
        period_min=94.91, inclination=97.48, color="#FF4500"
    ),
]

# -----------------------------------------------------------------------------
# CHINESE SAR & OPTICAL CONSTELLATIONS
# -----------------------------------------------------------------------------


CHINESE_SAR_OPTICAL = [
    # ============== GAOFEN-3 SERIES – C‑band SAR ==============
    _create_satellite(
        norad=41727, name="Gaofen-3 01", provider="CNSA", sat_type="SAR",
        series="Gaofen-3", launch="2016-08-10",
        cameras={
            "Sliding Spotlight": {"swath_km": 10, "resolution_m": 1},
            "Ultra-fine Stripmap": {"swath_km": 30, "resolution_m": 3},
            "Fine Stripmap": {"swath_km": 100, "resolution_m": 8},
            "Standard Stripmap": {"swath_km": 130, "resolution_m": 25},
            "Wide Swath Stripmap": {"swath_km": 250, "resolution_m": 50},
            "Narrow ScanSAR": {"swath_km": 300, "resolution_m": 100},
            "Wide ScanSAR": {"swath_km": 500, "resolution_m": 50},
            "Global Mode": {"swath_km": 650, "resolution_m": 500},
            "Wave Mode": {"swath_km": 50, "resolution_m": 10}
        },
        period_min=99.846, inclination=98.413, color="#FF4500",
        description="12 imaging modes, world's most abundant SAR modes"
    ),
    _create_satellite(
        norad=49495, name="Gaofen-3 02", provider="CNSA", sat_type="SAR",
        series="Gaofen-3", launch="2021-11-23",
        cameras={
            "Sliding Spotlight": {"swath_km": 10, "resolution_m": 1},
            "Ultra-fine Stripmap": {"swath_km": 30, "resolution_m": 3},
            "Fine Stripmap": {"swath_km": 100, "resolution_m": 8},
            "Standard Stripmap": {"swath_km": 130, "resolution_m": 25},
            "Wide ScanSAR": {"swath_km": 500, "resolution_m": 50}
        },
        period_min=99.84, inclination=98.41, color="#FF4500"
    ),
    _create_satellite(
        norad=52200, name="Gaofen-3 03", provider="CNSA", sat_type="SAR",
        series="Gaofen-3", launch="2022-04-07",
        cameras={
            "Sliding Spotlight": {"swath_km": 10, "resolution_m": 1},
            "Ultra-fine Stripmap": {"swath_km": 30, "resolution_m": 3},
            "Standard Stripmap": {"swath_km": 130, "resolution_m": 25},
            "Wide ScanSAR": {"swath_km": 500, "resolution_m": 50}
        },
        period_min=99.85, inclination=98.41, color="#FF4500"
    ),

    # ============== HAIYANG SERIES – Ocean observation ==============
    _create_satellite(
        norad=43655, name="Haiyang-2B", provider="CNSA", sat_type="SAR",
        series="Haiyang", launch="2018-10-25",
        cameras={"Radar Altimeter (Ku-band)": {"swath_km": 40, "resolution_m": 5}},
        period_min=104.400, inclination=99.333, color="#FF4500"
    ),
    _create_satellite(
        norad=46469, name="Haiyang-2C", provider="CNSA", sat_type="SAR",
        series="Haiyang", launch="2020-09-21",
        cameras={"Radar Altimeter (Ku-band)": {"swath_km": 40, "resolution_m": 5}},
        period_min=104.093, inclination=65.985, color="#FF4500"
    ),
    _create_satellite(
        norad=48621, name="Haiyang-2D", provider="CNSA", sat_type="SAR",
        series="Haiyang", launch="2021-05-19",
        cameras={"Radar Altimeter (Ku-band)": {"swath_km": 40, "resolution_m": 5}},
        period_min=104.093, inclination=65.998, color="#FF4500"
    ),
    _create_satellite(
        norad=58349, name="Haiyang-3A", provider="CNSA", sat_type="SAR",
        series="Haiyang", launch="2023-11-16",
        cameras={"SAR (Ku-band)": {"swath_km": 50, "resolution_m": 5}},
        period_min=100.20, inclination=98.80, color="#FF4500"
    ),
    _create_satellite(
        norad=61936, name="Haiyang-4A", provider="CNSA", sat_type="SAR",
        series="Haiyang", launch="2024-11-15",
        cameras={"SAR (Ku-band)": {"swath_km": 50, "resolution_m": 5}},
        period_min=100.25, inclination=98.82, color="#FF4500"
    ),

    # ============== HONGTU-1 / PIESAT-1 – X‑band SAR ==============
    _create_satellite(
        norad=56153, name="Hongtu-1 01 (PIESAT-1 01)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-1", launch="2023-03-30",
        cameras={
            "Spot": {"swath_km": 5, "resolution_m": 1},
            "Stripmap": {"swath_km": 30, "resolution_m": 3},
            "ScanSAR": {"swath_km": 100, "resolution_m": 12}
        },
        period_min=94.72, inclination=97.44, color="#FF4500"
    ),
    _create_satellite(
        norad=56154, name="Hongtu-1 02 (PIESAT-1 02)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-1", launch="2023-03-30",
        cameras={"Spot": {"swath_km": 5, "resolution_m": 1}, 
                 "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                 "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=94.72, inclination=97.44, color="#FF4500"
    ),
    _create_satellite(
        norad=56155, name="Hongtu-1 03 (PIESAT-1 03)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-1", launch="2023-03-30",
        cameras={"Spot": {"swath_km": 5, "resolution_m": 1}, 
                 "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                 "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=94.73, inclination=97.44, color="#FF4500"
    ),
    _create_satellite(
        norad=56156, name="Hongtu-1 04 (PIESAT-1 04)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-1", launch="2023-03-30",
        cameras={"Spot": {"swath_km": 5, "resolution_m": 1}, 
                 "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                 "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=94.73, inclination=97.44, color="#FF4500"
    ),

    # ============== HONGTU-2 / PIESAT-2 – X‑band SAR ==============
    _create_satellite(
        norad=61869, name="Hongtu-2 01 (PIESAT-2 01)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-11-09",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},
                "Stripmap": {"swath_km": 30, "resolution_m": 3},
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}
        },
        period_min=95.10, inclination=97.49, color="#FF4500"
    ),
    _create_satellite(
        norad=61870, name="Hongtu-2 02 (PIESAT-2 02)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-11-09",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                
                "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=95.15, inclination=97.49, color="#FF4500"
    ),
    _create_satellite(
        norad=61871, name="Hongtu-2 03 (PIESAT-2 03)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-11-09",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                 
                "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=95.12, inclination=97.49, color="#FF4500"
    ),
    _create_satellite(
        norad=61872, name="Hongtu-2 04 (PIESAT-2 04)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-11-09",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                 
                "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=95.14, inclination=97.49, color="#FF4500"
    ),
    _create_satellite(
        norad=62333, name="Hongtu-2 09 (PIESAT-2 09)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-12-16",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                 
                "Stripmap": {"swath_km": 30, "resolution_m": 3},
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}
        },
        period_min=95.11, inclination=97.52, color="#FF4500"
    ),
    _create_satellite(
        norad=62334, name="Hongtu-2 10 (PIESAT-2 10)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-12-16",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                 
                "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=95.12, inclination=97.52, color="#FF4500"
    ),
    _create_satellite(
        norad=62335, name="Hongtu-2 11 (PIESAT-2 11)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-12-16",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                 
                "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=95.10, inclination=97.51, color="#FF4500"
    ),
    _create_satellite(
        norad=62336, name="Hongtu-2 12 (PIESAT-2 12)", provider="PIESAT", sat_type="SAR",
        series="PIESAT-2", launch="2024-12-16",
        cameras={
                "Sliding Spotlight 1": {"swath_km": 5, "resolution_m": 0.5},
                "Sliding Spotlight 2": {"swath_km": 10, "resolution_m": 1},                 
                "Stripmap": {"swath_km": 30, "resolution_m": 3}, 
                "ScanSAR": {"swath_km": 100, "resolution_m": 12}},
        period_min=95.11, inclination=97.52, color="#FF4500"
    ),
        
    # ============== SPACETY SERIES – MULTIPLE BANDS & MODES ==============
    # SPACETY CSAT

    _create_satellite(
       norad=51843, name="C-SAT 02 Chaohu-1", provider="Spacety", sat_type="SAR",
       series="C-SAT", launch="2022-02-27", alt_name="TY-MINISAR-02", 
       cameras={
           "Spotlight (C-band)": {"swath_km": 10, "resolution_m": 0.5},
           "Stripmap (C-band)": {"swath_km": 35, "resolution_m": 3.0},
           "ScanSAR (C-band)": {"swath_km": 100, "resolution_m": 20.0}
       },
       period_min=95.10, inclination=97.39, altitude=525, color="#5F9EA0"
    ),
    _create_satellite(
       norad=56849, name="C-SAT 03 Fucheng-1", provider="Spacety", sat_type="SAR", 
       series="C-SAT", launch="2023-06-07", alt_name="TY-MINISAR-03", 
       cameras={
           "Spotlight (C-band)": {"swath_km": 10, "resolution_m": 0.5},
           "Stripmap (C-band)": {"swath_km": 35, "resolution_m": 3.0},
           "ScanSAR (C-band)": {"swath_km": 100, "resolution_m": 20.0}
       },
       period_min=95.22, inclination=97.51, altitude=530, color="#5F9EA0"
    ),
    _create_satellite(
       norad=62190, name="C-SAT 04 Haishao-1", provider="Spacety", sat_type="SAR", 
       series="C-SAT", launch="2024-12-04", alt_name="TY-MINISAR-04", 
       cameras={
           "Spotlight (C-band)": {"swath_km": 10, "resolution_m": 0.5},
           "Stripmap (C-band)": {"swath_km": 35, "resolution_m": 3.0},
           "ScanSAR (C-band)": {"swath_km": 100, "resolution_m": 20.0}
       },
       period_min=94.50, inclination=43.00, altitude=495, color="#5F9EA0"
    ),
    _create_satellite(
        norad=59912, name="C-SAT 05 Shenqi-1", provider="Spacety", sat_type="SAR (InSAR)",
        series="C-SAT", launch="2024-05-29", alt_name="Tianyi-28", 
        cameras={
            "Spotlight (C-band)": {"swath_km": 10, "resolution_m": 0.5},
            "Stripmap (C-band)": {"swath_km": 35, "resolution_m": 3.0},
          #  "InSAR Mode": {"revisit_days": 3.5, "precision": "millimeter-level"}
        },
        period_min=103.1, inclination=45.00, altitude=900, 
        color="#FF8C00"
    ),
    # ============== AIRSAT SERIES – MULTIPLE BANDS & MODES ==============
    # AIRSAT-01/02 : Ku‑band, single polarization (HH)
    _create_satellite(
        norad=56157, name="AIRSAT-01 (Hongtu-2 A-01)", provider="PIESAT", sat_type="SAR",
        series="AIRSAT", launch="2023-03-30",
        cameras={
            "Spotlight (Ku-band)": {"swath_km": 5, "resolution_m": 0.5},
            "Stripmap (Ku-band)": {"swath_km": 30, "resolution_m": 3},
            "ScanSAR (Ku-band)": {"swath_km": 100, "resolution_m": 15}
        },
        period_min=94.72, inclination=97.44, color="#FF4500"
    ),
    _create_satellite(
        norad=56158, name="AIRSAT-02 (Hongtu-2 A-02)", provider="PIESAT", sat_type="SAR",
        series="AIRSAT", launch="2023-03-30",
        cameras={
            "Spotlight (Ku-band)": {"swath_km": 5, "resolution_m": 0.5},
            "Stripmap (Ku-band)": {"swath_km": 30, "resolution_m": 3},
            "ScanSAR (Ku-band)": {"swath_km": 100, "resolution_m": 15}
        },
        period_min=94.72, inclination=97.44, color="#FF4500"
    ),
    # AIRSAT-05 : Ku‑band experimental
    _create_satellite(
        norad=59124, name="AIRSAT-05 (Hongtu-2 B-01)", provider="PIESAT", sat_type="SAR",
        series="AIRSAT", launch="2024-03-21",
        cameras={
            "Ku-Spot": {"swath_km": 3, "resolution_m": 0.3},
            "Ku-Strip": {"swath_km": 15, "resolution_m": 1.5},
            "Ku-Scan": {"swath_km": 40, "resolution_m": 5}
        },
        period_min=94.97, inclination=97.45, color="#FF4500"
    ),
    # AIRSAT-06/07 : Optical (Pan + MS)
    _create_satellite(
        norad=60245, name="AIRSAT-06 (Hongtu-2 C-01)", provider="PIESAT", sat_type="Optical",
        series="AIRSAT", launch="2024-07-10",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.5},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 2.0}
        },
        period_min=94.91, inclination=97.48, color="#00CED1"
    ),
    _create_satellite(
        norad=60246, name="AIRSAT-07 (Hongtu-2 C-02)", provider="PIESAT", sat_type="Optical",
        series="AIRSAT", launch="2024-07-10",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.5},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 2.0}
        },
        period_min=94.92, inclination=97.48, color="#00CED1"
    ),
    # AIRSAT-08 : Hybrid (SAR + Optical)
    _create_satellite(
        norad=61834, name="AIRSAT-08 (Hongtu-2 D-01)", provider="PIESAT", sat_type="Hybrid (SAR/Opt)",
        series="AIRSAT", launch="2024-11-09",
        cameras={
            "Sliding-Spot (X-band)": {"swath_km": 8, "resolution_m": 0.5},
            "Stripmap (X-band)": {"swath_km": 10, "resolution_m": 1.0},
            "Scan-Med (X-band)": {"swath_km": 40, "resolution_m": 5.0},
            "Optical-Context (RGB)": {"swath_km": 90, "resolution_m": 12.0}
        },
        period_min=95.09, inclination=97.49, color="#FFA500"
    ),

    # ============== LUTAN-1 SERIES – L‑band SAR ==============
    _create_satellite(
        norad=51284, name="Lutan-1A (LT-1A)", provider="CNSA", sat_type="SAR",
        series="Lutan-1", launch="2022-01-26",
        cameras={
            "Stripmap (L-band)": {"swath_km": 30, "resolution_m": 3},
            "ScanSAR (L-band)": {"swath_km": 400, "resolution_m": 30},
            "Spotlight (L-band)": {"swath_km": 15, "resolution_m": 1}
        },
        period_min=96.9, inclination=97.8, color="#FF4500",
        description="First Chinese L‑band SAR, quad-pol capability"
    ),
    _create_satellite(
        norad=51822, name="Lutan-1B (LT-1B)", provider="CNSA", sat_type="SAR",
        series="Lutan-1", launch="2022-02-27",
        cameras={
            "Stripmap (L-band)": {"swath_km": 30, "resolution_m": 3},
            "ScanSAR (L-band)": {"swath_km": 400, "resolution_m": 30},
            "Spotlight (L-band)": {"swath_km": 15, "resolution_m": 1}
        },
        period_min=96.9, inclination=97.8, color="#FF4500"
    ),

    # ============== TAIJING-4 SERIES – C/X‑band SAR ==============
    _create_satellite(
        norad=64087, name="Taijing-4 02A", provider="Taijing", sat_type="SAR",
        series="Taijing-4", launch="2025-12-01",
        cameras={"Stripmap (C/X-band)": {"swath_km": 25, "resolution_m": 3}},
        period_min=94.95, inclination=97.52, color="#FF4500"
    ),
    _create_satellite(
        norad=58822, name="Taijing-4 03", provider="Taijing", sat_type="SAR",
        series="Taijing-4", launch="2024-01-23",
        cameras={"Stripmap (C/X-band)": {"swath_km": 25, "resolution_m": 3}},
        period_min=94.98, inclination=97.51, color="#FF4500"
    ),

    # ============== GAOFEN-7 – Optical stereo ==============
    _create_satellite(
        norad=44703, name="Gaofen-7", provider="CNSA", sat_type="Optical (Stereo)",
        series="Gaofen-7", launch="2019-11-03",
        cameras={
            "Stereo (Panchromatic)": {"swath_km": 20, "resolution_m": 0.65},
            "Multispectral": {"swath_km": 20, "resolution_m": 3.2}
        },
        period_min=96.00, inclination=97.97, color="#00CED1"
    ),

    # ============== SUPERVIEW-1 (GAOJING-1) – High Res Optical ==============
    _create_satellite(
        norad=41907, name="Superview-1 01", provider="Siwei", sat_type="Optical",
        series="SuperView-1", launch="2016-12-28",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.5},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 2}
        },
        period_min=95.42, inclination=97.44, color="#00CED1"
    ),
    _create_satellite(
        norad=41908, name="Superview-1 02", provider="Siwei", sat_type="Optical",
        series="SuperView-1", launch="2016-12-28",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.5},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 2}
        },
        period_min=95.42, inclination=97.44, color="#00CED1"
    ),
    _create_satellite(
        norad=43099, name="Superview-1 03", provider="Siwei", sat_type="Optical",
        series="SuperView-1", launch="2018-01-09",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.5},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 2}
        },
        period_min=95.41, inclination=97.44, color="#00CED1"
    ),
    _create_satellite(
        norad=43100, name="Superview-1 04", provider="Siwei", sat_type="Optical",
        series="SuperView-1", launch="2018-01-09",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.5},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 2}
        },
        period_min=95.41, inclination=97.44, color="#00CED1"
    ),

    # ============== SUPERVIEW NEO-1 – 0.3m / 0.25m Optical ==============
    _create_satellite(
        norad=52320, name="SuperView Neo-1 01", provider="Siwei", sat_type="Optical",
        series="SuperView Neo-1", launch="2022-04-29",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.3},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 1.2}
        },
        period_min=97.20, inclination=97.45, color="#FF1493"
    ),
    _create_satellite(
        norad=52322, name="SuperView Neo-1 02", provider="Siwei", sat_type="Optical",
        series="SuperView Neo-1", launch="2022-04-29",
        cameras={
            "Panchromatic": {"swath_km": 15, "resolution_m": 0.3},
            "Multispectral (4-band)": {"swath_km": 15, "resolution_m": 1.2}
        },
        period_min=97.24, inclination=97.47, color="#FF1493"
    ),
    _create_satellite(
        norad=63125, name="SuperView Neo-1 03", provider="Siwei", sat_type="Optical",
        series="SuperView Neo-1", launch="2025-04-29",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.25},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 1.0}
        },
        period_min=97.18, inclination=97.46, color="#FF1493"
    ),
    _create_satellite(
        norad=63126, name="SuperView Neo-1 04", provider="Siwei", sat_type="Optical",
        series="SuperView Neo-1", launch="2025-04-29",
        cameras={
            "Panchromatic": {"swath_km": 12, "resolution_m": 0.25},
            "Multispectral (4-band)": {"swath_km": 12, "resolution_m": 1.0}
        },
        period_min=97.19, inclination=97.46, color="#FF1493"
    ),

    # ============== SUPERVIEW NEO-2 – X‑band SAR ==============
    _create_satellite(
        norad=53128, name="SuperView Neo-2 01", provider="Siwei", sat_type="SAR",
        series="SuperView Neo-2", launch="2022-12-09",
        cameras={"Spotlight (X-band)": {"swath_km": 15, "resolution_m": 0.5}},
        period_min=94.75, inclination=97.393, color="#FF4500"
    ),
    _create_satellite(
        norad=53130, name="SuperView Neo-2 02", provider="Siwei", sat_type="SAR",
        series="SuperView Neo-2", launch="2022-12-09",
        cameras={"Spotlight (X-band)": {"swath_km": 15, "resolution_m": 0.5}},
        period_min=94.74, inclination=97.394, color="#FF4500"
    ),
    _create_satellite(
        norad=63450, name="SuperView Neo-2 05", provider="Siwei", sat_type="SAR",
        series="SuperView Neo-2", launch="2025-10-15",
        cameras={
            "Spotlight (X-band)": {"swath_km": 15, "resolution_m": 0.5},
            "Stripmap (X-band)": {"swath_km": 50, "resolution_m": 3}
        },
        period_min=94.76, inclination=97.44, color="#FF4500"
    ),
    _create_satellite(
        norad=63451, name="SuperView Neo-2 06", provider="Siwei", sat_type="SAR",
        series="SuperView Neo-2", launch="2025-10-15",
        cameras={
            "Spotlight (X-band)": {"swath_km": 15, "resolution_m": 0.5},
            "Stripmap (X-band)": {"swath_km": 50, "resolution_m": 3}
        },
        period_min=94.75, inclination=97.44, color="#FF4500"
    ),

    # ============== SUPERVIEW NEO-3 – Wide Swath Optical ==============
    _create_satellite(
        norad=59510, name="SuperView Neo-3 01", provider="Siwei", sat_type="Optical",
        series="SuperView Neo-3", launch="2024-05-20",
        cameras={
            "Panchromatic": {"swath_km": 130, "resolution_m": 0.5},
            "Multispectral (9-band)": {"swath_km": 130, "resolution_m": 2.0}
        },
        period_min=94.74, inclination=97.46, color="#00CED1",
        description="First Chinese commercial 130km swath with 0.5m resolution"
    ),
    _create_satellite(
        norad=63208, name="SuperView Neo-3 02", provider="Siwei", sat_type="Optical",
        series="SuperView Neo-3", launch="2025-08-10",
        cameras={
            "Panchromatic": {"swath_km": 130, "resolution_m": 0.5},
            "Multispectral (9-band)": {"swath_km": 130, "resolution_m": 2.0}
        },
        period_min=94.73, inclination=97.45, color="#00CED1"
    ),
]

# -----------------------------------------------------------------------------
# OTHER SATELLITE CATEGORIES
# -----------------------------------------------------------------------------

# High Resolution Optical (Non‑Chinese)

HIGH_RES_OPTICAL = [
    _create_satellite(
        norad=35946, name="WorldView-1", provider="DigitalGlobe", sat_type="Optical",
        series="WorldView", launch=None,
        cameras={"Panchromatic": {"swath_km": 17.6, "resolution_m": 0.5}},
        period_min=94.2, inclination=97.8, color="#4169E1"
    ),
    _create_satellite(
        norad=38101, name="WorldView-2", provider="DigitalGlobe", sat_type="Optical",
        series="WorldView", launch=None,
        cameras={
            "Panchromatic": {"swath_km": 16.4, "resolution_m": 0.46},
            "Multispectral (8-band)": {"swath_km": 16.4, "resolution_m": 1.84}
        },
        period_min=94.2, inclination=97.8, color="#4169E1"
    ),
    _create_satellite(
        norad=33331, name="GeoEye-1", provider="DigitalGlobe", sat_type="Optical",
        series="GeoEye", launch=None,
        cameras={
            "Panchromatic": {"swath_km": 15.2, "resolution_m": 0.41},
            "Multispectral (4-band)": {"swath_km": 15.2, "resolution_m": 1.65}
        },
        period_min=98.0, inclination=98.1, color="#1E90FF"
    ),
]

# Medium Resolution Optical

MEDIUM_RES_OPTICAL = [
    _create_satellite(
        norad=40697, name="Sentinel-2A", provider="ESA", sat_type="Optical",
        series="Sentinel", launch=None,
        cameras={"MSI (13-band)": {"swath_km": 290, "resolution_m": 10}},
        period_min=100.6, inclination=98.57, color="#00FF00"
    ),
    _create_satellite(
        norad=39084, name="Landsat-8", provider="NASA/USGS", sat_type="Optical",
        series="Landsat", launch=None,
        cameras={
            "OLI (9-band)": {"swath_km": 185, "resolution_m": 30},
            "TIRS (2-band)": {"swath_km": 185, "resolution_m": 100}
        },
        period_min=98.9, inclination=98.2, color="#FF0000"
    ),
]

# Commercial Constellations

COMMERCIAL_CONSTELLATIONS = [
    _create_satellite(
        norad=42072, name="Planet-Scope-1", provider="Planet", sat_type="Optical",
        series="Dove", launch=None,
        cameras={"Dove (RGB+NIR)": {"swath_km": 24, "resolution_m": 3}},
        period_min=95.2, inclination=97.3, color="#FFA500"
    ),
    _create_satellite(
        norad=44880, name="BlackSky-1", provider="BlackSky", sat_type="Optical",
        series="BlackSky", launch=None,
        cameras={"Global (Pan+MS)": {"swath_km": 4.4, "resolution_m": 1}},
        period_min=95.3, inclination=97.4, color="#9400D3"
    ),
]

# -----------------------------------------------------------------------------
# MASTER SATELLITE DICTIONARY
# -----------------------------------------------------------------------------

