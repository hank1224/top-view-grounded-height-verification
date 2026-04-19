# Package Drawings Dataset

This directory contains the value-only package drawing dataset imported from:

```text
other_repo/test_0402
```

It contains 15 package types with two numeric value variants each:

- `canonical-values`
- `rotated-values`

That gives 30 images total. ID-only variants and raw Notion export files are not copied because the verifier pipeline only consumes numeric value images.

Each image manifest row includes package-level `shape_class` metadata. Current classes:

- `sot_like_smd`
- `tabbed_power_smd`
- `two_terminal_diode_smd`

## Licensing

This dataset is licensed under:

```text
CC-BY-SA-4.0 WITH KiCad-libraries-exception
```

See [`../../LICENSE`](../../LICENSE).
