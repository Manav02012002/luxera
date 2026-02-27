# Desktop Dev Workspace (pnpm + Turborepo)

This repo now supports a JavaScript/TypeScript workspace at the root **without changing Python workflows**.

## Install JS toolchain

From repo root:

```bash
pnpm install
```

Note: in this execution environment, outbound npm registry access may be blocked. Run install on a normal networked machine.

## Desktop app development

Workspace layout is configured for:

- `apps/*`
- `packages/*`

When a desktop app package exists (for example `apps/desktop`), start it with:

```bash
pnpm dev
```

Other monorepo tasks:

```bash
pnpm build
pnpm lint
pnpm typecheck
pnpm test
```

For baseline workspace verification before real JS apps/packages exist:

```bash
pnpm -r run typecheck
```

## Python workflows (unchanged)

Run Python tests exactly as before:

```bash
pytest -q
```

Run Luxera compute/CLI exactly as before:

```bash
luxera run-all examples/indoor_office/office.luxera.json --job office_direct --report --bundle
# or
python -m luxera.cli run-all examples/indoor_office/office.luxera.json --job office_direct --report --bundle
```

No Python packaging or schema files were changed by this workspace setup.

## If pnpm install fails (DNS / blocked network)

Check DNS:

```bash
nslookup registry.npmjs.org
```

Ensure registry is set:

```bash
pnpm config set registry https://registry.npmjs.org/
```

If your environment uses a proxy, configure npm/pnpm proxy settings (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, or pnpm proxy config) before retrying.
