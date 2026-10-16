(*
  OpenPLC IEC 61131-3 Structured Text Program: Medical X-Ray Acquisition Controller
  Compatible with OpenPLC Editor / OpenPLC Runtime v3
*)
PROGRAM XRayController
  VAR
    DoorInterlock AT %QX0.0 : BOOL := TRUE;
    ExposureTrigger AT %QX0.1 : BOOL := FALSE;
    DeviceStatus AT %QW0 : INT := 1;
    TubeKvp AT %QW1 : INT := 85;
    TubeMas AT %QW2 : INT := 12;
    SelectedStudyIdx AT %QW3 : INT := 0;
    LastSyncHttpCode AT %QW4 : INT := 200;
  END_VAR

  (* Enforce radiation room door safety interlock *)
  IF NOT DoorInterlock THEN
    DeviceStatus := 4; (* INTERLOCK_OPEN *)
    ExposureTrigger := FALSE;
  ELSIF ExposureTrigger THEN
    DeviceStatus := 3; (* TRANSFERRING / STAGING STUDY *)
  ELSE
    DeviceStatus := 1; (* READY *)
  END_IF;

  (* Clamp kVp and mAs to physical tube limits *)
  IF TubeKvp < 40 THEN TubeKvp := 40; END_IF;
  IF TubeKvp > 150 THEN TubeKvp := 150; END_IF;
  IF TubeMas < 1 THEN TubeMas := 1; END_IF;
  IF TubeMas > 200 THEN TubeMas := 200; END_IF;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK MainTask(INTERVAL := T#100ms, PRIORITY := 0);
    PROGRAM Inst0 WITH MainTask : XRayController;
  END_RESOURCE
END_CONFIGURATION
