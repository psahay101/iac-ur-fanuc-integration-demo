# Validation

Verified on October 1, 2026 using Ubuntu 22.04.5, ROS 2 Humble, Python 3.10.12 and Node 24.15.0. The installed ros2_control version is 2.50.0; joint_trajectory_controller is 2.45.0.

## Backend and adapter tests

```bash
bash scripts/test.sh
```

**29 passed.** One third-party test-client deprecation warning was emitted; no test failures. Coverage includes:

- The same request contract and result handling for both configured OEMs.
- Invalid envelopes, poses, joint counts, nonfinite values, positions and velocity limits.
- Incomplete model configuration rejected at startup.
- Idempotent retries, conflicting IDs and busy-arm rejection.
- Failed actions, adapter exceptions, cancellation while unhealthy and reservation release.
- ROS joint-name reordering, extra/missing joints and malformed feedback.
- Joint and controller freshness, plus cancellation of late-accepted action goals.
- HTTP catalog, errors and WebSocket snapshots.

These tests use test doubles for isolation. The following checks use the running ROS stacks.

## HTTP → ROS → controller → feedback

With `bash scripts/run.sh` running in another terminal:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python tests/integration.py
```

The recorded integration run also cycled both real mock controllers through inactive/active states:

```bash
source /opt/ros/humble/setup.bash
ROS_DOMAIN_ID=71 ROS_LOCALHOST_ONLY=1 PYTHONNOUSERSITE=1 \
  .venv/bin/python tests/integration.py --controller-cycle
```

Run integration/browser tests serially while the console is idle; they send motion commands to the mock stacks.

Both arms passed the same named-pose request and three-waypoint demo through the public API. Intermediate joint feedback was observed, the ROS actions succeeded, and final target error in the returned mock state was **0 rad**. Software cancellation returned **CANCELED**; observed position drift during the subsequent 0.6-second check was **0 rad** for both arms. These are mock-state observations, not physical accuracy measurements.

Additional checks passed: live WebSocket state, duplicate request handling, busy rejection, out-of-limits rejection, official URDF serving, and controller deactivation blocking new motion with HTTP 503 while the cancel endpoint remained callable. Reactivation restored readiness. Disabling each joint-state broadcaster during a ten-second trajectory made the feedback stale, failed the mission and requested action cancellation; after feedback returned, the joints were confirmed held. The raw result is [artifacts/integration-results.json](artifacts/integration-results.json).

The underlying source integrations were also tested independently: four UR packages and six FANUC packages built successfully. Direct ROS trajectory tests observed intermediate positions, successful action results and cancellation. See [FANUC integration notes](ros/FANUC_NOTES.md) for the compatibility patch and source-specific details.

## Clean build after relocation

A source copy was placed in a separate temporary directory with no `.venv`, `.runtime`, `node_modules` or build caches. `bash scripts/setup.sh` completed successfully: a fresh Python environment, all four UR packages, all six FANUC packages, npm installation and the production frontend build. Running `bash scripts/test.sh` in that copy also produced **29 passed**. Its ROS install symlinks and setup prefixes were checked for references to the original workspace; none were found.

## Browser and production build

```bash
cd frontend
npm run build
PLAYWRIGHT_BROWSERS_PATH=../.runtime/browsers npx playwright install chromium
npm run test:e2e
```

The TypeScript check and Vite production build passed. **Four Playwright cases passed** against the running API and both ROS stacks:

1. Load both official models without asset/page errors, submit the same commands, observe changed ROS joint feedback and successful completion.
2. Switch robot views during execution, preserve the running mission and cancel it through the web console.
3. Use the mobile layout and joint-target panel without horizontal overflow.
4. Lose the browser feedback connection and verify that motion controls disable. Only the transport failure is injected in this case; the other tests use live ROS execution.

The model/command case also passed again after the final camera-framing adjustment. Screenshots are under `frontend/screenshots/`; the robot model is driven only by received joint positions. Camera fitting changes the camera, not robot motion.

## Simulation boundaries

The actual ROS graph, controllers, actions, message transport, API and browser are running. Device state comes from the official stacks' ros2_control mock hardware. No physical vendor communication, external pose measurement, collision planning, manufacturing result, certified stop or restart recovery was tested. Tool coordinates use URDF forward kinematics; mission progress uses controller trajectory feedback. The frontend does not synthesize robot motion.
