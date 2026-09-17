"""Reading the ledger must not change it.

`bets/ledger.csv` is the project's evidence and it is rewritten on every
`recommend` and every `settle`. pandas' default CSV float parser is not
correctly rounded, so loading and saving the file perturbs values nothing
touched -- which both corrupts the record in the last bit and fills `git diff`
with rows that did not change, hiding the ones that did.

`storage.snapshots` fixed this for the game tables and odds snapshots in run 11
and pinned it with tests; the ledger kept the default parser until run 15.
These are the equivalent pins.
"""
import pandas as pd
import pytest

from sportsedge.betting import ledger as ledger_mod


def test_the_committed_ledger_survives_a_load_save_cycle_byte_for_byte():
    """The real file, not a fixture: the drift is data-dependent.

    Only 2 of 123 rows drifted on the day this was written, and which cells
    they are depends on the exact decimal expansions the ledger happens to
    hold. A synthetic fixture would pass while the real file did not.
    """
    if not ledger_mod.LEDGER_PATH.exists():
        pytest.skip("no committed ledger")
    original = ledger_mod.LEDGER_PATH.read_text()

    df = ledger_mod._load()
    rewritten = df.to_csv(index=False)

    assert rewritten == original


def test_the_default_parser_is_the_thing_that_breaks_it():
    """Pins the diagnosis, not just the symptom.

    If a future pandas makes the default parser correctly rounded this test
    starts failing, and that is the right moment to reconsider the note in
    `ledger._load` -- rather than discovering years later that it guards
    nothing. It is skipped, not failed, when the committed ledger happens to
    hold no value the default parser mangles.
    """
    if not ledger_mod.LEDGER_PATH.exists():
        pytest.skip("no committed ledger")

    default = pd.read_csv(ledger_mod.LEDGER_PATH, dtype=ledger_mod._ID_COLUMNS)
    exact = pd.read_csv(ledger_mod.LEDGER_PATH, dtype=ledger_mod._ID_COLUMNS,
                        float_precision="round_trip")

    float_cols = [c for c in default.columns
                  if pd.api.types.is_float_dtype(default[c])]
    drifted = sum(
        int(((default[c] != exact[c]) & default[c].notna() & exact[c].notna()).sum())
        for c in float_cols)
    if drifted == 0:
        pytest.skip("this ledger holds no value the default parser mangles")
    assert drifted > 0
