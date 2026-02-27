# UGR Luminous Area Pack

Intent: regression-protect that UGR contributor weighting depends on luminous opening area.

Setup:
- Two luminaires use identical intensity distribution and flux.
- Luminous opening differs (small vs large rectangle).
- One fixed glare observer view is used with UGR debug contributor output.

Expected behavior:
- Small-opening luminaire contributes more to UGR than large-opening luminaire.
- Contributor ordering in `summary.ugr_debug.top_contributors` is deterministic.
