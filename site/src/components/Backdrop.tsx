import { useEffect, useRef } from "react";

// Ambient 3D "speedup trajectory field" (a reimagining of the paper's Fig. 21).
// Many runs climb left→right (iterations) and up (speedup), spread across the full
// width and depth, each in its own hue, with a glowing comet flowing along it.
// Client-only: three is dynamic-imported inside the effect so it never runs in SSR.
export default function Backdrop({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    let disposed = false;
    let cleanup = () => {};

    (async () => {
      let THREE: typeof import("three");
      try {
        THREE = await import("three");
      } catch {
        return;
      }
      if (disposed || !ref.current) return;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 240);
      camera.position.set(0, 6, 30);

      let renderer: import("three").WebGLRenderer;
      try {
        renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
      } catch {
        return; // no WebGL — skip gracefully
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

      const resize = () => {
        const w = canvas.clientWidth || 1;
        const h = canvas.clientHeight || 1;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
      };
      resize();
      window.addEventListener("resize", resize);

      const group = new THREE.Group();
      scene.add(group);

      const RUNS = 130;
      const SEG = 84;
      const X0 = -52; // extends well past the visible frame → no cutoff at the edges
      const X1 = 52;
      const MAXH = 17;
      const tmp = new THREE.Color();

      const smoothstep = (a: number, b: number, x: number) => {
        const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
        return t * t * (3 - 2 * t);
      };

      const runPoints: number[][][] = [];
      const cometHue: number[] = [];
      const lineMats: import("three").LineBasicMaterial[] = [];
      const lineGeos: import("three").BufferGeometry[] = [];

      for (let r = 0; r < RUNS; r++) {
        const z = THREE.MathUtils.lerp(-24, 24, r / (RUNS - 1)) + (Math.random() - 0.5) * 1.2;
        const finalH = Math.pow(Math.random(), 2.2) * MAXH + 0.2;
        // golden-ratio hue spread → a wide, evenly distributed range of colors
        const hue = (r * 0.61803398875 + Math.random() * 0.04) % 1;
        cometHue.push(hue);
        const s1 = 0.04 + Math.random() * 0.25;
        const e1 = s1 + 0.1 + Math.random() * 0.25;
        const s2 = Math.min(0.9, e1 + Math.random() * 0.15);
        const e2 = Math.min(0.99, s2 + 0.1 + Math.random() * 0.2);

        const positions = new Float32Array(SEG * 3);
        const colors = new Float32Array(SEG * 3);
        const pts: number[][] = [];
        for (let i = 0; i < SEG; i++) {
          const t = i / (SEG - 1);
          const x = THREE.MathUtils.lerp(X0, X1, t);
          const y = finalH * (0.58 * smoothstep(s1, e1, t) + 0.42 * smoothstep(s2, e2, t));
          positions[i * 3] = x;
          positions[i * 3 + 1] = y;
          positions[i * 3 + 2] = z;
          // dim at the bottom, bright at the top, in this line's hue
          tmp.setHSL(hue, 0.78, THREE.MathUtils.lerp(0.22, 0.62, Math.min(1, y / MAXH)));
          colors[i * 3] = tmp.r;
          colors[i * 3 + 1] = tmp.g;
          colors[i * 3 + 2] = tmp.b;
          pts.push([x, y, z]);
        }
        runPoints.push(pts);

        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        const mat = new THREE.LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.62,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        group.add(new THREE.Line(geo, mat));
        lineMats.push(mat);
        lineGeos.push(geo);
      }

      // flowing comets — one bright point per run, traveling its path on a loop
      const cometPos = new Float32Array(RUNS * 3);
      const cometCol = new Float32Array(RUNS * 3);
      const phases = new Float32Array(RUNS);
      const speeds = new Float32Array(RUNS);
      for (let r = 0; r < RUNS; r++) {
        phases[r] = Math.random();
        speeds[r] = 0.03 + Math.random() * 0.05;
        tmp.setHSL(cometHue[r], 0.85, 0.7);
        cometCol[r * 3] = tmp.r;
        cometCol[r * 3 + 1] = tmp.g;
        cometCol[r * 3 + 2] = tmp.b;
      }
      const cometGeo = new THREE.BufferGeometry();
      cometGeo.setAttribute("position", new THREE.BufferAttribute(cometPos, 3));
      cometGeo.setAttribute("color", new THREE.BufferAttribute(cometCol, 3));
      const cometMat = new THREE.PointsMaterial({
        size: 0.42,
        vertexColors: true,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const comets = new THREE.Points(cometGeo, cometMat);
      group.add(comets);

      let mx = 0;
      let my = 0;
      const onMove = (e: MouseEvent) => {
        mx = e.clientX / window.innerWidth - 0.5;
        my = e.clientY / window.innerHeight - 0.5;
      };
      window.addEventListener("mousemove", onMove);

      const cpos = cometGeo.getAttribute("position") as import("three").BufferAttribute;
      let raf = 0;
      let tElapsed = 0;
      const tick = () => {
        tElapsed += 0.016;
        for (let r = 0; r < RUNS; r++) {
          phases[r] = (phases[r] + speeds[r] * 0.016) % 1;
          const pts = runPoints[r];
          const f = phases[r] * (pts.length - 1);
          const i0 = Math.floor(f);
          const i1 = Math.min(pts.length - 1, i0 + 1);
          const lf = f - i0;
          const a = pts[i0];
          const b = pts[i1];
          cpos.array[r * 3] = a[0] + (b[0] - a[0]) * lf;
          cpos.array[r * 3 + 1] = a[1] + (b[1] - a[1]) * lf;
          cpos.array[r * 3 + 2] = a[2] + (b[2] - a[2]) * lf;
        }
        cpos.needsUpdate = true;

        group.rotation.y = Math.sin(tElapsed * 0.07) * 0.16;
        camera.position.x += (mx * 7 - camera.position.x) * 0.02;
        camera.position.y += (6 - my * 4 - camera.position.y) * 0.02;
        camera.lookAt(0, 5, 0);
        renderer.render(scene, camera);
        raf = requestAnimationFrame(tick);
      };
      tick();

      cleanup = () => {
        cancelAnimationFrame(raf);
        window.removeEventListener("resize", resize);
        window.removeEventListener("mousemove", onMove);
        lineGeos.forEach((g) => g.dispose());
        lineMats.forEach((m) => m.dispose());
        cometGeo.dispose();
        cometMat.dispose();
        renderer.dispose();
      };
    })();

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}
