import pandas as pd
import statsmodels.api as sm
from linearmodels.panel import PanelOLS

df = pd.read_csv("data/processed/panel_clean.csv")
df = df.set_index(['country','year'])

y = df['ln_tfp']
X = sm.add_constant(df[['ln_ai','ln_hc']])

model = PanelOLS(
    y,
    X,
    entity_effects=True,
    drop_absorbed=True
)

res = model.fit(cov_type='clustered', cluster_entity=True)

with open("tables/tfp_regression.txt","w") as f:
    f.write(str(res.summary))