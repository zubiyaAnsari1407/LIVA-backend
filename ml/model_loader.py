from functools import lru_cache
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
import shap


BASE_DIR = Path(__file__).resolve().parents[1]

MODEL_FILE = (
    BASE_DIR
    / "models"
    / "risk_model.joblib"
)

METRICS_FILE = (
    BASE_DIR
    / "models"
    / "risk_model_metrics.json"
)


MODEL_FEATURES = [
    "original_cost_cr",
    "expenditure_cr",
    "expenditure_ratio",
    "physical_progress_pct",
    "original_completion_year",
    "sanction_year",
    "sector",
    "line_ministry",
]


@lru_cache(maxsize=1)
def load_risk_model():
    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Trained model not found: {MODEL_FILE}"
        )

    return joblib.load(
        MODEL_FILE
    )


@lru_cache(maxsize=1)
def load_model_metadata():
    if not METRICS_FILE.exists():
        return {}

    with open(
        METRICS_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def clean_feature_name(
    feature: str,
) -> str:
    feature = feature.replace(
        "numeric__",
        "",
    )

    feature = feature.replace(
        "categorical__",
        "",
    )

    return feature


def predict_schedule_delay(
    payload: dict,
) -> dict:
    model = load_risk_model()

    missing = [
        feature
        for feature in MODEL_FEATURES
        if feature not in payload
    ]

    if missing:
        raise ValueError(
            f"Missing ML features: {missing}"
        )

    sample = pd.DataFrame(
        [
            {
                feature: payload[feature]
                for feature in MODEL_FEATURES
            }
        ]
    )

    prediction = int(
        model.predict(sample)[0]
    )

    probability = float(
        model.predict_proba(
            sample
        )[0][1]
    )

    explanation = explain_prediction(
        sample
    )

    metadata = load_model_metadata()

    return {
        "prediction": prediction,
        "is_delay_predicted": (
            prediction == 1
        ),
        "delay_probability": round(
            probability,
            6,
        ),
        "delay_probability_pct": round(
            probability * 100,
            2,
        ),
        "model_name": metadata.get(
            "model_name",
            "Unknown",
        ),
        "model_version": (
            "liva-general-schedule-delay-v1"
        ),
        "training_rows": metadata.get(
            "training_rows"
        ),
        "source_policy": metadata.get(
            "source_policy"
        ),
        "explanation": explanation,
        "important_note": (
            "This model predicts general "
            "infrastructure schedule-delay risk "
            "using official MoSPI/PAIMANA data. "
            "It is not a purely land-acquisition-"
            "specific model."
        ),
    }


def explain_prediction(
    sample: pd.DataFrame,
) -> list[dict]:
    model = load_risk_model()

    preprocessor = (
        model.named_steps[
            "preprocessor"
        ]
    )

    classifier = (
        model.named_steps[
            "classifier"
        ]
    )

    transformed = (
        preprocessor.transform(
            sample
        )
    )

    if hasattr(
        transformed,
        "toarray",
    ):
        transformed = (
            transformed.toarray()
        )

    feature_names = (
        preprocessor
        .get_feature_names_out()
    )

    explainer = shap.TreeExplainer(
        classifier
    )

    shap_values = (
        explainer.shap_values(
            transformed
        )
    )

    if isinstance(
        shap_values,
        list,
    ):
        values = (
            shap_values[1][0]
        )

    else:
        shap_array = np.asarray(
            shap_values
        )

        if (
            shap_array.ndim == 3
        ):
            values = shap_array[
                0,
                :,
                1,
            ]

        else:
            values = (
                shap_array[0]
            )

    rows = []

    for feature, value in zip(
        feature_names,
        values,
    ):
        impact = float(value)

        rows.append(
            {
                "feature": clean_feature_name(
                    feature
                ),
                "shap_value": round(
                    impact,
                    6,
                ),
                "absolute_impact": round(
                    abs(impact),
                    6,
                ),
                "direction": (
                    "INCREASES_DELAY_RISK"
                    if impact > 0
                    else "REDUCES_DELAY_RISK"
                    if impact < 0
                    else "NEUTRAL"
                ),
            }
        )

    rows.sort(
        key=lambda item:
            item["absolute_impact"],
        reverse=True,
    )

    return rows[:8]