"""
02_clean_data.py
----------------
Build data/processed/panel_clean.csv from data/raw/merged_dataset.csv.

Key decisions
-------------
* Drop World Bank regional / income-group aggregates (not sovereign countries).
* ln_ai  = log(ai_proxy_total)   ← externally downloaded AI-adoption proxy;
           always positive, so the log is well-defined.
           NOT log(AI_index): AI_index is a z-score composite that takes
           negative values, making log undefined for ~30 % of observations.
* ln_gdp = log(gdp_pc)
* ln_tfp = log(tfp)              from Penn World Tables
* ln_hc  = log(hc)               human capital index (PWT)
* digital_infra_index, innovation_index — constructed sub-indices for
  falsification / construct-validity tests (see add_sub_indices).
"""

import numpy as np
import pandas as pd

from agents.data_agent import drop_aggregate_entities

df = pd.read_csv("data/raw/merged_dataset.csv")

# Drop World Bank regional/income-group aggregates so the panel
# contains sovereign countries only.
df = drop_aggregate_entities(df)

# Core log transforms --------------------------------------------------
df["ln_gdp"] = np.log(df["gdp_pc"])

# AI adoption: use the raw downloaded proxy (always positive).
# AI_index is a z-score composite — it cannot be log-transformed.
df["ln_ai"] = np.log(df["ai_proxy_total"])

df["ln_tfp"] = np.log(df["tfp"])
df["ln_hc"]  = np.log(df["hc"])

# Sub-indices for construct-validity tests -----------------------------
# digital_infra_index: z-scored mean of internet/mobile/server access.
digital_cols    = ["internet_users", "mobile_subs", "secure_servers"]
innovation_cols = ["pat_res", "pat_nres", "ip_receipts"]

df["digital_infra_index"] = (
    df[digital_cols]
    .apply(lambda s: (s - s.mean()) / s.std())
    .mean(axis=1, skipna=True)
)

df["innovation_index"] = (
    df[innovation_cols]
    .apply(lambda s: (s - s.mean()) / s.std())
    .mean(axis=1, skipna=True)
)

df.to_csv("data/processed/panel_clean.csv", index=False)
print(f"Saved panel_clean.csv: {len(df)} rows, {df['country'].nunique()} countries")

# Quick coverage report
complete = df.dropna(subset=["ln_ai", "ln_tfp", "ln_hc", "ln_gdp"])
print(f"Complete-case sample: {complete['country'].nunique()} countries, {len(complete)} obs")
