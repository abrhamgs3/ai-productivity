"""
04c_download_oecd_tfp.py
------------------------
Downloads OECD Multi-Factor Productivity (MFP) data and extracts
country-years still missing TFP in panel_clean.csv.

OECD data: "Multifactor Productivity" (dataset: MFP)
Indicator: T_GDPV (MFP growth index or level, economy-wide)

We use the OECD JSON-stat API (no key required):
  https://stats.oecd.org/SDMX-JSON/data/PDYGTH/...

Fallback: also tries the newer OECD Data Explorer API.

Output: data/raw/oecd_tfp.csv
        country | year | tfp_oecd   (levels, base year normalized if needed)
"""

import sys
import json
import urllib.request
import urllib.error
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Find which countries still need TFP ───────────────────────────────────
panel = pd.read_csv("data/processed/panel_clean.csv")
missing_tfp = panel[panel["tfp"].isna()]["country"].unique()
print(f"Countries still missing TFP after PWT supplement: {len(missing_tfp)}")
print(sorted(missing_tfp)[:30], "..." if len(missing_tfp) > 30 else "")

# ── OECD country codes (ISO3 that OECD uses) ─────────────────────────────
# Map WDI country names → OECD ISO3 codes for the missing countries
OECD_CODE_MAP = {
    "United Arab Emirates":       "ARE",
    "Vietnam":                    "VNM",
    "Bangladesh":                 "BGD",
    "Pakistan":                   "PAK",
    "Ethiopia":                   "ETH",
    "Ghana":                      "GHA",
    "Cambodia":                   "KHM",
    "Senegal":                    "SEN",
    "Uganda":                     "UGA",
    "Cameroon":                   "CMR",
    "Mozambique":                 "MOZ",
    "Mali":                       "MLI",
    "Burkina Faso":               "BFA",
    "Niger":                      "NER",
    "Chad":                       "TCD",
    "Sierra Leone":               "SLE",
    "Liberia":                    "LBR",
    "Guinea":                     "GIN",
    "Benin":                      "BEN",
    "Togo":                       "TGO",
    "Haiti":                      "HTI",
    "Papua New Guinea":           "PNG",
    "Myanmar":                    "MMR",
    "Nepal":                      "NPL",
    "Afghanistan":                "AFG",
    "Yemen, Rep.":                "YEM",
    "Syrian Arab Republic":       "SYR",
    "Libya":                      "LBY",
    "Gabon":                      "GAB",
    "Equatorial Guinea":          "GNQ",
    "Congo, Dem. Rep.":           "COD",
    "Congo, Rep.":                "COG",
    "Central African Republic":   "CAF",
    "South Sudan":                "SSD",
    "Somalia":                    "SOM",
    "Eritrea":                    "ERI",
    "Djibouti":                   "DJI",
    "Comoros":                    "COM",
    "Sao Tome and Principe":      "STP",
    "Cabo Verde":                 "CPV",
    "Maldives":                   "MDV",
    "Bhutan":                     "BTN",
    "Timor-Leste":                "TLS",
    "Solomon Islands":            "SLB",
    "Vanuatu":                    "VUT",
    "Samoa":                      "WSM",
    "Tonga":                      "TON",
    "Kiribati":                   "KIR",
    "Micronesia, Fed. Sts.":      "FSM",
    "Marshall Islands":           "MHL",
    "Palau":                      "PLW",
    "Nauru":                      "NRU",
    "Tuvalu":                     "TUV",
    "Kosovo":                     "XKX",
    "West Bank and Gaza":         "PSE",
    "Cuba":                       "CUB",
    "Sudan":                      "SDN",
    "Angola":                     "AGO",
    "Burundi":                    "BDI",
    "Zimbabwe":                   "ZWE",
    "Zambia":                     "ZMB",
    "Rwanda":                     "RWA",
    "Tanzania":                   "TZA",
    "Namibia":                    "NAM",
    "Botswana":                   "BWA",
    "Eswatini":                   "SWZ",
    "Lesotho":                    "LSO",
    "Malawi":                     "MWI",
    "Mauritania":                 "MRT",
    "Mauritius":                  "MUS",
    "Madagascar":                 "MDG",
    "Algeria":                    "DZA",
    "Libya":                      "LBY",
    "Tunisia":                    "TUN",
    "Morocco":                    "MAR",
    "Iraq":                       "IRQ",
    "Lebanon":                    "LBN",
    "Oman":                       "OMN",
    "Bahrain":                    "BHR",
    "Qatar":                      "QAT",
    "Kuwait":                     "KWT",
    "Armenia":                    "ARM",
    "Azerbaijan":                 "AZE",
    "Georgia":                    "GEO",
    "Belarus":                    "BLR",
    "Ukraine":                    "UKR",
    "Serbia":                     "SRB",
    "North Macedonia":            "MKD",
    "Bosnia and Herzegovina":     "BIH",
    "Albania":                    "ALB",
    "Montenegro":                 "MNE",
    "Ecuador":                    "ECU",
    "Peru":                       "PER",
    "Colombia":                   "COL",
    "Guatemala":                  "GTM",
    "Honduras":                   "HND",
    "Nicaragua":                  "NIC",
    "El Salvador":                "SLV",
    "Dominican Republic":         "DOM",
    "Trinidad and Tobago":        "TTO",
    "Jamaica":                    "JAM",
    "Barbados":                   "BRB",
    "Guyana":                     "GUY",
    "Suriname":                   "SUR",
    "Mongolia":                   "MNG",
    "Sri Lanka":                  "LKA",
    "Jordan":                     "JOR",
    "Tajikistan":                 "TJK",
    "Turkmenistan":               "TKM",
    "Uzbekistan":                 "UZB",
    "Hong Kong SAR, China":       "HKG",
    "Macao SAR, China":           "MAC",
    "Taiwan, China":              "TWN",
}

# ── Try OECD API ───────────────────────────────────────────────────────────
# OECD Productivity dataset: PDB_LV (productivity levels) or PDYGTH (growth)
# We try the MFP index from the "Productivity Statistics" dataset

print("\nAttempting OECD API download...")

OECD_COUNTRIES = "AUS+AUT+BEL+CAN+CHL+COL+CRI+CZE+DNK+EST+FIN+FRA+DEU+GRC+HUN+ISL+IRL+ISR+ITA+JPN+KOR+LVA+LTU+LUX+MEX+NLD+NZL+NOR+POL+PRT+SVK+SVN+ESP+SWE+CHE+TUR+GBR+USA"

url = (
    "https://stats.oecd.org/SDMX-JSON/data/"
    f"PDB_LV/{OECD_COUNTRIES}.T_GDPV.IDX2015/"
    "all?startTime=2010&endTime=2024&dimensionAtObservation=allDimensions"
)

records = []
try:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    
    # Parse SDMX-JSON structure
    dims = data["structure"]["dimensions"]["observation"]
    dim_map = {d["id"]: {str(i): v["id"] for i, v in enumerate(d["values"])} for d in dims}
    obs = data["dataSets"][0]["observations"]
    
    for key_str, val_list in obs.items():
        parts = key_str.split(":")
        country_code = dim_map["LOCATION"][parts[0]]
        measure = dim_map.get("MEASURE", dim_map.get("SUBJECT", {}))[parts[1]]
        time_str = dim_map["TIME_PERIOD"][parts[-1]]
        value = val_list[0]
        if value is not None:
            records.append({"iso3": country_code, "year": int(time_str), "tfp_oecd": float(value)})
    
    print(f"  OECD API: {len(records)} observations downloaded")
except Exception as e:
    print(f"  OECD API failed: {e}")
    print("  Trying alternative endpoint...")
    
    # Alternative: OECD Data Explorer (newer API)
    url2 = (
        "https://sdmx.oecd.org/public/rest/data/"
        "OECD.SDD.TPS,DSD_PRODUCTIVITY@DF_MFP,1.0/"
        "A.AUS+AUT+BEL+CAN+CHL+CZE+DNK+EST+FIN+FRA+DEU+GRC+HUN+IRL+ISR+ITA+JPN+KOR+LUX+MEX+NLD+NZL+NOR+POL+PRT+SVK+ESP+SWE+CHE+TUR+GBR+USA"
        ".MFP_GROWTH...."
        "?startPeriod=2010&endPeriod=2024&format=jsondata"
    )
    try:
        req2 = urllib.request.Request(url2, headers={"Accept": "application/vnd.sdmx.data+json"})
        with urllib.request.urlopen(req2, timeout=30) as resp2:
            data2 = json.loads(resp2.read())
        print(f"  Alternative OECD API: got response")
        # Parse it
        series = data2.get("data", {}).get("dataSets", [{}])[0].get("series", {})
        dims2 = data2["data"]["structure"]["dimensions"]["series"]
        tdims = data2["data"]["structure"]["dimensions"]["observation"]
        
        loc_idx = next(i for i, d in enumerate(dims2) if d["id"] == "REF_AREA")
        loc_vals = [v["id"] for v in dims2[loc_idx]["values"]]
        time_vals = [v["id"] for v in tdims[0]["values"]]
        
        for skey, sval in series.items():
            parts = skey.split(":")
            country_code = loc_vals[int(parts[loc_idx])]
            for tkey, obs_val in sval.get("observations", {}).items():
                yr_str = time_vals[int(tkey)]
                val = obs_val[0]
                if val is not None:
                    records.append({"iso3": country_code, "year": int(yr_str[:4]), "tfp_oecd": float(val)})
        
        print(f"  Alternative OECD API: {len(records)} observations")
    except Exception as e2:
        print(f"  Alternative OECD API also failed: {e2}")

if records:
    oecd_df = pd.DataFrame(records)
    
    # Reverse map ISO3 → WDI country name
    iso3_to_wdi = {v: k for k, v in OECD_CODE_MAP.items()}
    # Add OECD member WDI names that are already in panel
    extra = {
        "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium", "CAN": "Canada",
        "CHL": "Chile", "COL": "Colombia", "CRI": "Costa Rica", "CZE": "Czechia",
        "DNK": "Denmark", "EST": "Estonia", "FIN": "Finland", "FRA": "France",
        "DEU": "Germany", "GRC": "Greece", "HUN": "Hungary", "ISL": "Iceland",
        "IRL": "Ireland", "ISR": "Israel", "ITA": "Italy", "JPN": "Japan",
        "KOR": "Korea, Rep.", "LVA": "Latvia", "LTU": "Lithuania", "LUX": "Luxembourg",
        "MEX": "Mexico", "NLD": "Netherlands", "NZL": "New Zealand", "NOR": "Norway",
        "POL": "Poland", "PRT": "Portugal", "SVK": "Slovak Republic", "SVN": "Slovenia",
        "ESP": "Spain", "SWE": "Sweden", "CHE": "Switzerland", "TUR": "Turkiye",
        "GBR": "United Kingdom", "USA": "United States",
    }
    iso3_to_wdi.update(extra)
    
    oecd_df["country"] = oecd_df["iso3"].map(iso3_to_wdi)
    oecd_df = oecd_df.dropna(subset=["country"])
    oecd_df = oecd_df[["country", "year", "tfp_oecd"]]
    
    # Normalize: convert growth index to approximate levels if needed
    # OECD PDB_LV T_GDPV is already an index (2015=100), divide by 100
    oecd_df["tfp_oecd"] = oecd_df["tfp_oecd"] / 100.0
    
    oecd_df.to_csv("data/raw/oecd_tfp.csv", index=False)
    print(f"\nSaved: data/raw/oecd_tfp.csv")
    print(f"  {oecd_df['country'].nunique()} countries, {len(oecd_df)} obs")
    print(f"  Year range: {oecd_df['year'].min()} – {oecd_df['year'].max()}")
    print(f"  Countries: {sorted(oecd_df['country'].unique())}")
    
    # Check overlap with still-missing
    missing_set = set(missing_tfp)
    covered_by_oecd = missing_set & set(oecd_df["country"].unique())
    print(f"\n  Of the {len(missing_tfp)} countries still missing TFP:")
    print(f"  OECD covers {len(covered_by_oecd)}: {sorted(covered_by_oecd)}")
else:
    print("\nNo OECD data downloaded. Manual download may be required.")
    print("See: https://stats.oecd.org/index.aspx?DataSetCode=PDB_LV")
