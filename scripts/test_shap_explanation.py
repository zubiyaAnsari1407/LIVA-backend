from pathlib import Path

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

DATA_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "liva_master_training.csv"
)


def main():
    model = joblib.load(MODEL_FILE)

    df = pd.read_csv(DATA_FILE)

    features = [
        "original_cost_cr",
        "expenditure_cr",
        "expenditure_ratio",
        "physical_progress_pct",
        "original_completion_year",
        "sanction_year",
        "sector",
        "line_ministry",
    ]

    sample = df[features].iloc[[0]].copy()

    preprocessor = model.named_steps[
        "preprocessor"
    ]

    classifier = model.named_steps[
        "classifier"
    ]

    transformed = preprocessor.transform(
        sample
    )

    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()

    feature_names = (
        preprocessor
        .get_feature_names_out()
    )

    probability = model.predict_proba(
        sample
    )[0][1]

    prediction = int(
        model.predict(sample)[0]
    )

    explainer = shap.TreeExplainer(
        classifier
    )

    shap_values = explainer.shap_values(
        transformed
    )

    # Handle different SHAP versions
    if isinstance(shap_values, list):
        values = shap_values[1][0]

    else:
        shap_array = np.asarray(
            shap_values
        )

        if shap_array.ndim == 3:
            values = shap_array[
                0,
                :,
                1,
            ]
        else:
            values = shap_array[0]

    explanation = pd.DataFrame(
        {
            "feature": feature_names,
            "shap_value": values,
        }
    )

    explanation[
        "absolute_impact"
    ] = explanation[
        "shap_value"
    ].abs()

    explanation = (
        explanation
        .sort_values(
            "absolute_impact",
            ascending=False,
        )
        .head(10)
    )

    print(
        "\n=============================="
    )
    print(
        "LIVA SHAP EXPLANATION TEST"
    )
    print(
        "=============================="
    )

    print(
        "\nProject:",
        df.iloc[0]["project_name"],
    )

    print(
        "\nActual label:",
        int(
            df.iloc[0][
                "is_schedule_delayed"
            ]
        ),
    )

    print(
        "Predicted label:",
        prediction,
    )

    print(
        "Delay probability:",
        round(
            probability * 100,
            2,
        ),
        "%",
    )

    print(
        "\nTop SHAP factors:\n"
    )

    print(
        explanation[
            [
                "feature",
                "shap_value",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()