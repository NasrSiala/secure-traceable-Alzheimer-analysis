"""Diagnostic label aggregation for PTB-XL."""

from collections import Counter

import pandas as pd


DIAGNOSTIC_CLASSES = ("NORM", "MI", "STTC", "CD", "HYP")


def summarize_diagnostics(metadata, statements, splits):
    """Count ECGs by diagnostic superclass for each dataset split.

    An ECG is counted at most once per superclass.
    ECGs without a recognized positive diagnostic code are reported
    separately as having no recognized diagnostic labels.
    """
    required_statement_columns = {"diagnostic", "diagnostic_class"}
    missing = required_statement_columns.difference(statements.columns)

    if missing:
        raise ValueError(
            f"Missing statement columns: {sorted(missing)}"
        )

    diagnostic_statements = statements[
        (pd.to_numeric(statements["diagnostic"], errors="coerce") == 1)
        & statements["diagnostic_class"].isin(DIAGNOSTIC_CLASSES)
    ]

    code_to_class = diagnostic_statements["diagnostic_class"].to_dict()

    results = []

    for split_name, split_metadata in splits.items():
        class_counts = Counter()
        labeled_ecgs = 0

        for codes in split_metadata["scp_codes"]:
            recognized_classes = set()

            if isinstance(codes, dict):
                for code, score in codes.items():
                    try:
                        positive = float(score) > 0
                    except (TypeError, ValueError):
                        positive = False

                    if positive and code in code_to_class:
                        recognized_classes.add(code_to_class[code])

            if recognized_classes:
                labeled_ecgs += 1

            for diagnostic_class in recognized_classes:
                class_counts[diagnostic_class] += 1

        total_ecgs = len(split_metadata)

        for diagnostic_class in DIAGNOSTIC_CLASSES:
            results.append({
                "split": split_name,
                "total_ecgs": total_ecgs,
                "labeled_ecgs": labeled_ecgs,
                "unlabeled_ecgs": total_ecgs - labeled_ecgs,
                "diagnostic_class": diagnostic_class,
                "class_count": class_counts[diagnostic_class],
            })

    return pd.DataFrame(results)
