"""
train_model.py
==============
MIRA – Health Risk Classifier
Trains a Random Forest + Gradient Boosting ensemble on synthetic patient data.

Risk Categories:
  0 – Healthy
  1 – Diabetes Risk          (elevated glucose)
  2 – Anaemia Risk           (low haemoglobin)
  3 – Dyslipidaemia Risk     (high cholesterol)
  4 – High Composite Risk    (2+ abnormal values)

Run ONCE before starting the Flask server:
    python train_model.py        (Linux / macOS)
    python train_model.py        (Windows – inside activated venv)

Outputs:
    model.pkl       – trained scikit-learn Pipeline
    features.json   – feature names + label map (read by app.py)
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings("ignore")

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

# ── Label map ──────────────────────────────────────────────────────────────────
LABELS = {
    0: "Healthy – all values within normal range.",
    1: "Diabetes Risk – elevated glucose detected.",
    2: "Anaemia Risk – low haemoglobin detected.",
    3: "Dyslipidaemia Risk – high cholesterol detected.",
    4: "High Composite Risk – multiple abnormal values detected.",
}

# ── Synthetic data generation ──────────────────────────────────────────────────
# Clinical reference ranges used:
#   Glucose      70–100  mg/dL  normal  |  >140 diabetic risk
#   Haemoglobin  12–17   g/dL   normal  |  <12  anaemia
#   Cholesterol  <200    mg/dL  normal  |  >200 dyslipidaemia

np.random.seed(42)

def make_samples(n, g_range, hb_range, ch_range, label):
    g  = np.random.uniform(*g_range,  n) + np.random.normal(0, 2.0, n)
    hb = np.random.uniform(*hb_range, n) + np.random.normal(0, 0.3, n)
    ch = np.random.uniform(*ch_range, n) + np.random.normal(0, 3.0, n)
    g  = np.clip(g,   40.0, 500.0)
    hb = np.clip(hb,   3.0,  22.0)
    ch = np.clip(ch,  80.0, 450.0)
    return np.column_stack([g, hb, ch, np.full(n, label)])

data = np.vstack([
    # 0 – Healthy
    make_samples(400, (70, 100),  (12.0, 17.0), (120, 199), 0),
    make_samples(100, (80,  99),  (12.5, 16.5), (130, 185), 0),
    # 1 – Diabetes Risk
    make_samples(250, (141, 300), (12.0, 17.0), (120, 199), 1),
    make_samples(100, (110, 140), (12.0, 17.0), (120, 190), 1),
    # 2 – Anaemia Risk
    make_samples(250, (70, 110),  (3.0, 11.9),  (120, 199), 2),
    make_samples(100, (70, 100),  (8.0, 11.5),  (130, 195), 2),
    # 3 – Dyslipidaemia Risk
    make_samples(250, (70, 110),  (12.0, 17.0), (201, 400), 3),
    make_samples(100, (75, 100),  (12.5, 16.5), (210, 350), 3),
    # 4 – High Composite Risk (2+ abnormal)
    make_samples(200, (141, 300), (3.0, 11.9),  (201, 400), 4),
    make_samples(150, (141, 300), (12.0, 17.0), (201, 400), 4),
    make_samples(150, (70, 110),  (3.0, 11.9),  (201, 400), 4),
    make_samples(100, (141, 300), (3.0, 11.9),  (120, 199), 4),
])

df = pd.DataFrame(data, columns=["glucose", "haemoglobin", "cholesterol", "label"])
df["label"] = df["label"].astype(int)

# ── Feature engineering ────────────────────────────────────────────────────────
df["glucose_hb_ratio"]     = df["glucose"]     / (df["haemoglobin"] + 1e-6)
df["chol_hb_ratio"]        = df["cholesterol"] / (df["haemoglobin"] + 1e-6)
df["glucose_norm"]         = (df["glucose"]     - 85)   / 30
df["hb_norm"]              = (df["haemoglobin"] - 14.5) / 2.5
df["chol_norm"]            = (df["cholesterol"] - 160)  / 40
df["composite_risk_score"] = (
    (df["glucose"]     > 140).astype(int) +
    (df["haemoglobin"] <  12).astype(int) +
    (df["cholesterol"] > 200).astype(int)
)

FEATURES = [
    "glucose", "haemoglobin", "cholesterol",
    "glucose_hb_ratio", "chol_hb_ratio",
    "glucose_norm", "hb_norm", "chol_norm",
    "composite_risk_score",
]

X = df[FEATURES].values
y = df["label"].values

# ── Train/test split ───────────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

# ── Build ensemble pipeline ────────────────────────────────────────────────────
rf = RandomForestClassifier(
    n_estimators=300, max_depth=10, min_samples_leaf=3,
    random_state=42, class_weight="balanced", n_jobs=-1,
)
gb = GradientBoostingClassifier(
    n_estimators=200, learning_rate=0.05, max_depth=5, random_state=42,
)
ensemble = VotingClassifier(estimators=[("rf", rf), ("gb", gb)], voting="soft")
pipeline = Pipeline([("scaler", StandardScaler()), ("model", ensemble)])

print("=" * 58)
print("  MIRA – Health Risk Classifier Training")
print("=" * 58)
print(f"  Total samples : {len(X)}")
print(f"  Features      : {len(FEATURES)}")
print(f"  Train / Test  : {len(X_train)} / {len(X_test)}")
print("\n  Training ensemble …")

pipeline.fit(X_train, y_train)

# ── Evaluation ─────────────────────────────────────────────────────────────────
y_pred    = pipeline.predict(X_test)
acc       = accuracy_score(y_test, y_pred)
cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring="accuracy")

label_names = [LABELS[i].split(" –")[0] for i in range(5)]

print(f"\n  Test Accuracy  : {acc * 100:.2f}%")
print(f"  5-Fold CV Mean : {cv_scores.mean() * 100:.2f}%  ±  {cv_scores.std() * 100:.2f}%")
print()
print(classification_report(y_test, y_pred, target_names=label_names))
print("  Confusion Matrix:")
for i, row in enumerate(confusion_matrix(y_test, y_pred)):
    print(f"    {label_names[i]:<30}: {list(row)}")

# ── Save artefacts ─────────────────────────────────────────────────────────────
BASE          = os.path.dirname(os.path.abspath(__file__))
model_path    = os.path.join(BASE, "model.pkl")
features_path = os.path.join(BASE, "features.json")

joblib.dump(pipeline, model_path)

with open(features_path, "w") as f:
    json.dump({"features": FEATURES, "labels": {str(k): v for k, v in LABELS.items()}}, f, indent=2)

print(f"\n  ✅ model.pkl    → {model_path}")
print(f"  ✅ features.json → {features_path}")
print(f"\n  Now run:  python app.py")
print("=" * 58)
