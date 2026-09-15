"""Run the context-feature tiers and score them on RANKING, not on ROI.

This is the harness for the one question run 11 left open. The bound it
established was about AUC, so the answer has to be about AUC too: a tier that
improves log-loss but not AUC has done nothing that was not already ruled out.

## The control, and what it caught

A logistic regression on elo_diff alone is a strictly monotone transform of
elo_diff, so it must rank games exactly as baseline Elo does. Run 12 asserted
that and it FAILED on the pooled sample: 0.68389 against 0.68532.

The cause is not a leak, and it is worth stating precisely because it qualifies
how run 11's bound should be read. The transform is monotone *within* a fit,
but this model refits at every season boundary, so five seasons are priced by
five different monotone transforms. Pooling them is not a monotone transform of
anything. Measured per season the control is an exact tie -- 0.00e+00 in all
five -- and only the pooled figure moves.

Two consequences, both load-bearing:

  1. The control is asserted PER SEASON (`per_season_control`). That is where
     the invariance actually holds, so that is where a leak would show up.
  2. The right yardstick for "did the new information help" is the ELO_ONLY
     TIER, not baseline Elo. Both carry the seasonal-refit effect; only one
     carries the features. Comparing a context tier against raw Elo would
     silently credit the features with the refit, which here is worth -0.0014
     AUC -- small, and pointed the other way, but it is not zero and this
     project has been bitten twelve times by a number that was not what the
     surrounding code assumed.

None of this rescues the recalibration family. Run 11's bound was about a
single fixed transform and is untouched; the seasonal-refit effect measured
here is two orders of magnitude short of the -0.046 gap to the market, and
negative besides.

## Comparisons, in descending order of how much they matter

  context vs market     the only one that could ever move the deployment gate.
  context vs elo_only   did the new information reorder anything at all?
  context vs baseline   reported for continuity with run 11's numbers.

Everything is measured on the COMMON SUBSET: games where the context model has
a fit and the market has a price. Baseline Elo is re-scored on that subset
rather than quoted from the full-window number, because the context model has
no fit during burn-in and comparing 1,942 games of Elo against 1,408 of context
would be a sample difference wearing a result's clothes.
"""
from __future__ import annotations

import pandas as pd

from sportsedge.backtest.discrimination import auc, auc_gap_bootstrap, _log_loss
from sportsedge.backtest.engine import backtest_nfl
from sportsedge.models.elo import NflEloModel
from sportsedge.models.features import ContextFeatureModel, TIER_ELO_ONLY, TIERS

CONTROL_TOLERANCE = 1e-9


def _common_subset(predictions: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(predictions)
    if "p_context" not in df.columns:
        return df.iloc[0:0]
    return df.dropna(subset=["p_model", "p_market", "p_context"])


def _tier_predictions(games: pd.DataFrame, tier: str, edge_threshold: float,
                      min_train_games: int) -> tuple[pd.DataFrame, ContextFeatureModel]:
    ctx = ContextFeatureModel(tier=tier, min_train_games=min_train_games)
    result = backtest_nfl(games, NflEloModel(), edge_threshold=edge_threshold,
                          context_model=ctx)
    return _common_subset(result["predictions"]), ctx


def per_season_control(df: pd.DataFrame) -> dict:
    """Within a season the elo_only fit is ONE monotone transform, so its AUC
    must equal baseline Elo's exactly. This is where a real leak would show."""
    rows = []
    for season, grp in df.groupby("season"):
        a_ctx, a_base = auc(grp["y"], grp["p_context"]), auc(grp["y"], grp["p_model"])
        rows.append({"season": str(season), "n": int(len(grp)),
                     "auc_elo_only": a_ctx, "auc_baseline": a_base,
                     "delta": a_ctx - a_base})
    return {
        "seasons": rows,
        "max_abs_delta": max((abs(r["delta"]) for r in rows), default=None),
        "ok": all(abs(r["delta"]) < CONTROL_TOLERANCE for r in rows) and bool(rows),
    }


def run_tier(games: pd.DataFrame, tier: str, edge_threshold: float = 0.03,
             min_train_games: int = 400,
             reference: pd.DataFrame | None = None) -> dict:
    """One walk-forward pass with a context model of `tier` riding along.

    `reference` is the elo_only tier's predictions on the same window; when
    given, the tier is also scored against it, which is the comparison that
    isolates the features from the seasonal refit.
    """
    df, ctx = _tier_predictions(games, tier, edge_threshold, min_train_games)
    if df.empty:
        return {"tier": tier, "n": 0,
                "note": "context model never reached a fit on this window"}

    y = df["y"].to_numpy()
    p_ctx, p_base, p_mkt = (df["p_context"].to_numpy(), df["p_model"].to_numpy(),
                            df["p_market"].to_numpy())

    vs_market = auc_gap_bootstrap(y, p_ctx, p_mkt)
    vs_base = auc_gap_bootstrap(y, p_ctx, p_base)

    out = {
        "tier": tier,
        "features": list(ctx.feature_names),
        "n": int(len(df)),
        "n_train_final": ctx.n_train,
        "coefficients": ctx.coefficients,
        "auc": {"context": auc(y, p_ctx), "baseline_elo": auc(y, p_base),
                "market": auc(y, p_mkt)},
        "log_loss": {"context": _log_loss(y, p_ctx),
                     "baseline_elo": _log_loss(y, p_base),
                     "market": _log_loss(y, p_mkt)},
        # Signed so POSITIVE always means "context ranks better than the thing
        # it is named against".
        "vs_market": {"gap": vs_market["gap"], "ci95": vs_market["ci95"],
                      "share_better": vs_market["share_model_ranks_better"]},
        "vs_baseline_elo": {"gap": vs_base["gap"], "ci95": vs_base["ci95"],
                            "share_better": vs_base["share_model_ranks_better"]},
        "beats_market": bool(vs_market["ci95"][0] > 0),
    }

    if reference is not None and not reference.empty and tier != TIER_ELO_ONLY:
        merged = df.merge(reference[["game_id", "p_context"]], on="game_id",
                          suffixes=("", "_ref"))
        # Never assume the two passes lined up; a tier that silently evaluated
        # a different set of games would look like a result.
        if len(merged) != len(df):
            raise ValueError(
                f"tier {tier!r} evaluated {len(df)} games but aligns with only "
                f"{len(merged)} of the elo_only reference; the subsets differ")
        vs_ctrl = auc_gap_bootstrap(merged["y"].to_numpy(),
                                    merged["p_context"].to_numpy(),
                                    merged["p_context_ref"].to_numpy())
        out["vs_elo_only"] = {"gap": vs_ctrl["gap"], "ci95": vs_ctrl["ci95"],
                              "share_better": vs_ctrl["share_model_ranks_better"]}
        out["beats_elo_only"] = bool(vs_ctrl["ci95"][0] > 0)

    return out


DEFAULT_C_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)


def regularization_sweep(games: pd.DataFrame, tiers: tuple[str, ...] = ("schedule", "weather", "qb"),
                         c_grid: tuple[float, ...] = DEFAULT_C_GRID,
                         edge_threshold: float = 0.03,
                         min_train_games: int = 400, draws: int = 2000) -> dict:
    """Turns "your fit was overfit" from an argument into a measurement.

    The obvious objection to a tier ranking WORSE than the control is that the
    logistic fit is chasing noise in a few hundred training games. If that were
    the whole story, shrinking the coefficients would recover the control and
    then some. So sweep the L2 penalty and look for ANY setting at which a tier
    ranks better than elo_only.

    One honest caveat on how to read the small-C end: the penalty is not
    selective, so it crushes `elo_diff` along with the context features. That is
    why C = 0.001 collapses every tier's AUC toward 0.5 -- those rows are not
    "context, shrunk", they are "the whole model, shrunk", and they say nothing
    about the features. The informative region is the middle of the grid, where
    elo_diff survives roughly intact and the context terms are the ones being
    pulled in.
    """
    control_df, _ = _tier_predictions(games, TIER_ELO_ONLY, edge_threshold,
                                      min_train_games)
    ref = control_df[["game_id", "p_context"]].rename(columns={"p_context": "p_ref"})

    rows = []
    for tier in tiers:
        for c in c_grid:
            ctx = ContextFeatureModel(tier=tier, min_train_games=min_train_games, C=c)
            res = backtest_nfl(games, NflEloModel(), edge_threshold=edge_threshold,
                               context_model=ctx)
            df = _common_subset(res["predictions"]).merge(ref, on="game_id")
            y = df["y"].to_numpy()
            boot = auc_gap_bootstrap(y, df["p_context"].to_numpy(),
                                     df["p_ref"].to_numpy(), draws=draws)
            rows.append({
                "tier": tier, "C": c, "n": int(len(df)),
                "auc": auc(y, df["p_context"].to_numpy()),
                "log_loss": _log_loss(y, df["p_context"].to_numpy()),
                "gap_vs_elo_only": boot["gap"], "ci95": boot["ci95"],
                "beats_control": bool(boot["ci95"][0] > 0),
            })

    best = max(rows, key=lambda r: r["gap_vs_elo_only"])
    return {
        "rows": rows,
        "best_gap_vs_elo_only": best,
        "any_setting_beats_control": any(r["beats_control"] for r in rows),
        # The headline the sweep exists to produce. A negative maximum across
        # the whole grid means no penalty strength rescues these features.
        "max_gap_vs_elo_only": best["gap_vs_elo_only"],
    }


def context_report(games: pd.DataFrame, tiers: tuple[str, ...] = TIERS,
                   edge_threshold: float = 0.03,
                   min_train_games: int = 400) -> dict:
    control_df, _ = _tier_predictions(games, TIER_ELO_ONLY, edge_threshold,
                                      min_train_games)
    control = per_season_control(control_df) if not control_df.empty else {"ok": False}

    tier_results = [run_tier(games, t, edge_threshold, min_train_games,
                             reference=control_df) for t in tiers]
    by_tier = {r["tier"]: r for r in tier_results}

    # The seasonal-refit effect, isolated: a pure recalibration's pooled AUC
    # minus baseline Elo's. Reported because it is the confound that the
    # elo_only yardstick exists to remove.
    refit_effect = None
    ctrl = by_tier.get(TIER_ELO_ONLY)
    if ctrl and ctrl.get("n"):
        refit_effect = ctrl["auc"]["context"] - ctrl["auc"]["baseline_elo"]

    return {
        "per_season_control": control,
        "control_ok": bool(control.get("ok")),
        "pooled_seasonal_refit_auc_effect": refit_effect,
        "tiers": tier_results,
        "verdict": _verdict(by_tier),
    }


def _verdict(by_tier: dict) -> str:
    deployable = by_tier.get("schedule") or {}
    if not deployable.get("n"):
        return "no tier produced a usable fit."
    if deployable.get("beats_market"):
        return ("the schedule tier ranks games significantly better than the closing "
                "line. This is the first candidate the deployment gate has seen; "
                "re-run it out-of-sample before anything is flipped.")
    any_beats_ctrl = any(t.get("beats_elo_only") for t in by_tier.values())
    if any_beats_ctrl:
        return ("context improves on the elo_only control's ranking but does NOT "
                "reach the closing line. The information is real and insufficient; "
                "the gate stays shut.")
    return ("no tier significantly improves on the elo_only control. The "
            "pre-kickoff context nflverse ships does not carry the information "
            "the model is missing.")
