# Vendored third-party code

| File(s) | Package | Version | Source | Licence |
|---|---|---|---|---|
| `three.module.min.js`, `three.core.min.js` | [three.js](https://threejs.org/) | 0.180.0 | npm registry (`npm pack three@0.180.0`), files `build/three.module.min.js` and `build/three.core.min.js` | MIT — see `LICENSE` |
| `OrbitControls.js` | three.js examples | 0.180.0 | same tarball, `examples/jsm/controls/OrbitControls.js` | MIT — same `LICENSE` |

Copied unmodified. They are vendored rather than loaded from a CDN because the demo machine may have
no internet access. `three` is resolved through the import map in `webapp/index.html`, so
`OrbitControls.js` keeps its original `import ... from 'three'` line untouched.

No 3D models, textures or fonts are shipped: the warehouse, the robot and every label are built from
three.js primitives and canvas-drawn textures at runtime, so there is no asset of unknown provenance.
