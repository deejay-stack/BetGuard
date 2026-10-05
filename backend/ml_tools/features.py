"""Offline estimator factories; never needed by model inference."""
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MaxAbsScaler
from sklearn.svm import LinearSVC
from app.ml.features import NormalizeHostnames, HostnameLexicalFeatures


def pipelines(seed=42, max_features=8000, trees=64):
    estimators = {
        "logistic_regression": LogisticRegression(solver="liblinear", class_weight="balanced", max_iter=300, random_state=seed),
        "svm": LinearSVC(C=1.0, class_weight="balanced", max_iter=3000, random_state=seed, dual="auto"),
        "random_forest": RandomForestClassifier(n_estimators=trees, max_depth=14, min_samples_leaf=2,
                                                class_weight="balanced_subsample", n_jobs=1, random_state=seed),
    }
    return {name: Pipeline([
        ("normalize", NormalizeHostnames()),
        ("features", FeatureUnion([
            ("characters", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=2,
                                           max_features=max_features, sublinear_tf=True, dtype=np.float32)),
            ("lexical", Pipeline([("extract", HostnameLexicalFeatures()),
                                  ("scale", MaxAbsScaler())])),
        ], n_jobs=1)),
        ("estimator", estimator),
    ]) for name, estimator in estimators.items()}


