# GM website

The product page for [GM](https://github.com/edreisMD/finegrain), built with React, Vinext, and Sites. It uses a GM monogram, a deep navy and cool blue palette, and an original animated grid inspired by the hackathon page.

Requires Node.js 22.13 or newer.

```sh
npm ci
npm run dev
```

`npm run build` produces the deployment. `npx tsc --noEmit` checks types. `npx oxlint app --deny-warnings` checks the product code; the vendored component catalog retains its upstream lint findings.

The page is in `app/page.tsx`, styling in `app/globals.css`, and the procedural grid in `app/grain-field.tsx`. The grid stops after 4.5 seconds and respects reduced-motion preferences. All product text and links work without JavaScript.

The Sites project identity is recorded in `.openai/hosting.json`. Publication uses an isolated copy of this directory as its source repository; the project monorepo remains the canonical editable source. No credentials belong in either repository.
