"""The estimation engine: consumes the ledger read-only, emits EstimateRange.

Per BASEMENT.md law L1, this module never emits a point estimate and never
asks a model to guess a number. Per the calibration experiment run this
session (experiments/calib/VERDICT.md), cost/duration/files-touched all
verdicted MARGINAL — wide but honestly-covered intervals — so v0 estimates
are computed and written to the ledger for calibration tracking, but the CLI
and hooks only DISPLAY them when a caller explicitly passes --show-shadow;
by default they remain shadow-mode (BASEMENT.md §3, "Guard" and "Brief" rows).
"""
