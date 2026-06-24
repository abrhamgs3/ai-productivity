"""
tests/conftest.py — Shared pytest fixtures for the APRP test suite.

All fixtures reference ``src/ai_productivity/`` — the single authoritative
package.  Fixtures that depend on sub-systems not yet implemented return
``None``; tests that require them should be marked ``@pytest.mark.skip``.

Fixture inventory
-----------------
sample_panel        Synthetic balanced panel (10 countries x 10 years).
world_bank_raw      Well-formed World Bank API v2 JSON response stub.
oecd_raw            OECD SDMX-JSON response skeleton.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Panel fixtures
# ---------------------------------------------------------------------------

N_COUNTRIES = 10
N_YEARS = 10
COUNTRIES = [f"C{i:02d}" for i in range(N_COUNTRIES)]
YEARS = list(range(2010, 2010 + N_YEARS))
RNG = np.random.default_rng(42)


@pytest.fixture(scope="session")
def sample_panel() -> pd.DataFrame:
    """
    Synthetic balanced panel: 10 countries x 10 years (100 observations).

    Columns
    -------
    iso3, year, tfp_growth, aipi, log_gdp_pc, log_hc, log_capital,
    trade_openness, gfcf_share, tertiary_enrol
    """
    rows = [
        {
            "iso3": c,
            "year": y,
            "tfp_growth": RNG.normal(0.02, 0.03),
            "aipi": RNG.uniform(0.0, 1.0),
            "log_gdp_pc": RNG.normal(9.5, 1.0),
            "log_hc": RNG.normal(0.5, 0.2),
            "log_capital": RNG.normal(12.0, 1.5),
            "trade_openness": RNG.uniform(0.3, 1.5),
            "gfcf_share": RNG.uniform(0.15, 0.40),
            "tertiary_enrol": RNG.uniform(20.0, 90.0),
        }
        for c in COUNTRIES
        for y in YEARS
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Raw API response fixtures (used by ingestion tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def world_bank_raw() -> list:
    """
    Minimal well-formed World Bank API v2 JSON response for two observations.
    """
    return [
        {"page": 1, "pages": 1, "per_page": 50, "total": 2},
        [
            {
                "indicator": {"id": "IT.NET.USER.ZS", "value": "Individuals using the Internet"},
                "country": {"id": "US", "value": "United States"},
                "countryiso3code": "USA",
                "date": "2020",
                "value": 90.1,
                "unit": "",
                "obs_status": "",
                "decimal": 1,
            },
            {
                "indicator": {"id": "IT.NET.USER.ZS", "value": "Individuals using the Internet"},
                "country": {"id": "DE", "value": "Germany"},
                "countryiso3code": "DEU",
                "date": "2020",
                "value": 88.4,
                "unit": "",
                "obs_status": "",
                "decimal": 1,
            },
        ],
    ]


@pytest.fixture(scope="session")
def oecd_raw() -> dict:
    """
    Skeleton OECD SDMX-JSON response structure for unit tests.
    """
    return {
        "header": {
            "id": "test",
            "test": True,
            "prepared": "2024-01-01T00:00:00",
            "sender": {"id": "OECD"},
        },
        "dataSets": [
            {
                "action": "Information",
                "series": {
                    "0:0:0:0": {
                        "attributes": [0],
                        "observations": {
                            "0": [42.3, 0, None],
                            "1": [43.1, 0, None],
                        },
                    }
                },
            }
        ],
        "structure": {
            "dimensions": {
                "series": [
                    {"id": "LOCATION", "values": [{"id": "USA", "name": "United States"}]},
                    {"id": "INDICATOR", "values": [{"id": "GERD", "name": "GERD"}]},
                    {"id": "MEASURE", "values": [{"id": "PC_GDP", "name": "% of GDP"}]},
                    {"id": "POWERCODE", "values": [{"id": "0", "name": "Units"}]},
                ],
                "observation": [
                    {
                        "id": "TIME_PERIOD",
                        "values": [
                            {"id": "2019", "name": "2019"},
                            {"id": "2020", "name": "2020"},
                        ],
                    }
                ],
            }
        },
    }
