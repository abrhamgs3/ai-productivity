import pandas as pd

df = pd.read_csv("data/processed/panel_clean.csv")

summary = df[['ln_ai','ln_tfp','ln_gdp','ln_hc']].describe()

summary.to_latex("tables/summary_stats.tex")