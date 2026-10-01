import { useEffect, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  Box,
  Braces,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Code2,
  Copy,
  ExternalLink,
  Layers3,
  LoaderCircle,
  MoveUpRight,
  Play,
  Radio,
  RefreshCw,
  ScanLine,
  Settings2,
  ShieldCheck,
  Square,
  Terminal,
  TriangleAlert,
  Waypoints,
  X,
} from "lucide-react";
import type { CSSProperties } from "react";
import RobotViewport from "./RobotViewport";
import { usePlatform } from "./usePlatform";
import type { MissionRequest, PlatformEvent, Robot, RobotState } from "./types";

const toDegrees = (radians: number) => (radians * 180) / Math.PI;
const poseIcons = [CircleDot, ScanLine, Box];
const title = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (first) => first.toUpperCase());
const time = (value: string) =>
  new Date(value).toLocaleTimeString([], { hour12: false });

export default function App() {
  const { robots, state, live, catalogError, reload } = usePlatform();
  const [selected, setSelected] = useState("");
  const [duration, setDuration] = useState(5);
  const [manual, setManual] = useState(false);
  const [targets, setTargets] = useState<number[]>([]);
  const [pending, setPending] = useState(false);
  const [cancelPending, setCancelPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [lastRequest, setLastRequest] = useState<MissionRequest | null>(null);
  const [inspectOpen, setInspectOpen] = useState(true);
  const robot = robots.find((item) => item.id === selected) ?? robots[0];
  const current = state?.robots.find((item) => item.id === robot?.id);
  const fresh =
    live &&
    current?.connected &&
    current.state_age_ms !== null &&
    current.state_age_ms !== undefined &&
    current.state_age_ms <= 1500;
  const available = Boolean(
    fresh &&
    current?.controller_ready &&
    current.status === "ready" &&
    !pending,
  );
  const missions = (state?.missions ?? [])
    .filter((item) => item.robot === robot?.id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const mission = missions[0];
  const events = (state?.events ?? [])
    .filter((item) => !item.robot || item.robot === robot?.id)
    .sort((a, b) => b.id - a.id)
    .slice(0, 7);
  const busy = mission?.status === "running" || mission?.status === "accepted";
  const status = !live ? "offline" : (current?.status ?? "offline");
  useEffect(() => {
    if (!selected && robots[0]) setSelected(robots[0].id);
  }, [robots, selected]);
  useEffect(() => {
    setManual(false);
    setTargets([]);
    setError("");
    setNotice("");
    setLastRequest(null);
  }, [selected]);
  useEffect(() => {
    if (!targets.length && current?.joint_positions.length)
      setTargets([...current.joint_positions]);
  }, [current?.joint_positions, targets.length]);

  async function submit(type: string, inputs: Record<string, unknown>) {
    if (!robot || !available) return;
    const request = {
      id: `web-${crypto.randomUUID().slice(0, 8)}`,
      type,
      robot: robot.id,
      actor: "web-console",
      inputs,
    };
    setPending(true);
    setError("");
    setNotice("");
    setLastRequest(request);
    try {
      const response = await fetch("/api/missions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail),
        );
      setNotice("Mission accepted by the platform.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The mission request could not be sent.",
      );
    } finally {
      setPending(false);
    }
  }
  async function cancel() {
    if (!robot) return;
    setCancelPending(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        `/api/robots/${encodeURIComponent(robot.id)}/stop`,
        { method: "POST" },
      );
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.detail || "Cancellation failed.");
      setNotice(result.detail);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Cancellation could not be sent.",
      );
    } finally {
      setCancelPending(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="IAC robot platform home">
          <div className="brand-icon">
            <Waypoints size={24} />
          </div>
          <b>
            IAC<span> / </span>PLATFORM
          </b>
          <span className="version">01</span>
        </a>
        <div className="topbar-center">
          <span className="workspace-dot" />
          Robot integration workspace
        </div>
        <div className="topbar-right">
          <span className="mode-badge">
            <Layers3 size={13} />
            ROS 2 mock hardware
          </span>
          <span className={`connection ${live ? "live" : ""}`}>
            <span className="dot" />
            {live ? "Live connection" : "Reconnecting"}
          </span>
        </div>
      </header>
      <main>
        <div className="page-heading">
          <div>
            <div className="breadcrumb">
              <span>WORKSPACE</span>
              <ChevronRight size={11} />
              <span>ROBOT CONTROL</span>
            </div>
            <h1>
              Different robots.<span> One interface.</span>
            </h1>
            <p>A common control layer, connected to official ROS 2 stacks.</p>
          </div>
          <div className="heading-mark">
            <span>CONTROL SURFACE</span>
            <b>
              OEM <ArrowLeftRightIcon /> API
            </b>
            <small>One command contract</small>
          </div>
        </div>
        {catalogError && (
          <div className="global-error" role="alert">
            <TriangleAlert size={18} />
            <span>
              {catalogError}. Start the platform backend to load the robot
              catalog.
            </span>
            <button onClick={reload}>
              <RefreshCw size={14} />
              Retry
            </button>
          </div>
        )}
        <div className="workspace">
          <aside className="control-panel">
            <div className="section-heading">
              <span className="section-number">01</span>
              <h2>Select robot</h2>
              <span className="small-tag">{robots.length} adapters</span>
            </div>
            <div
              className="robot-picker"
              role="group"
              aria-label="Select robot"
            >
              {robots.map((item) => {
                const rs = state?.robots.find((entry) => entry.id === item.id);
                return (
                  <button
                    key={item.id}
                    className={`robot-option ${robot?.id === item.id ? "active" : ""}`}
                    onClick={() => setSelected(item.id)}
                    aria-pressed={robot?.id === item.id}
                    aria-label={`${item.manufacturer} ${item.model}`}
                    style={{ "--robot-accent": item.accent } as CSSProperties}
                  >
                    <span className="robot-glyph">
                      <Waypoints size={24} />
                    </span>
                    <span className="robot-option-label">
                      <small>{item.manufacturer}</small>
                      <strong>{item.model}</strong>
                    </span>
                    <span
                      className={`robot-indicator ${live && rs?.connected ? "online" : ""}`}
                      title={live && rs?.connected ? "Connected" : "Offline"}
                    />
                    {robot?.id === item.id && (
                      <span className="selected-check">
                        <Check size={10} />
                      </span>
                    )}
                  </button>
                );
              })}
              {!robots.length && !catalogError && (
                <div className="catalog-loading">
                  <LoaderCircle className="spin" size={17} />
                  Connecting to robot catalog…
                </div>
              )}
            </div>
            <div className="control-divider" />
            <div className="section-heading">
              <span className="section-number">02</span>
              <h2>Send a command</h2>
              <span className="icon-muted">
                <Settings2 size={15} />
              </span>
            </div>
            <p className="control-description">
              Choose a named pose or run the complete motion sequence.
            </p>
            <div className="pose-controls">
              {robot?.capabilities.includes("move_named") &&
                robot.poses.map((pose, index) => {
                  const Icon = poseIcons[index % poseIcons.length];
                  return (
                    <button
                      key={pose.id}
                      disabled={!available}
                      onClick={() =>
                        void submit("move_named", { pose: pose.id, duration })
                      }
                    >
                      <Icon size={17} />
                      <span>{pose.label}</span>
                      <MoveUpRight size={13} />
                    </button>
                  );
                })}
            </div>
            <div className="duration-control">
              <label htmlFor="duration">Segment duration</label>
              <span>
                <b>{duration}</b> sec
              </span>
              <input
                id="duration"
                type="range"
                min="2"
                max="12"
                step="1"
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
              />
              <div>
                <small>2s · faster</small>
                <small>12s · slower</small>
              </div>
            </div>
            {robot?.capabilities.includes("run_demo") && (
              <button
                className="run-button"
                disabled={!available}
                onClick={() => void submit("run_demo", { duration })}
              >
                {pending ? (
                  <LoaderCircle size={17} className="spin" />
                ) : (
                  <Play size={17} fill="currentColor" />
                )}
                <span>Run demo sequence</span>
                <ArrowRight size={17} />
              </button>
            )}
            {robot?.capabilities.includes("stop") && (
              <button
                className="cancel-button"
                disabled={cancelPending}
                onClick={() => void cancel()}
              >
                <Square size={12} fill="currentColor" />
                Cancel motion
              </button>
            )}
            <p className="cancel-note">
              Software cancellation · not a safety stop
            </p>
            <div className="feedback-message" role="status" aria-live="polite">
              {error ? (
                <div className="error-message">
                  <TriangleAlert size={15} />
                  <span>{error}</span>
                  <button
                    aria-label="Dismiss error"
                    onClick={() => setError("")}
                  >
                    <X size={13} />
                  </button>
                </div>
              ) : notice ? (
                <div className="notice-message">
                  <CheckCircle2 size={14} />
                  <span>{notice}</span>
                </div>
              ) : !fresh ? (
                <div className="idle-message">
                  <Radio size={14} />
                  <span>Motion controls unlock with fresh ROS feedback.</span>
                </div>
              ) : (
                <div className="idle-message">
                  <ShieldCheck size={14} />
                  <span>Joint limits checked before dispatch.</span>
                </div>
              )}
            </div>
            {robot?.capabilities.includes("move_joints") && (
              <div className="manual-section">
                <button
                  className="disclosure"
                  aria-expanded={manual}
                  onClick={() => setManual((value) => !value)}
                >
                  <Settings2 size={14} />
                  <span>Joint targets</span>
                  <ChevronDown size={15} className={manual ? "rotate" : ""} />
                </button>
                {manual && (
                  <div className="manual-controls">
                    <div className="manual-info">
                      <span>Angles in degrees</span>
                      <button
                        disabled={!fresh}
                        onClick={() =>
                          setTargets([...(current?.joint_positions ?? [])])
                        }
                      >
                        Use current
                      </button>
                    </div>
                    {robot.joint_names.map((name, index) => (
                      <label className="manual-joint" key={name}>
                        <span title={name}>J{index + 1}</span>
                        <input
                          aria-label={`Joint ${index + 1} target`}
                          type="number"
                          step="1"
                          min={toDegrees(robot.limits[index].lower).toFixed(1)}
                          max={toDegrees(robot.limits[index].upper).toFixed(1)}
                          value={
                            targets[index] === undefined
                              ? ""
                              : Number(toDegrees(targets[index]).toFixed(1))
                          }
                          onChange={(event) =>
                            setTargets((values) => {
                              const next = [...values];
                              next[index] =
                                (Number(event.target.value) * Math.PI) / 180;
                              return next;
                            })
                          }
                        />
                        <small>°</small>
                      </label>
                    ))}
                    <button
                      className="manual-submit"
                      disabled={!available || targets.length !== robot.dof}
                      onClick={() =>
                        void submit("move_joints", {
                          positions: targets,
                          duration,
                        })
                      }
                    >
                      Move to joint targets
                      <ArrowRight size={14} />
                    </button>
                  </div>
                )}
              </div>
            )}
            <div className="mode-note">
              <Layers3 size={16} />
              <div>
                <strong>Real ROS. Simulated hardware.</strong>
                <p>
                  Official models and ROS controllers. No physical robot is
                  connected.
                </p>
              </div>
            </div>
          </aside>
          <div className="main-panel">
            <div className="robot-header">
              <div>
                <span className="eyebrow">CONNECTED MODEL</span>
                <h2>
                  {robot?.name ?? "Robot workspace"}
                  <span>{robot ? `${robot.dof} AXES` : "—"}</span>
                </h2>
              </div>
              <div className={`status-pill ${status}`}>
                <span className="dot" />
                {title(status)}
              </div>
            </div>
            {robot ? (
              <RobotViewport
                robot={robot}
                state={current}
                live={Boolean(fresh)}
              />
            ) : (
              <div className="empty-viewport">
                <Box size={48} />
                <span>Waiting for the platform</span>
                <p>The official robot model will appear here.</p>
              </div>
            )}
            {robot && (
              <JointTelemetry
                robot={robot}
                state={current}
                fresh={Boolean(fresh)}
              />
            )}
            <div className="execution-bar">
              <div className="execution-icon">
                {busy ? (
                  <LoaderCircle size={20} className="spin" />
                ) : mission?.status === "succeeded" ? (
                  <CheckCircle2 size={20} />
                ) : (
                  <Activity size={20} />
                )}
              </div>
              <div className="execution-label">
                <span className="eyebrow">
                  {mission ? "LATEST MISSION" : "EXECUTION"}
                </span>
                <strong>
                  {mission
                    ? title(mission.phase || mission.status)
                    : "Ready when you are"}
                </strong>
                <small>
                  {mission
                    ? mission.detail || mission.id
                    : "Send the same command to either robot."}
                </small>
              </div>
              <div className="execution-progress">
                <div>
                  <span>{mission ? title(mission.status) : "Standby"}</span>
                  <b>
                    {mission ? `${Math.round(mission.progress * 100)}%` : "—"}
                  </b>
                </div>
                <div className={`progress-track ${mission?.status ?? ""}`}>
                  <span
                    style={{
                      width: `${Math.max(0, Math.min(100, (mission?.progress ?? 0) * 100))}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
        {robot && (
          <div className="architecture-strip">
            <div className="architecture-caption">
              <Layers3 size={16} />
              <span>
                SAME API.
                <br />
                <b>SWAPPABLE ADAPTER.</b>
              </span>
            </div>
            <div className="architecture-flow">
              <div>
                <span className="flow-icon">
                  <Box size={16} />
                </span>
                <span>
                  Web console<small>OEM-independent</small>
                </span>
              </div>
              <ArrowRight className="flow-arrow" size={16} />
              <div>
                <span className="flow-icon">
                  <Braces size={16} />
                </span>
                <span>
                  Mission API<small>Validate & coordinate</small>
                </span>
              </div>
              <ArrowRight className="flow-arrow" size={16} />
              <div className="adapter-node">
                <span className="flow-icon">
                  <Waypoints size={16} />
                </span>
                <span>
                  {robot.adapter.name}
                  <small>Selected adapter</small>
                </span>
              </div>
              <ArrowRight className="flow-arrow" size={16} />
              <div>
                <span className="flow-icon">
                  <Radio size={16} />
                </span>
                <span>
                  ROS 2 controller<small>Mock hardware feedback</small>
                </span>
              </div>
            </div>
            <button
              onClick={() => setInspectOpen((value) => !value)}
              aria-expanded={inspectOpen}
              title="Toggle implementation details"
            >
              <Code2 size={16} />
              <ChevronDown size={14} className={inspectOpen ? "rotate" : ""} />
            </button>
          </div>
        )}
        {inspectOpen && (
          <div className="details-grid">
            <section className="events-panel">
              <div className="panel-heading">
                <h2>
                  <Activity size={16} />
                  Event stream
                </h2>
                <span className="small-tag">{live ? "LIVE" : "OFFLINE"}</span>
              </div>
              <div
                className="events-list"
                aria-label="Controller and platform events"
              >
                {events.length ? (
                  events.map((event) => (
                    <EventRow key={event.id} event={event} />
                  ))
                ) : (
                  <div className="events-empty">
                    <Terminal size={23} />
                    <span>Controller and mission events appear here.</span>
                  </div>
                )}
              </div>
            </section>
            <section className="api-panel">
              <div className="panel-heading">
                <h2>
                  <Braces size={16} />
                  Common command contract
                </h2>
                <span className="small-tag">API v1</span>
              </div>
              {robot && (
                <RequestInspector
                  request={
                    lastRequest ?? {
                      id: "web-<unique-id>",
                      type: "move_named",
                      robot: robot.id,
                      actor: "web-console",
                      inputs: { pose: robot.poses[0]?.id ?? "ready", duration },
                    }
                  }
                  submitted={Boolean(lastRequest)}
                />
              )}
            </section>
          </div>
        )}
        <footer>
          <div>
            <span className="footer-symbol">IAC</span>
            <span>Robot integration platform · ROS 2 Humble</span>
          </div>
          <span>
            Joint-space motion · no collision planning · mock feedback
          </span>
          {robot && (
            <a href={robot.source_url} target="_blank" rel="noreferrer">
              Official driver source
              <ExternalLink size={12} />
            </a>
          )}
        </footer>
      </main>
    </div>
  );
}

function JointTelemetry({
  robot,
  state,
  fresh,
}: {
  robot: Robot;
  state?: RobotState;
  fresh: boolean;
}) {
  return (
    <section className="telemetry" aria-label="Live joint positions">
      <div className="telemetry-heading">
        <span>
          <Activity size={13} />
          JOINT FEEDBACK
        </span>
        <span>
          {fresh && state?.state_age_ms !== null ? (
            <>
              <span className="dot" />
              {Math.round(state?.state_age_ms ?? 0)} ms old
            </>
          ) : (
            "No fresh telemetry"
          )}
        </span>
      </div>
      <div className="joint-grid">
        {robot.joint_names.map((name, index) => {
          const value = state?.joint_positions[index];
          const limit = robot.limits[index];
          const percentage =
            value === undefined
              ? 0
              : Math.max(
                  0,
                  Math.min(
                    100,
                    ((value - limit.lower) / (limit.upper - limit.lower)) * 100,
                  ),
                );
          return (
            <div
              className={`joint ${!fresh ? "stale" : ""}`}
              key={name}
              title={name}
            >
              <div>
                <span>J{String(index + 1).padStart(2, "0")}</span>
                <small>deg</small>
              </div>
              <strong>
                {value === undefined ? "—" : toDegrees(value).toFixed(1)}
                <small>°</small>
              </strong>
              <div className="joint-track">
                <span style={{ width: `${percentage}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EventRow({ event }: { event: PlatformEvent }) {
  return (
    <div className={`event-row ${event.level}`}>
      <span className="event-dot" />
      <time dateTime={event.timestamp}>{time(event.timestamp)}</time>
      <div>
        <span>{event.message}</span>
        <small>
          {event.source}
          {event.mission ? ` / ${event.mission}` : ""}
        </small>
      </div>
    </div>
  );
}

function RequestInspector({
  request,
  submitted,
}: {
  request: MissionRequest;
  submitted: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(request, null, 2);
  return (
    <>
      <div className="request-route">
        <span>POST</span>
        <code>/api/missions</code>
        <small>
          {submitted ? "Last submitted request" : "Request preview"}
        </small>
        <button
          title="Copy request JSON"
          aria-label="Copy request JSON"
          onClick={() => {
            void navigator.clipboard
              .writeText(json)
              .then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1600);
              })
              .catch(() => {});
          }}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
      </div>
      <pre className="request-json">
        {json.split("\n").map((line, index) => {
          const parts = line.match(/^(\s*)("[^\"]+")(.*)$/);
          return (
            <span key={index}>
              <i>{index + 1}</i>
              {parts ? (
                <>
                  {parts[1]}
                  <b>{parts[2]}</b>
                  <em>{parts[3]}</em>
                </>
              ) : (
                line
              )}
              {"\n"}
            </span>
          );
        })}
      </pre>
      <div className="api-footnote">
        <ArrowDown size={12} />
        <span>
          Only the robot identifier changes. The platform resolves the adapter.
        </span>
      </div>
    </>
  );
}

function ArrowLeftRightIcon() {
  return <span className="heading-arrows">⇄</span>;
}
