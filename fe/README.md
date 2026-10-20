# Frontend

Web UI for the spine MRI segmentation system. React, TypeScript, Vite and NiiVue. The API follows `docs/spec.md`.

User guide (Vietnamese): [docs/huong-dan-su-dung.md](docs/huong-dan-su-dung.md)

## Run

Node 22.18 or newer. Use two terminals:

```bash
cd fe
npm install
npm run mock    # fake backend on port 8000
npm run dev     # open http://localhost:5173
```

The mock uses the sample data in `ai/demo`.

## Use the real backend

Stop the mock and run the backend on port 8000. If the backend runs somewhere else, create `fe/.env.local`:

```
VITE_PROXY_TARGET=http://<host>:<port>
```

Check that the backend matches the spec:

```bash
npm run check:api -- http://<host>:<port>/api/v1
```

## Build

```bash
npm run build
```

Output is in `dist/`. The backend must return `index.html` for every path that does not start with `/api`.

## Notes for backend and AI

- This branch only changes `fe/`.
- If the API changes, update `docs/spec.md` first, then `src/types.ts` and `src/api/validate.ts`.
- The mock and `check:api` read `ai/demo/0100_seg.nii.gz` and `ai/demo/analysis_0100.json`. Tell the FE team if these files move.
