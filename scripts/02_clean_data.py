import pandas as pd
import numpy as np

from agents.data_agent import drop_aggregate_entities

df = pd.read_csv("data/raw/merged_dataset.csv")

# Drop World Bank regional/income-group aggregates ("World", "High income",
# "Sub-Saharan Africa", etc.) so the panel contains actual countries only.
df = drop_aggregate_entities(df)

df['ln_gdp'] = np.log(df['gdp_pc'])
df['ln_ai'] = np.log(df['AI_index'])
df['ln_tfp'] = np.log(df['tfp'])
df['ln_hc'] = np.log(df['hc'])

# Construct-validity sub-indices: split the AI proxy into a "digital
# infrastructure" component (internet/mobile/secure-server access) and an
# "innovation/patent" component (patent and IP-receipt activity). Each is a
# row-wise mean of z-scored inputs, used to test whether the headline AI
# association is driven by general digital diffusion or by innovation activity.
digital_cols = ['internet_users', 'mobile_subs', 'secure_servers']
innovation_cols = ['pat_res', 'pat_nres', 'ip_receipts']

df['digital_infra_index'] = df[digital_cols].apply(
    lambda s: (s - s.mean()) / s.std()
).mean(axis=1, skipna=True)

df['innovation_index'] = df[innovation_cols].apply(
    lambda s: (s - s.mean()) / s.std()
).mean(axis=1, skipna=True)

df.to_csv("data/processed/panel_clean.csv", index=False)