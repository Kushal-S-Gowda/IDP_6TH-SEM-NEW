# FloodSense Pro — ML Model Training
# Labels = FHI risk class from ml/hydrology.py (physics-grounded, not arbitrary).
# Features = 16 (10 weather/geo + 6 engineered hydrology). Retrain after preprocess.py.

import pandas as pd
import numpy as np
import joblib
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import (classification_report, confusion_matrix,
                              accuracy_score, f1_score, roc_auc_score)
from sklearn.preprocessing import label_binarize
from xgboost import XGBClassifier

from ml.preprocess import (
    ML_FEATURES,
    generate_flood_dataset,
    preprocess_and_split,
    show_dataset_stats,
)

RISK_LABELS = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "EXTREME"}

def train_all_models():
    print("FloodSense Pro — ML Model Training")
    print("=" * 55)

    # ── Step 1: Generate & preprocess data ──────────────────
    df = generate_flood_dataset(n_samples=5000)
    show_dataset_stats(df)
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv("data/processed/flood_dataset.csv", index=False)
    print(f"  Features ({len(ML_FEATURES)}): {', '.join(ML_FEATURES[:4])} ...")
    X_train, X_test, y_train, y_test, scaler = preprocess_and_split(df)

    # ── Step 2: Define all 4 models ─────────────────────────
    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight="balanced"
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            class_weight="balanced"
        ),
        "XGBoost": XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            random_state=42,
            eval_metric="mlogloss",
            verbosity=0
        ),
        "Support Vector Machine": SVC(
            kernel="rbf",
            C=1.0,
            random_state=42,
            class_weight="balanced",
            probability=True
        )
    }

    # ── Step 3: Train & evaluate each model ─────────────────
    results = {}
    best_model = None
    best_score = 0
    best_name = ""

    for name, model in models.items():
        print(f"\n[Training] {name}...")
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)

        # Metrics
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="weighted")

        # AUC-ROC (multiclass)
        y_test_bin = label_binarize(y_test, classes=[0,1,2,3])
        auc = roc_auc_score(y_test_bin, y_prob, multi_class="ovr", average="weighted")

        # Per-class recall (EXTREME recall is most critical)
        report = classification_report(y_test, y_pred,
                                        target_names=["LOW","MEDIUM","HIGH","EXTREME"],
                                        output_dict=True)
        extreme_recall = report["EXTREME"]["recall"]
        high_recall    = report["HIGH"]["recall"]

        results[name] = {
            "accuracy":       round(accuracy * 100, 2),
            "f1_score":       round(f1 * 100, 2),
            "auc_roc":        round(auc * 100, 2),
            "extreme_recall": round(extreme_recall * 100, 2),
            "high_recall":    round(high_recall * 100, 2),
            "model":          model
        }

        print(f"  Accuracy       : {accuracy*100:.2f}%")
        print(f"  F1 Score       : {f1*100:.2f}%")
        print(f"  AUC-ROC        : {auc*100:.2f}%")
        print(f"  HIGH Recall    : {high_recall*100:.2f}%")
        print(f"  EXTREME Recall : {extreme_recall*100:.2f}%")

        # Track best model (prioritize F1 score)
        if f1 > best_score:
            best_score = f1
            best_model = model
            best_name  = name

    # ── Step 4: Print comparison table ──────────────────────
    print("\n")
    print("=" * 75)
    print("  MODEL COMPARISON TABLE")
    print("=" * 75)
    print(f"  {'Model':<26} {'Accuracy':>9} {'F1 Score':>9} {'AUC-ROC':>8} {'HIGH R':>7} {'EXT R':>7}")
    print("-" * 75)
    for name, res in results.items():
        marker = " [BEST]" if name == best_name else ""
        print(f"  {name:<26} {res['accuracy']:>8}% {res['f1_score']:>8}% "
              f"{res['auc_roc']:>7}% {res['high_recall']:>6}% "
              f"{res['extreme_recall']:>6}%{marker}")
    print("=" * 75)

    # ── Step 5: Detailed report for best model ───────────────
    print(f"\n[Best Model] {best_name}")
    best_preds = best_model.predict(X_test)
    print("\nDetailed Classification Report:")
    print(classification_report(y_test, best_preds,
                                  target_names=["LOW","MEDIUM","HIGH","EXTREME"]))

    print("\nConfusion Matrix:")
    cm = confusion_matrix(y_test, best_preds)
    print(f"  {'':12} {'Pred LOW':>10} {'Pred MED':>10} {'Pred HIGH':>10} {'Pred EXT':>10}")
    print(f"  {'Actual LOW':12} {cm[0][0]:>10} {cm[0][1]:>10} {cm[0][2]:>10} {cm[0][3]:>10}")
    print(f"  {'Actual MED':12} {cm[1][0]:>10} {cm[1][1]:>10} {cm[1][2]:>10} {cm[1][3]:>10}")
    print(f"  {'Actual HIGH':12} {cm[2][0]:>10} {cm[2][1]:>10} {cm[2][2]:>10} {cm[2][3]:>10}")
    print(f"  {'Actual EXT':12} {cm[3][0]:>10} {cm[3][1]:>10} {cm[3][2]:>10} {cm[3][3]:>10}")

    # ── Step 6: Save best model ──────────────────────────────
    os.makedirs("ml/models", exist_ok=True)
    joblib.dump(best_model, "ml/models/best_model.pkl")
    joblib.dump(results,    "ml/models/results.pkl")

    print(f"\n[OK] Best model saved -> ml/models/best_model.pkl")
    print(f"[OK] Results saved   -> ml/models/results.pkl")
    print(f"\nWinner: {best_name} with {best_score*100:.2f}% F1 Score")

    return best_model, results

# ─── RUN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    train_all_models()