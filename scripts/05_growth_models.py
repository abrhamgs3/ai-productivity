df['gdp_growth'] = df.groupby(level=0)['ln_gdp'].diff()

df_g = df[['gdp_growth','ln_ai','ln_hc']].dropna()

y = df_g['gdp_growth']
X = sm.add_constant(df_g[['ln_ai','ln_hc']])

model = PanelOLS(
    y,
    X,
    entity_effects=True,
    drop_absorbed=True
)

res = model.fit(cov_type='clustered', cluster_entity=True)

print(res.summary)