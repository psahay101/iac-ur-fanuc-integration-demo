import { useEffect, useRef, useState } from "react";
import {
  Crosshair,
  Expand,
  MousePointer2,
  Orbit,
  Route,
  TriangleAlert,
} from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import URDFLoader from "urdf-loader";
import type { URDFRobot } from "urdf-loader";
import type { Robot, RobotState } from "./types";

type Props = { robot: Robot; state?: RobotState; live: boolean };

/** Render the official model from observed joints. No command ever animates this view. */
export default function RobotViewport({ robot, state, live }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const model = useRef<URDFRobot | null>(null);
  const resetCamera = useRef<() => void>(() => {});
  const latest = useRef({ positions: state?.joint_positions ?? [], live });
  latest.current = { positions: state?.joint_positions ?? [], live };
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [showTrace, setShowTrace] = useState(true);
  const traceEnabled = useRef(true);
  traceEnabled.current = showTrace;
  const [tcp, setTcp] = useState<number[] | null>(null);
  useEffect(() => {
    if (!host.current) return;
    const container = host.current;
    let disposed = false;
    let animation = 0;
    let loaded: URDFRobot | null = null;
    let renderer: THREE.WebGLRenderer;
    setLoading(true);
    setLoadError("");
    setTcp(null);
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      setLoadError(
        "3D rendering is unavailable. Enable WebGL in this browser to view the robot.",
      );
      setLoading(false);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.domElement.setAttribute(
      "aria-label",
      "Interactive official robot model. Drag to orbit, scroll to zoom.",
    );
    renderer.domElement.setAttribute("role", "img");
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#dce2e2");
    scene.fog = new THREE.Fog("#dce2e2", 5, 13);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 50);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 0.4;
    controls.maxDistance = 7;
    controls.maxPolarAngle = Math.PI / 2 + 0.08;
    controls.target.set(0, 0, 0.5);
    camera.position.set(2, -2.6, 1.65);
    scene.add(new THREE.HemisphereLight("#ffffff", "#647773", 1.8));
    const keyLight = new THREE.DirectionalLight("#fff8ec", 3.0);
    keyLight.position.set(2, -3, 5);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(2048, 2048);
    keyLight.shadow.camera.left = -2;
    keyLight.shadow.camera.right = 2;
    keyLight.shadow.camera.top = 2;
    keyLight.shadow.camera.bottom = -2;
    keyLight.shadow.normalBias = 0.02;
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight("#d4e8ff", 1.6);
    fillLight.position.set(-3, 2, 3);
    scene.add(fillLight);
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(100, 100),
      new THREE.MeshStandardMaterial({ color: "#dce2e2", roughness: 1 }),
    );
    ground.position.z = -0.055;
    ground.receiveShadow = true;
    scene.add(ground);
    const grid = new THREE.GridHelper(8, 80, "#a4b2b2", "#bdc9c8");
    grid.rotation.x = Math.PI / 2;
    grid.position.z = -0.05;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.5;
    scene.add(grid);
    const platform = new THREE.Mesh(
      new THREE.CylinderGeometry(0.2, 0.215, 0.045, 64),
      new THREE.MeshStandardMaterial({
        color: "#aab9b8",
        metalness: 0.5,
        roughness: 0.55,
      }),
    );
    platform.rotation.x = Math.PI / 2;
    platform.position.z = -0.0275;
    platform.castShadow = true;
    platform.receiveShadow = true;
    scene.add(platform);
    const axes = new THREE.AxesHelper(0.19);
    axes.position.set(-0.34, -0.34, -0.045);
    scene.add(axes);
    const tracePoints: THREE.Vector3[] = [];
    const trace = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({
        color: "#187f75",
        transparent: true,
        opacity: 0.68,
      }),
    );
    scene.add(trace);
    const toolDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.009, 12, 12),
      new THREE.MeshBasicMaterial({ color: "#087e74" }),
    );
    toolDot.visible = false;
    scene.add(toolDot);
    const fit = () => {
      const box = loaded
        ? new THREE.Box3().setFromObject(loaded)
        : new THREE.Box3(
            new THREE.Vector3(-0.5, -0.5, 0),
            new THREE.Vector3(0.5, 0.5, 1),
          );
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const radius = Math.max(size.x, size.y, size.z, 0.85);
      const distance = radius * (camera.aspect < 1.25 ? 3.15 : 2.45);
      controls.target.copy(center);
      controls.target.z = Math.max(0.36, center.z);
      camera.position
        .copy(controls.target)
        .add(
          new THREE.Vector3(0.85, -1.1, 0.7)
            .normalize()
            .multiplyScalar(distance),
        );
      controls.update();
    };
    let automaticFraming = true;
    controls.addEventListener("start", () => {
      automaticFraming = false;
    });
    resetCamera.current = () => {
      automaticFraming = true;
      fit();
    };
    const manager = new THREE.LoadingManager();
    manager.onError = (url) => {
      if (!disposed)
        setLoadError(
          `An official model asset could not load: ${url.split("/").pop()}`,
        );
    };
    manager.onLoad = () => {
      if (disposed) return;
      if (loaded) {
        applyObservedJoints();
        loaded.traverse((object) => {
          if ((object as THREE.Mesh).isMesh) {
            object.castShadow = true;
            object.receiveShadow = true;
          }
        });
        fit();
      }
      setLoading(false);
    };
    const applyObservedJoints = () => {
      const values = latest.current.positions;
      if (
        loaded &&
        values.length === robot.joint_names.length &&
        values.every(Number.isFinite)
      ) {
        robot.joint_names.forEach((name, index) =>
          loaded!.setJointValue(name, values[index]),
        );
        loaded.updateMatrixWorld(true);
      }
    };
    const loader = new URDFLoader(manager);
    loader.parseCollision = false;
    // Asset URLs in the platform URDF are root-relative, not relative to its folder.
    loader.workingPath = location.origin;
    loader.load(
      robot.urdf_url,
      (result) => {
        if (disposed) {
          disposeObject(result);
          return;
        }
        loaded = result;
        model.current = result;
        scene.add(result);
        applyObservedJoints();
      },
      undefined,
      (error) => {
        if (!disposed) {
          setLoadError(
            error instanceof Error
              ? error.message
              : "The official robot model could not load.",
          );
          setLoading(false);
        }
      },
    );
    const resize = new ResizeObserver(() => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
    });
    resize.observe(container);
    const endpoint = new THREE.Vector3();
    let lastTelemetry = 0;
    let lastFrameCheck = 0;
    const bounds = new THREE.Box3();
    const corner = new THREE.Vector3();
    const render = (time: number) => {
      if (disposed) return;
      animation = requestAnimationFrame(render);
      applyObservedJoints();
      // Keep an observed motion in frame until the user takes camera control.
      // This changes only the camera; the arm always uses ROS joint positions.
      if (loaded && automaticFraming && time - lastFrameCheck >= 250) {
        bounds.setFromObject(loaded);
        let outside = false;
        for (const x of [bounds.min.x, bounds.max.x])
          for (const y of [bounds.min.y, bounds.max.y])
            for (const z of [bounds.min.z, bounds.max.z]) {
              corner.set(x, y, z).project(camera);
              if (Math.abs(corner.x) > 0.84 || Math.abs(corner.y) > 0.78)
                outside = true;
            }
        if (outside) fit();
        lastFrameCheck = time;
      }
      const tool = loaded?.links[robot.tool_link];
      if (
        tool &&
        latest.current.positions.length &&
        time - lastTelemetry >= 100
      ) {
        tool.getWorldPosition(endpoint);
        setTcp([endpoint.x, endpoint.y, endpoint.z]);
        toolDot.position.copy(endpoint);
        toolDot.visible = true;
        if (
          latest.current.live &&
          (!tracePoints.length ||
            tracePoints[tracePoints.length - 1].distanceTo(endpoint) > 0.002)
        ) {
          tracePoints.push(endpoint.clone());
          if (tracePoints.length > 650) tracePoints.shift();
          trace.geometry.dispose();
          trace.geometry = new THREE.BufferGeometry().setFromPoints(
            tracePoints,
          );
        }
        lastTelemetry = time;
      }
      trace.visible = traceEnabled.current;
      controls.update();
      renderer.render(scene, camera);
    };
    animation = requestAnimationFrame(render);
    return () => {
      disposed = true;
      cancelAnimationFrame(animation);
      resize.disconnect();
      controls.dispose();
      model.current = null;
      disposeObject(scene);
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, [robot]);

  return (
    <section className="viewport" ref={frame} aria-label="Robot visualization">
      <div className="viewport-top">
        <div>
          <span className="eyebrow dark">LIVE MODEL</span>
          <span className="model-caption">Official URDF & meshes</span>
        </div>
        <span
          className={`viewport-live ${live && state?.connected ? "is-live" : ""}`}
        >
          <span className="dot" />
          {live && state?.connected
            ? "ROS joint feedback"
            : "Awaiting live feedback"}
        </span>
      </div>
      <div className="canvas-host" ref={host} />
      {(loading || loadError) && (
        <div className="model-overlay">
          {loadError ? (
            <TriangleAlert size={24} />
          ) : (
            <span className="spinner" />
          )}
          <strong>{loadError || "Loading official robot assets"}</strong>
          {!loadError && <span>Building the articulated model</span>}
        </div>
      )}
      <div className="viewport-tools">
        <button
          title="Reset camera"
          aria-label="Reset camera"
          onClick={() => resetCamera.current()}
        >
          <Crosshair size={17} />
        </button>
        <button
          title="Toggle observed tool path"
          aria-label="Toggle observed tool path"
          aria-pressed={showTrace}
          className={showTrace ? "selected" : ""}
          onClick={() => setShowTrace((value) => !value)}
        >
          <Route size={17} />
        </button>
        <button
          title="Expand model view"
          aria-label="Expand model view"
          onClick={() => {
            if (document.fullscreenElement) void document.exitFullscreen();
            else void frame.current?.requestFullscreen().catch(() => {});
          }}
        >
          <Expand size={17} />
        </button>
      </div>
      <div className="viewport-bottom">
        <div className="tool-position">
          <span className="eyebrow dark">
            TOOL POSITION <small>URDF FK · m</small>
          </span>
          <div>
            {["X", "Y", "Z"].map((axis, index) => (
              <span key={axis}>
                <b>{axis}</b>
                {tcp ? tcp[index].toFixed(3) : "—"}
              </span>
            ))}
          </div>
        </div>
        <div className="orbit-hint">
          <Orbit size={14} />
          <span>Drag to orbit</span>
          <MousePointer2 size={12} />
          <span>Scroll to zoom</span>
        </div>
      </div>
    </section>
  );
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    mesh.geometry?.dispose();
    if (mesh.material)
      for (const material of Array.isArray(mesh.material)
        ? mesh.material
        : [mesh.material]) {
        for (const value of Object.values(material))
          if (value instanceof THREE.Texture) value.dispose();
        material.dispose();
      }
  });
}
