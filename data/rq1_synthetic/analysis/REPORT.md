# Synthetic RQ1 Planner × Execution Study

SYNTHETIC — NOT PHYSICALLY IDENTIFIED. All uncertainty is descriptive layout-level percentile bootstrap (95%, 5,000 resamples); no hypothesis tests, significance claims, or GO/NO-GO decision are made here.

## Frozen provenance

- Lock: `355a6b600b50409b680ffb0e06ee53d75e1a915fb3142bddfb3a3a3180f9c8d5`
- Protocol/layout/schedule hashes: `9c3e40dddda4d9427dc4c460f2c06b114b565da0408f75ba7ad5cb287335bcd6` / `73d2d255b460fd09a07b3d2a078ba6e60fac65867e65e8d15af4e8e122421ef6` / `490176d278fa4898ef71ce08b3d2b4675644b348ab66a6f842bf121261803cb6`
- Seeds: layouts 20260826; schedule 20260827; bootstrap 20260828.
- 880 valid locked episodes and readable traces: 440 discovery, 440 holdout.
- TR is official `dwa_local_planner/DWAPlannerROS` with `planner.use_dwa: false`; TEB is official `teb_local_planner/TebLocalPlannerROS`.
- Preflight records static checks, one TR/E0 executor probe, and TR/TEB × E0/E1 restart determinism. Each retained episode independently passed timing, executed-feedback, command-hold, and collision-truth contracts.
- Attempts: `{'algorithm': 880}`. Exclusions: none; algorithm outcomes remain terminal observations.

## Separate discovery and holdout summaries

`descriptive.csv` reports each partition separately for success, normalized global-path progress, and terminal-reason composition. `paired_effects.csv` contains within-planner profile-minus-E0 changes for success and progress. `interaction_contrasts.csv` contains TEB-minus-TR profile-minus-E0 contrasts. The four figures retain the same profile order and separate discovery from holdout.

Discovery, partition × planner (`E0` then all-profile aggregate plus terminal counts): `{'tr': {'e0_success_rate': 0.65, 'e0_mean_normalized_path_progress': 0.694135, 'all_profile_success_rate': 0.627273, 'all_profile_mean_normalized_path_progress': 0.684699, 'terminal_reasons': {'external_tolerance': 138, 'footprint_collision': 3, 'logical_timeout': 79}}, 'teb': {'e0_success_rate': 0.95, 'e0_mean_normalized_path_progress': 0.957929, 'all_profile_success_rate': 0.922727, 'all_profile_mean_normalized_path_progress': 0.951945, 'terminal_reasons': {'external_tolerance': 203, 'footprint_collision': 2, 'logical_timeout': 1, 'plugin returned no valid velocity command': 14}}}`.

Holdout, partition × planner (`E0` then all-profile aggregate plus terminal counts): `{'tr': {'e0_success_rate': 0.6, 'e0_mean_normalized_path_progress': 0.694652, 'all_profile_success_rate': 0.586364, 'all_profile_mean_normalized_path_progress': 0.68843, 'terminal_reasons': {'external_tolerance': 129, 'footprint_collision': 5, 'logical_timeout': 84, 'plugin returned no valid velocity command': 2}}, 'teb': {'e0_success_rate': 0.9, 'e0_mean_normalized_path_progress': 0.94578, 'all_profile_success_rate': 0.881818, 'all_profile_mean_normalized_path_progress': 0.941657, 'terminal_reasons': {'external_tolerance': 194, 'footprint_collision': 1, 'plugin returned no valid velocity command': 25}}}`.

Terminal reasons over all locked episodes: `{'external_tolerance': 664, 'footprint_collision': 11, 'logical_timeout': 164, 'plugin returned no valid velocity command': 41}`.

This report is the endpoint of the synthetic execution run and stops for primary scientific review.
