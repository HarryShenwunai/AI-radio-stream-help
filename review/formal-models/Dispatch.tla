---------------------------- MODULE Dispatch ----------------------------
EXTENDS Naturals, TLC

CONSTANTS AtomicAdmission, AtomicCleanup, AtomicCommit, PrivateBarrier

VARIABLES owner, publicPhase, privatePhase, handle, cancelled, scannedHandle,
          stopUsed, permit, published, missedWindow, staleCommit, overtook
vars == <<owner, publicPhase, privatePhase, handle, cancelled, scannedHandle,
          stopUsed, permit, published, missedWindow, staleCommit, overtook>>

Init == /\ owner = "none" /\ publicPhase = "idle" /\ privatePhase = "idle"
        /\ handle = FALSE /\ cancelled = FALSE /\ scannedHandle = FALSE
        /\ stopUsed = FALSE /\ permit = FALSE /\ published = FALSE
        /\ missedWindow = "none" /\ staleCommit = FALSE /\ overtook = FALSE

PublicAcquire ==
  /\ owner = "none" /\ publicPhase = "idle"
  /\ (~PrivateBarrier \/ privatePhase \notin {"announced", "scanned"})
  /\ owner' = "public"
  /\ publicPhase' = IF AtomicAdmission THEN "registered" ELSE "locked"
  /\ handle' = AtomicAdmission
  /\ overtook' = (privatePhase \in {"announced", "scanned"})
  /\ UNCHANGED <<privatePhase, cancelled, scannedHandle, stopUsed, permit,
                  published, missedWindow, staleCommit>>

PublicRegister ==
  /\ owner = "public" /\ publicPhase = "locked"
  /\ publicPhase' = "registered" /\ handle' = TRUE
  /\ UNCHANGED <<owner, privatePhase, cancelled, scannedHandle, stopUsed,
                  permit, published, missedWindow, staleCommit, overtook>>

PrivateAnnounce ==
  /\ privatePhase = "idle" /\ privatePhase' = "announced"
  /\ UNCHANGED <<owner, publicPhase, handle, cancelled, scannedHandle,
                  stopUsed, permit, published, missedWindow, staleCommit, overtook>>

PrivateCancelScan ==
  /\ privatePhase = "announced" /\ privatePhase' = "scanned"
  /\ scannedHandle' = handle
  /\ cancelled' = (cancelled \/ handle)
  /\ missedWindow' = IF owner = "public" /\ ~handle
                      THEN publicPhase ELSE missedWindow
  /\ UNCHANGED <<owner, publicPhase, handle, stopUsed, permit,
                  published, staleCommit, overtook>>

PrivateAcquire ==
  /\ privatePhase = "scanned" /\ owner = "none"
  /\ owner' = "private" /\ privatePhase' = "using"
  /\ UNCHANGED <<publicPhase, handle, cancelled, scannedHandle, stopUsed,
                  permit, published, missedWindow, staleCommit, overtook>>

PrivateImmediateBusy ==
  /\ privatePhase = "scanned" /\ owner = "public" /\ ~scannedHandle
  /\ privatePhase' = "rejected"
  /\ UNCHANGED <<owner, publicPhase, handle, cancelled, scannedHandle, stopUsed,
                  permit, published, missedWindow, staleCommit, overtook>>

PrivateBoundedWaitExpired ==
  /\ privatePhase = "scanned" /\ owner = "public" /\ scannedHandle
  /\ privatePhase' = "rejected"
  /\ UNCHANGED <<owner, publicPhase, handle, cancelled, scannedHandle, stopUsed,
                  permit, published, missedWindow, staleCommit, overtook>>

PrivateRelease ==
  /\ privatePhase = "using" /\ owner = "private"
  /\ privatePhase' = "done" /\ owner' = "none"
  /\ UNCHANGED <<publicPhase, handle, cancelled, scannedHandle, stopUsed,
                  permit, published, missedWindow, staleCommit, overtook>>

StopPublic ==
  /\ ~stopUsed /\ stopUsed' = TRUE /\ cancelled' = (cancelled \/ handle)
  /\ UNCHANGED <<owner, publicPhase, privatePhase, handle, scannedHandle,
                  permit, published, missedWindow, staleCommit, overtook>>

PublicCommit ==
  /\ owner = "public" /\ publicPhase = "registered"
  /\ publicPhase' = IF AtomicCommit THEN "committed" ELSE "approved"
  /\ permit' = ~cancelled
  /\ published' = IF AtomicCommit THEN ~cancelled ELSE published
  /\ UNCHANGED <<owner, privatePhase, handle, cancelled, scannedHandle,
                  stopUsed, missedWindow, staleCommit, overtook>>

PublicAppendUnsafe ==
  /\ owner = "public" /\ publicPhase = "approved"
  /\ publicPhase' = "committed" /\ published' = permit
  /\ staleCommit' = (permit /\ cancelled)
  /\ UNCHANGED <<owner, privatePhase, handle, cancelled, scannedHandle,
                  stopUsed, permit, missedWindow, overtook>>

PublicClear ==
  /\ owner = "public" /\ publicPhase = "committed"
  /\ publicPhase' = IF AtomicCleanup THEN "done" ELSE "cleared"
  /\ owner' = IF AtomicCleanup THEN "none" ELSE "public"
  /\ handle' = FALSE
  /\ UNCHANGED <<privatePhase, cancelled, scannedHandle, stopUsed, permit,
                  published, missedWindow, staleCommit, overtook>>

PublicReleaseUnsafe ==
  /\ owner = "public" /\ publicPhase = "cleared"
  /\ owner' = "none" /\ publicPhase' = "done"
  /\ UNCHANGED <<privatePhase, handle, cancelled, scannedHandle, stopUsed,
                  permit, published, missedWindow, staleCommit, overtook>>

Next == PublicAcquire \/ PublicRegister \/ PrivateAnnounce \/ PrivateCancelScan
        \/ PrivateAcquire \/ PrivateImmediateBusy \/ PrivateBoundedWaitExpired
        \/ PrivateRelease \/ StopPublic \/ PublicCommit \/ PublicAppendUnsafe
        \/ PublicClear \/ PublicReleaseUnsafe

TypeOK == /\ owner \in {"none", "public", "private"}
          /\ publicPhase \in {"idle", "locked", "registered", "approved", "committed", "cleared", "done"}
          /\ privatePhase \in {"idle", "announced", "scanned", "using", "done", "rejected"}
          /\ handle \in BOOLEAN /\ cancelled \in BOOLEAN /\ scannedHandle \in BOOLEAN
          /\ stopUsed \in BOOLEAN /\ permit \in BOOLEAN /\ published \in BOOLEAN
          /\ missedWindow \in {"none", "locked", "cleared"}
          /\ staleCommit \in BOOLEAN /\ overtook \in BOOLEAN

PublicOccupationDiscoverable == missedWindow = "none"
NoStaleCommit == ~staleCommit
PrivateWaiterHasPriority == ~overtook
Safety == TypeOK /\ PublicOccupationDiscoverable /\ NoStaleCommit /\ PrivateWaiterHasPriority
Spec == Init /\ [][Next]_vars
=============================================================================
