---
name: ml-model-development
description: "Train, evaluate, and ship a classical machine-learning model (tabular classification or regression, ranking, or forecasting) with a cost-aware metric, a simple baseline first, leak-free time-based or grouped splits, reproducible runs, one shared feature path for training and serving, fairness checks, input validation, drift monitoring, and a shadow or A/B rollout. Use when building, retraining, or debugging a predictive model. Not for LLM features (use the build-llm-feature and llm-eval-harness skills)."
---

# ML Model Development

Ship a predictive model that is better than a simple rule on data it has never
seen, and stays honest in production. The stance is **baseline first, leakage
never**: a model ships only when it beats a simple baseline on a split that
mirrors how it will be used, in a run someone else can reproduce.

## When to use

- Building a model that predicts, classifies, scores, ranks, or forecasts from
  tabular or event data (churn, fraud, lead scoring, demand, arrival times).
- Retraining a model, adding features, or changing its algorithm.
- A model that scored well offline performs badly in production, which often
  means leakage or training-serving skew.

## When not to use

- Features backed by a language model: use the `build-llm-feature` skill, and
  the `llm-eval-harness` skill to evaluate them.
- Document search or embedding retrieval: use the `build-retrieval` skill.
- A one-off question answered from data: use the `analyze-data` skill.
- The warehouse pipeline that produces training tables: use the
  `data-pipeline-design` skill.
- Checking feasibility before committing: use the `prototype-spike` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- The decision the model drives, who acts on each prediction, the cost of each
  error type, and whether scoring is batch or per request (with its latency
  budget, from the project's SLO).
- The label: its definition, its source, and when it becomes known relative to
  the moment of prediction.
- Data sources, time span, volume, class balance, and the entity (user,
  account, device, store) and whether it appears in many rows.
- The existing stack from manifests and lockfiles: libraries and versions,
  experiment tracker (for example MLflow or Weights & Biases) if any, feature
  store, model registry, and serving path.
- Groups relevant to fairness, legal or policy limits on features and
  decisions, and who signs off.
- Test and lint commands from `AGENTS.md`, package scripts, or the `Makefile`.

## Workflow

1. **Define the decision and a metric that reflects its cost.** Write: "at
   time T, for each entity, predict Y over horizon H; act when the score
   passes a threshold." Then choose metrics:
   - Imbalanced classification: precision and recall at the operating
     threshold, and precision-recall AUC. Never accuracy alone: with 1% fraud,
     always predicting "not fraud" is 99% accurate.
   - Scores used as probabilities (pricing, expected value, combining
     models): check calibration with a reliability curve, Brier score, or log
     loss.
   - Pick the threshold that minimizes false positives times their cost plus
     false negatives times theirs, or from capacity (a team that reviews 200
     cases a day needs precision in the top 200).
   - Regression: MAE or RMSE (RMSE punishes large errors more); MAPE breaks
     near zero. Ranking: nDCG@k or precision@k. Forecasting: error per horizon
     against a seasonal naive forecast.
   Agree the metric and target with the decision owner.
2. **Build a simple baseline first:** the current rule or heuristic (or the
   majority class, last value, or seasonal naive), then logistic or linear
   regression, then gradient-boosted trees. Anything more complex must beat
   the best simple model on the decision metric by a margin that matters,
   with fold spread or an interval to show it is real.
3. **Split without leakage.** The split mirrors production use:
   - Temporal data: train on the past and test on later prediction points. A
     training row is usable only if its label was known by the cutoff; leave a
     gap before the test window that matches the delay between training and
     deployment.
   - Repeated entities: split by group so each user, patient, or device lands
     in one fold only.
   - Fit imputers, scalers, encoders, target encodings, and feature selection
     on training folds only, inside a pipeline, never on the full dataset.
   - Target leakage: no feature computed after the prediction point (a refund
     flag when predicting chargebacks, a closure date when predicting churn,
     aggregates over all history). Build features with point-in-time (as-of)
     joins and record each feature's source timestamp.
   - Remove exact duplicates across splits, and keep a final test set used once
     per decision. A score that looks too good, or one feature that dominates
     importance, is a leakage suspect until proven otherwise.
4. **Cross-validate to match the split:** expanding or rolling time windows for
   temporal data, grouped folds for entities, stratified folds for
   independent imbalanced rows (for example scikit-learn's `TimeSeriesSplit`,
   `GroupKFold`, and `StratifiedKFold`). Report the mean and spread across
   folds. Tune hyperparameters on validation folds only, never on the test set.
5. **Make runs reproducible.** Fix and record seeds; pin the data (a dated
   snapshot, a query with an as-of timestamp, a file hash, or the project's
   data versioning tool); record library versions, code commit, feature list,
   hyperparameters, training window, and per-fold metrics. Use the project's
   experiment tracker if it has one; otherwise write a run record next to the
   artifact. Some multithreaded or GPU training is not bit-for-bit
   deterministic, so expect reruns to match within noise.
6. **Keep training and serving features identical.** One feature code path (a
   shared module or the feature store) feeds both training and serving; never
   reimplement features in the service. Match missing-value defaults,
   unknown-category handling, units, and time zones. Save preprocessing and
   model together as one artifact, and test parity by computing features for a
   sample of entities through both paths.
7. **Document limits and check fairness.** Evaluate per relevant segment
   (region, platform, new versus long-standing customers, and protected or
   proxy groups where policy requires it and the data is lawfully available):
   the main metric, false positive and false negative rates, and calibration.
   Watch for proxies of protected attributes such as postal code. Write
   model-card notes: intended and out-of-scope uses, training data and window,
   overall and per-segment results, known limits, owner, and retraining
   cadence. For regulated decisions (credit, hiring, insurance, health), ask
   the owner about legal review before shipping.
8. **Package and serve with validation.** Version the artifact in the
   registry or a versioned path, linked to its run record. Load artifacts only
   from storage you control, since pickle-based formats run code on load.
   Validate every input at serving (schema, types, ranges, allowed categories,
   required fields) and reject it or fall back to the baseline rule instead of
   scoring garbage. Return the model version with each prediction, and log
   predictions with version and request ID, not raw personal data.
9. **Monitor and plan retraining and rollback.** Track feature drift against
   the training distribution (for example population stability index or
   quantile comparisons), missing-value rates, unseen categories, the score
   distribution, and the share over the threshold; once labels arrive, track
   live performance by segment. Use the `observability-setup` skill for
   metrics and alerts with owners. Define the retraining trigger (schedule or
   drift) with the same evaluation gate, and keep the previous version
   deployable behind a configuration or registry switch.
10. **Roll out in shadow, then A/B.** In shadow, the candidate scores live
    traffic beside the current model or rule and its predictions are logged
    but not acted on; compare distributions, then performance as labels
    arrive. Then run an A/B test or staged rollout on the business outcome,
    with guardrail metrics and stop criteria agreed in advance; use the
    `deployment-safety` skill for the stages. Each production step needs
    approval.

## Worked example: time-based split and leakage checks (illustrative)

Standard library only. It assumes the feature pipeline records, for each
feature, the newest source timestamp it used.

```python
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Example:
    entity_id: str
    predict_at: datetime                # when the model would have scored this row
    label_known_at: datetime            # when the outcome became known
    feature_as_of: dict[str, datetime]  # newest source timestamp behind each feature


def time_split(rows: list[Example], cutoff: datetime, gap: timedelta,
               test_end: datetime) -> tuple[list[Example], list[Example]]:
    """Train on what was knowable at the cutoff; test on later prediction points."""
    train = [r for r in rows if r.predict_at < cutoff and r.label_known_at <= cutoff]
    test = [r for r in rows if cutoff + gap <= r.predict_at < test_end]
    return train, test


def leaked_features(rows: list[Example]) -> Counter[str]:
    """Count rows where a feature used data from after the prediction point."""
    return Counter(name for r in rows for name, as_of in r.feature_as_of.items()
                   if as_of > r.predict_at)


def shared_entities(train: list[Example], test: list[Example]) -> set[str]:
    """Must be empty when the split is grouped by entity."""
    return {r.entity_id for r in train} & {r.entity_id for r in test}


day = timedelta(days=1)
t0 = datetime(2026, 1, 1)
rows = [
    Example("a", t0, t0 + 30 * day, {"orders_90d": t0, "refund_flag": t0 + 10 * day}),
    Example("b", t0 + 20 * day, t0 + 50 * day, {"orders_90d": t0 + 20 * day}),
    Example("c", t0 + 70 * day, t0 + 100 * day, {"orders_90d": t0 + 70 * day}),
]
train, test = time_split(rows, cutoff=t0 + 40 * day, gap=14 * day, test_end=t0 + 120 * day)
print([r.entity_id for r in train], [r.entity_id for r in test])  # ['a'] ['c']
print(leaked_features(rows))         # Counter({'refund_flag': 1})
print(shared_entities(train, test))  # set()
```

Row `b` is excluded from training because its label was not known at the
cutoff, and `refund_flag` is flagged because it uses data from after `a` was
scored. If scikit-learn is installed, a pipeline keeps preprocessing inside
each fold:

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def baseline_scores(X, y, numeric: list[str], categorical: list[str]):
    """X (a DataFrame) and y sorted by prediction time; preprocessing refits per fold."""
    preprocess = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])
    model = make_pipeline(preprocess, LogisticRegression(max_iter=1000))
    return cross_val_score(model, X, y, cv=TimeSeriesSplit(n_splits=5),
                           scoring="average_precision")
```

`TimeSeriesSplit` splits by row position and does not know when labels
matured; use its `gap` option (check your scikit-learn version) or a custom
splitter like `time_split` when labels arrive late.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  replacing the serving model, changing live traffic splits, writing to a
  production registry stage, and large paid training jobs.
- Never weaken a test, check, or threshold to make work pass. Never tune on
  the test set, and never report accuracy alone on imbalanced data.
- Train only on approved sources in approved environments. Do not copy
  production personal data to laptops or commit notebooks with row-level
  outputs. Store protected attributes used for fairness checks separately,
  with restricted access, and use them as features only where policy and law
  allow.
- Load model artifacts only from trusted storage.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Unit tests for the shared feature code, including missing values and unknown
  categories.
- Leakage checks pass: no feature newer than its prediction point, no shared
  entities in a grouped split, and preprocessing fit inside the pipeline.
- The candidate beats the baseline on the decision metric across validation
  folds, then once on the test set, with spread or an interval reported.
- Parity test: features computed by the training and serving paths match on a
  sample of entities.
- Serving tests: malformed, missing, out-of-range, and unknown-category inputs
  are rejected or fall back as designed.
- A rerun from the recorded configuration reproduces metrics within noise.
- Lint, type check, and the test suite pass.

## Report

- **Decision and metric:** the decision, metric, threshold, and why.
- **Data:** sources, window, snapshot or version, label definition, and class
  balance.
- **Split and leakage:** split method, cross-validation scheme, and leakage
  checks run.
- **Results:** baseline versus candidate per fold and on the test set, per
  segment, and calibration where scores are used as probabilities.
- **Reproducibility:** commit, data version, seeds, library versions,
  hyperparameters, and run ID.
- **Serving:** artifact and version, shared feature path, input validation, and
  fallback.
- **Monitoring and rollout:** drift metrics, alerts, retraining trigger,
  rollback switch, and the shadow and A/B plan.
- **Model card:** where the notes live.
- **Not verified:** checks that could not run and why (for example labels not
  yet available for shadow predictions).

## Optional delegation

The `data-engineer` subagent can review the training-data pipeline for
point-in-time correctness and late data. The `test-writer` subagent can write
the parity and input-validation tests, and the `performance-profiler` subagent
can measure serving latency. The workflow above stays complete for a single
agent.
