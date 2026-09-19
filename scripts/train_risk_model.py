from pathlib import Path
import json

import joblib
import pandas as pd

from sklearn.compose import (
    ColumnTransformer,
)

from sklearn.ensemble import (
    RandomForestClassifier,
)

from sklearn.impute import (
    SimpleImputer,
)

from sklearn.linear_model import (
    LogisticRegression,
)

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from sklearn.model_selection import (
    train_test_split,
)

from sklearn.pipeline import (
    Pipeline,
)

from sklearn.preprocessing import (
    OneHotEncoder,
    StandardScaler,
)


BASE_DIR = Path(__file__).resolve().parents[1]

DATA_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "liva_master_training.csv"
)

MODEL_DIR = (
    BASE_DIR
    / "models"
)

MODEL_FILE = (
    MODEL_DIR
    / "risk_model.joblib"
)

METRICS_FILE = (
    MODEL_DIR
    / "risk_model_metrics.json"
)


MIN_ROWS = 100
MIN_CLASS_COUNT = 20


TARGET = "is_schedule_delayed"

NUMERIC_FEATURES = [
    "original_cost_cr",
    "expenditure_cr",
    "expenditure_ratio",
    "physical_progress_pct",
    "original_completion_year",
    "sanction_year",
]

OPTIONAL_NUMERIC_FEATURES = []

CATEGORICAL_FEATURES = [
    "sector",
    "line_ministry",
]


def load_data() -> pd.DataFrame:

    if not DATA_FILE.exists():

        raise FileNotFoundError(
            f"Training dataset not found:\n"
            f"{DATA_FILE}"
        )

    return pd.read_csv(
        DATA_FILE
    )


def validate_dataset(
    df: pd.DataFrame,
) -> None:

    print("\n==============================")
    print("LIVA MODEL TRAINING GUARD")
    print("==============================")

    print(
        "\nTraining records:",
        len(df),
    )

    if TARGET not in df.columns:

        raise ValueError(
            f"Target '{TARGET}' missing."
        )

    counts = (
        df[TARGET]
        .value_counts()
        .sort_index()
    )

    print(
        "\nClass distribution:"
    )

    print(
        counts
    )

    problems = []

    if len(df) < MIN_ROWS:

        problems.append(
            f"Need at least {MIN_ROWS} "
            f"government records. "
            f"Found {len(df)}."
        )

    for label in [0, 1]:

        count = int(
            counts.get(
                label,
                0,
            )
        )

        if count < MIN_CLASS_COUNT:

            problems.append(
                f"Class {label} has "
                f"{count} records; "
                f"minimum is "
                f"{MIN_CLASS_COUNT}."
            )

    if problems:

        print(
            "\nTRAINING BLOCKED:"
        )

        for problem in problems:

            print(
                "-",
                problem,
            )

        raise RuntimeError(
            "Training aborted because "
            "the government dataset is "
            "not yet sufficient."
        )

    print(
        "\nTRAINING STATUS: READY"
    )


def prepare_features(
    df: pd.DataFrame,
):

    numeric_features = [
        column
        for column in (
            NUMERIC_FEATURES
            + OPTIONAL_NUMERIC_FEATURES
        )
        if column in df.columns
    ]

    categorical_features = [
        column
        for column
        in CATEGORICAL_FEATURES
        if column in df.columns
    ]

    features = (
        numeric_features
        + categorical_features
    )

    if not features:

        raise ValueError(
            "No training features available."
        )

    X = df[
        features
    ].copy()

    y = (
        df[TARGET]
        .astype(int)
    )

    return (
        X,
        y,
        numeric_features,
        categorical_features,
    )


def make_preprocessor(
    numeric_features,
    categorical_features,
):

    transformers = []

    if numeric_features:

        numeric_pipeline = Pipeline(
            steps=[
                (
                    "imputer",
                    SimpleImputer(
                        strategy="median",
                    ),
                ),
                (
                    "scaler",
                    StandardScaler(),
                ),
            ]
        )

        transformers.append(
            (
                "numeric",
                numeric_pipeline,
                numeric_features,
            )
        )

    if categorical_features:

        categorical_pipeline = Pipeline(
            steps=[
                (
                    "imputer",
                    SimpleImputer(
                        strategy="most_frequent",
                    ),
                ),
                (
                    "encoder",
                    OneHotEncoder(
                        handle_unknown="ignore",
                    ),
                ),
            ]
        )

        transformers.append(
            (
                "categorical",
                categorical_pipeline,
                categorical_features,
            )
        )

    return ColumnTransformer(
        transformers=transformers,
    )


def evaluate_model(
    name,
    pipeline,
    X_test,
    y_test,
):

    predictions = pipeline.predict(
        X_test
    )

    probabilities = None

    if hasattr(
        pipeline,
        "predict_proba",
    ):

        probabilities = (
            pipeline.predict_proba(
                X_test
            )[:, 1]
        )

    metrics = {
        "accuracy": float(
            accuracy_score(
                y_test,
                predictions,
            )
        ),

        "precision": float(
            precision_score(
                y_test,
                predictions,
                zero_division=0,
            )
        ),

        "recall": float(
            recall_score(
                y_test,
                predictions,
                zero_division=0,
            )
        ),

        "f1": float(
            f1_score(
                y_test,
                predictions,
                zero_division=0,
            )
        ),
    }

    if (
        probabilities is not None
        and y_test.nunique() == 2
    ):

        metrics["roc_auc"] = float(
            roc_auc_score(
                y_test,
                probabilities,
            )
        )

    print(
        f"\n=============================="
    )

    print(
        f"MODEL: {name}"
    )

    print(
        "=============================="
    )

    print(
        "\nMetrics:"
    )

    for key, value in metrics.items():

        print(
            f"{key}: "
            f"{value:.4f}"
        )

    print(
        "\nConfusion matrix:"
    )

    print(
        confusion_matrix(
            y_test,
            predictions,
        )
    )

    print(
        "\nClassification report:"
    )

    print(
        classification_report(
            y_test,
            predictions,
            zero_division=0,
        )
    )

    return metrics


def main():

    df = load_data()

    validate_dataset(
        df
    )

    (
        X,
        y,
        numeric_features,
        categorical_features,
    ) = prepare_features(
        df
    )

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.25,
            random_state=42,
            stratify=y,
        )
    )

    print(
        "\nTrain rows:",
        len(X_train),
    )

    print(
        "Test rows:",
        len(X_test),
    )

    print(
        "\nFeatures:"
    )

    print(
        list(X.columns)
    )

    # ==========================================
    # Model 1 - Logistic Regression baseline
    # ==========================================

    logistic_preprocessor = (
        make_preprocessor(
            numeric_features,
            categorical_features,
        )
    )

    logistic_model = Pipeline(
        steps=[
            (
                "preprocessor",
                logistic_preprocessor,
            ),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )

    logistic_model.fit(
        X_train,
        y_train,
    )

    logistic_metrics = (
        evaluate_model(
            "Logistic Regression",
            logistic_model,
            X_test,
            y_test,
        )
    )

    # ==========================================
    # Model 2 - Random Forest
    # ==========================================

    rf_preprocessor = (
        make_preprocessor(
            numeric_features,
            categorical_features,
        )
    )

    random_forest = Pipeline(
        steps=[
            (
                "preprocessor",
                rf_preprocessor,
            ),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=10,
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    random_forest.fit(
        X_train,
        y_train,
    )

    rf_metrics = (
        evaluate_model(
            "Random Forest",
            random_forest,
            X_test,
            y_test,
        )
    )

    # ==========================================
    # Select by F1
    # ==========================================

    if (
        rf_metrics["f1"]
        >= logistic_metrics["f1"]
    ):

        best_name = (
            "Random Forest"
        )

        best_model = (
            random_forest
        )

        best_metrics = (
            rf_metrics
        )

    else:

        best_name = (
            "Logistic Regression"
        )

        best_model = (
            logistic_model
        )

        best_metrics = (
            logistic_metrics
        )

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        best_model,
        MODEL_FILE,
    )

    metadata = {
        "model_name":
            best_name,

        "model_file":
            MODEL_FILE.name,

        "training_rows":
            len(df),

        "train_rows":
            len(X_train),

        "test_rows":
            len(X_test),

        "target":
            TARGET,

        "features":
            list(
                X.columns
            ),

        "metrics":
            best_metrics,

        "source_policy":
            (
                "Government and "
                "verified public-authority "
                "data only"
            ),
    }

    with open(
        METRICS_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2,
        )

    print(
        "\n================================"
    )

    print(
        "BEST MODEL:",
        best_name,
    )

    print(
        "================================"
    )

    print(
        "\nSaved model:"
    )

    print(
        MODEL_FILE
    )

    print(
        "\nSaved metrics:"
    )

    print(
        METRICS_FILE
    )


if __name__ == "__main__":
    main()