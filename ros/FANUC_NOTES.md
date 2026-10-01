# FANUC integration

The CRX-10iA uses FANUC's `ScaledJointTrajectoryController`, built from the official Humble driver source. Its official Xacro selects `mock_components/GenericSystem` with `use_mock=true`. The platform sends real ROS 2 `FollowJointTrajectory` actions and receives ROS joint states and action results. The FANUC hardware-interface implementation is compiled but not selected at runtime. This exercises the official controller stack with mock hardware; it does not test communication with a physical FANUC controller or ROBOGUIDE.

`fanuc_mock.launch.py` composes a headless controller manager and robot-state publisher. It loads the official robot Xacro and FANUC controller, omitting the upstream GUI slider, RViz, and unrelated I/O controllers. The common API contains no FANUC command translation branches; configured endpoints and joint order connect it to this stack.

- Action: `/fanuc/joint_trajectory_controller/follow_joint_trajectory`
- State: `/fanuc/joint_states`, with joints `J1` through `J6`
- Controller: `fanuc_controllers/ScaledJointTrajectoryController`
- Visual assets: `assets/fanuc/robot.urdf` and 14 original CRX-10iA visual/collision meshes; the browser uses the visual meshes.
- Build: `bash scripts/setup_fanuc.sh`
- Run: `ROS_DOMAIN_ID=71 bash scripts/run_fanuc.sh`

## Sources and compatibility

The source snapshot includes the required FANUC hardware, controller, library, and message packages, their tests and licenses, and the CRX-10iA description. `vendor/fanuc_sources.json` records repository and dependency commits. Git history, other model meshes, example applications, and the unused vcpkg checkout are omitted. The build uses bundled dependencies through CMake source overrides and performs no repository downloads. Output goes to `.runtime/fanuc_ws`.

Driver commit: `8f9f22e50f02042ded000440e305c7f6c820d5a2` (Humble, package version 1.6.0). Description commit: `fb40c9803a826ba68c7c8e28ba904a25efa7fcd2`. Sources are from [FANUC's driver](https://github.com/FANUC-CORPORATION/fanuc_driver) and [description repository](https://github.com/FANUC-CORPORATION/fanuc_description).

`fanuc_humble_realtime_buffer.patch` records a small compatibility change already applied to the bundled scaled controller: the current Humble joint-trajectory controller stores pending-goal and holding flags in `RealtimeBuffer<bool>`. Reads and writes use its buffer accessors rather than direct boolean access, matching the base controller's API. FANUC's three supplied dependency patches for sockpp, readerwriterqueue, and reflect-cpp are also already applied. Their patch files remain in the source snapshot. No motion algorithm was substituted.

The generated browser URDF uses the same official Xacro as ROS. Only resource paths are changed to web URLs; geometry, joint limits, and mesh bytes are retained. License and asset provenance are under `assets/fanuc`.

## Verification

Verified on October 1, 2026 with Ubuntu 22.04, ROS 2 Humble, ros2_control 2.50.0, and joint_trajectory_controller 2.45.0. A fresh build of the bundled source completed all six required packages without fetching dependencies.

A three-second trajectory reached `[0, -0.45, 0.55, 0, 0.7, 0]` radians with action status `SUCCEEDED`, error code `0`, and zero final joint-position error in the mock feedback. The test received 945 joint-state messages through completion and observed intermediate positions. An eight-second second goal was canceled after approximately 0.8 seconds; it returned `CANCELED`, and the reported position stayed unchanged during a subsequent 0.6-second observation. The two goals produced 76 action-feedback messages. Sample counts depend on scheduling and are records of this run, not timing guarantees.

All 14 mesh references resolved, the tool link existed, and every configured named pose was within the official URDF joint limits. These checks establish neither collision-free physical trajectories nor real hardware safety. Cancellation is a ROS software command, and the joint feedback comes from mock hardware.
