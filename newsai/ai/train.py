"""PHẦN 2 - HUẤN LUYỆN & ĐÁNH GIÁ MÔ HÌNH AI PHÂN TÍCH CẢM XÚC TIN TỨC.

Quy trình:
  1. Đọc bộ dữ liệu đã gán nhãn (tích cực / trung tính / tiêu cực), chia 80% train - 20% test (phân tầng).
  2. So sánh 4 mô hình: Từ điển (baseline), Naive Bayes, Logistic Regression, Linear SVM.
     Đặc trưng: TF-IDF n-gram từ (1-2) + n-gram ký tự (2-5) -> chịu được lỗi chính tả, từ ghép tiếng Việt.
  3. Chọn mô hình có F1-macro kiểm định chéo 5-fold cao nhất.
  4. Kiểm định thêm trên 400 bài báo THỰC TẾ đã gán nhãn tay (có cách diễn đạt mô hình chưa thấy).
  5. Lưu mô hình (.joblib), báo cáo (JSON, CSV, ma trận nhầm lẫn PNG), đăng ký vào analytics.model_registry.
     Cơ chế champion/challenger: chỉ kích hoạt mô hình mới nếu không kém mô hình đang chạy.
"""
import csv
import json
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from psycopg2.extras import Json
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from ..config import GROUND_TRUTH, LABELED_CORPUS, MODEL_DIR, REPORT_DIR
from ..db import RunLog
from .text import LexiconSentiment, build_input

LABELS = ["positive", "neutral", "negative"]
LABEL_VI = {"positive": "Tích cực", "neutral": "Trung tính", "negative": "Tiêu cực"}
SEED = 42


def tfidf_features():
    return FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True,
                                 max_features=60000)),
    ])


def candidate_models():
    return {
        "lexicon": ("Từ điển cảm xúc (baseline)", LexiconSentiment()),
        "naive_bayes": ("TF-IDF + Multinomial Naive Bayes", Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("clf", MultinomialNB(alpha=0.3))])),
        "logreg": ("TF-IDF (từ + ký tự) + Logistic Regression", Pipeline([
            ("features", tfidf_features()),
            ("clf", LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced"))])),
        "linear_svm": ("TF-IDF (từ + ký tự) + Linear SVM (hiệu chỉnh xác suất)", Pipeline([
            ("features", tfidf_features()),
            ("clf", CalibratedClassifierCV(LinearSVC(C=0.5, class_weight="balanced"), cv=3))])),
    }


def load_production_sample(conn):
    """Ghép nhãn tay của 400 bài thực tế với nội dung bài trong core.article."""
    if not GROUND_TRUTH.exists():
        return None
    with open(GROUND_TRUTH, encoding="utf-8") as f:
        truth = {(r["source_code"], r["external_id"]): r["true_label"] for r in csv.DictReader(f)}
    with conn.cursor() as cur:
        cur.execute("""SELECT s.source_code, a.external_id, a.title, a.summary
                       FROM core.article a JOIN core.dim_source s ON s.source_id = a.source_id""")
        rows = [(build_input(t, sm), truth[(sc, eid)]) for sc, eid, t, sm in cur.fetchall() if (sc, eid) in truth]
    if not rows:
        return None
    return [r[0] for r in rows], [r[1] for r in rows]


def evaluate(model, X, y):
    t0 = time.perf_counter()
    pred = model.predict(X)
    ms_per_1000 = (time.perf_counter() - t0) / max(len(X), 1) * 1_000_000
    return {
        "accuracy": round(accuracy_score(y, pred), 4),
        "f1_macro": round(f1_score(y, pred, average="macro"), 4),
        "per_class": {k: {m: round(v, 4) for m, v in d.items()}
                      for k, d in classification_report(y, pred, labels=LABELS, output_dict=True,
                                                        zero_division=0).items() if k in LABELS},
        "confusion_matrix": confusion_matrix(y, pred, labels=LABELS).tolist(),
        "inference_ms_per_1000_docs": round(ms_per_1000, 1),
    }


def save_confusion_png(cm, title, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    cm = np.array(cm)
    fig, ax = plt.subplots(figsize=(5.2, 4.4), dpi=150)
    ax.imshow(cm, cmap="Blues")
    names = [LABEL_VI[l] for l in LABELS]
    ax.set_xticks(range(3), names)
    ax.set_yticks(range(3), names)
    ax.set_xlabel("Nhãn dự đoán")
    ax.set_ylabel("Nhãn thực tế")
    ax.set_title(title, fontsize=10)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "#1f2937", fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def train(conn, force_activate=False):
    MODEL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    with RunLog(conn, "ai:train_sentiment") as log:
        df = pd.read_csv(LABELED_CORPUS)
        n_raw = len(df)
        # Bỏ mẫu trùng văn bản để tránh "rò rỉ" giữa tập train và test (điểm số ảo)
        df = df.drop_duplicates(subset=["title", "summary"]).reset_index(drop=True)
        X = [build_input(t, s) for t, s in zip(df["title"], df["summary"])]
        y = df["label"].tolist()
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
        prod = load_production_sample(conn)
        log.extracted = len(X)
        print(f"  Dữ liệu gán nhãn: {n_raw} mẫu, sau khi bỏ trùng {len(X)} mẫu (train {len(X_tr)} / test {len(X_te)}); "
              f"phân bố nhãn: {df['label'].value_counts().to_dict()}")
        if prod:
            print(f"  Mẫu kiểm định thực tế: {len(prod[0])} bài")

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
        results, fitted = {}, {}
        for key, (name, model) in candidate_models().items():
            t0 = time.perf_counter()
            cv_scores = cross_val_score(model, X_tr, y_tr, cv=cv, scoring="f1_macro")
            model.fit(X_tr, y_tr)
            train_sec = time.perf_counter() - t0
            res = {"name": name, "cv_f1_mean": round(cv_scores.mean(), 4), "cv_f1_std": round(cv_scores.std(), 4),
                   "train_seconds": round(train_sec, 2), "test": evaluate(model, X_te, y_te)}
            if prod:
                res["production_sample"] = evaluate(model, *prod)
            results[key], fitted[key] = res, model
            print(f"  - {name:<55} CV-F1 {res['cv_f1_mean']:.4f}±{res['cv_f1_std']:.4f} | "
                  f"test acc {res['test']['accuracy']:.4f} F1 {res['test']['f1_macro']:.4f}"
                  + (f" | thực tế F1 {res['production_sample']['f1_macro']:.4f}" if prod else ""))

        # Chọn theo F1-macro kiểm định chéo; hòa thì ưu tiên F1 trên mẫu thực tế, rồi F1 tập test
        best = max((k for k in results if k != "lexicon"),
                   key=lambda k: (results[k]["cv_f1_mean"],
                                  results[k].get("production_sample", {}).get("f1_macro", 0),
                                  results[k]["test"]["f1_macro"]))
        best_res = results[best]
        version = f"sentiment-{best}-{datetime.now():%Y%m%d-%H%M%S}"
        # Huấn luyện lại mô hình tốt nhất trên TOÀN BỘ dữ liệu gán nhãn trước khi triển khai
        final_model = candidate_models()[best][1].fit(X, y)
        artifact = MODEL_DIR / f"{version}.joblib"
        joblib.dump({"model": final_model, "version": version, "labels": LABELS,
                     "input_builder": "newsai.ai.text.build_input"}, artifact)

        # Báo cáo
        metrics = {"selected_model": best, "model_version": version, "trained_at": datetime.now().isoformat(),
                   "dataset": {"raw": n_raw, "total": len(X), "train": len(X_tr), "test": len(X_te),
                               "label_distribution": df["label"].value_counts().to_dict(),
                               "production_sample": len(prod[0]) if prod else 0},
                   "comparison": results}
        # Đổi kiểu số của numpy/pandas về kiểu Python để ghi JSON an toàn trên mọi phiên bản thư viện
        metrics = json.loads(json.dumps(metrics, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
        (REPORT_DIR / f"metrics_{version}.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
        with open(REPORT_DIR / "model_comparison.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["model", "cv_f1_mean", "cv_f1_std", "test_accuracy", "test_f1_macro",
                        "production_accuracy", "production_f1_macro", "train_seconds", "inference_ms_per_1000"])
            for k, r in results.items():
                p = r.get("production_sample", {})
                w.writerow([r["name"], r["cv_f1_mean"], r["cv_f1_std"], r["test"]["accuracy"],
                            r["test"]["f1_macro"], p.get("accuracy"), p.get("f1_macro"), r["train_seconds"],
                            r["test"]["inference_ms_per_1000_docs"]])
        save_confusion_png(best_res["test"]["confusion_matrix"], f"Ma trận nhầm lẫn - tập test\n{best_res['name']}",
                           REPORT_DIR / "confusion_matrix_test.png")
        if prod:
            save_confusion_png(best_res["production_sample"]["confusion_matrix"],
                               f"Ma trận nhầm lẫn - 400 bài thực tế\n{best_res['name']}",
                               REPORT_DIR / "confusion_matrix_production.png")

        # Đăng ký mô hình + champion/challenger
        with conn.cursor() as cur:
            cur.execute("SELECT model_version, f1_macro FROM analytics.model_registry WHERE task='sentiment' AND is_active")
            current = cur.fetchone()
            new_f1 = best_res["test"]["f1_macro"]
            activate = force_activate or current is None or new_f1 >= float(current[1]) - 0.005
            if activate:
                cur.execute("UPDATE analytics.model_registry SET is_active = FALSE WHERE task='sentiment' AND is_active")
            cur.execute(
                """INSERT INTO analytics.model_registry (model_version, task, algorithm, artifact_path, train_size,
                                                         test_size, accuracy, f1_macro, metrics, is_active)
                   VALUES (%s, 'sentiment', %s, %s, %s, %s, %s, %s, %s, %s)""",
                (version, best_res["name"], str(artifact), len(X_tr), len(X_te), best_res["test"]["accuracy"],
                 new_f1, Json(metrics), activate))
        conn.commit()
        log.loaded = 1
        print(f"  => Chọn: {best_res['name']} | phiên bản {version} | "
              f"{'ĐÃ KÍCH HOẠT' if activate else 'không kích hoạt (kém mô hình hiện tại ' + current[0] + ')'}")
        return version
