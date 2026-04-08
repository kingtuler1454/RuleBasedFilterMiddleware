import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix

inp = r"C:\Users\smorozov\Desktop\НИРС\windows_features.csv"
out = r"C:\Users\smorozov\Desktop\НИРС\iforest_scored.csv"

df = pd.read_csv(inp)

feature_cols = [
    "req_count", "x_std", "y_std", "z_std",
    "x_unique", "y_unique", "z_unique",
    "mean_abs_dx", "mean_abs_dy",
    "mean_dt", "std_dt", "min_dt", "max_dt"
]

# train только на clean (правильная схема для IF)
train = df[df["sourceLabel"] == "clean"].copy()
test = df.copy()

X_train = train[feature_cols].to_numpy()
X_test = test[feature_cols].to_numpy()

model = IsolationForest(
    n_estimators=300,
    contamination=0.10,
    random_state=42
)
model.fit(X_train)

pred_raw = model.predict(X_test)  # 1 normal, -1 anomaly
test["predLabel"] = np.where(pred_raw == -1, "synthetic", "clean")
test["anomalyScore"] = model.score_samples(X_test)

test.to_csv(out, index=False)

print("saved:", out)
print("test label counts:\n", test["sourceLabel"].value_counts().to_string())
print("pred label counts:\n", test["predLabel"].value_counts().to_string())

labels = ["clean", "synthetic"]
cm = confusion_matrix(test["sourceLabel"], test["predLabel"], labels=labels)
print("\nConfusion matrix (rows=true, cols=pred):")
print(pd.DataFrame(cm, index=labels, columns=labels).to_string())

print("\nClassification report:")
print(classification_report(test["sourceLabel"], test["predLabel"], labels=labels, digits=4))