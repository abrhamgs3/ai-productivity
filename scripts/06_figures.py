import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/processed/panel_clean.csv")

avg = df.groupby("year")[["ln_ai","ln_tfp"]].mean()

plt.figure()
plt.plot(avg.index, avg["ln_ai"])
plt.plot(avg.index, avg["ln_tfp"])
plt.xlabel("Year")
plt.ylabel("Log values")
plt.title("AI and TFP trends")

plt.savefig("figures/ai_tfp_trend.png")