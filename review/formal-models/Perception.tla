--------------------------- MODULE Perception ---------------------------
EXTENDS Naturals, FiniteSets, TLC
CONSTANTS RejectStale, OwnerOnly, RequireConsent
VARIABLES epoch, role, enabled, current, consent, starts, started,
          pending, submitted, accepted
vars == <<epoch, role, enabled, current, consent, starts, started,
          pending, submitted, accepted>>
Roles == {"A", "B"}
Empty == [session |-> 0, role |-> "A", epoch |-> 0]
Token(s,r,e) == [session |-> s, role |-> r, epoch |-> e]
Audit(w,c) == [who |-> w, consent |-> c]
Delivered(p,s,r,e,a,c) ==
  [session |-> p.session, role |-> p.role, epoch |-> p.epoch,
   nowSession |-> s, nowRole |-> r, nowEpoch |-> e,
   enabled |-> a, consent |-> c]

Init == /\ epoch = 0 /\ role = "A" /\ enabled = TRUE
        /\ current = 0 /\ consent = FALSE /\ starts = 0
        /\ started = {} /\ pending = Empty /\ submitted = {}
        /\ accepted = {}

Start == \E who \in {"owner", "plugin"}, grant \in BOOLEAN :
  /\ enabled /\ current = 0 /\ starts < 2
  /\ (~OwnerOnly \/ who = "owner") /\ (~RequireConsent \/ grant)
  /\ starts' = starts + 1 /\ current' = starts + 1 /\ consent' = grant
  /\ started' = started \cup {Audit(who,grant)}
  /\ UNCHANGED <<epoch,role,enabled,pending,submitted,accepted>>

Capture ==
  /\ current > 0 /\ pending = Empty /\ current \notin submitted
  /\ pending' = Token(current,role,epoch)
  /\ submitted' = submitted \cup {current}
  /\ UNCHANGED <<epoch,role,enabled,current,consent,starts,started,accepted>>

Deliver ==
  /\ pending # Empty
  /\ (~RejectStale \/ (pending.session = current /\ pending.role = role
                       /\ pending.epoch = epoch /\ enabled /\ consent))
  /\ accepted' = accepted \cup {Delivered(pending,current,role,epoch,enabled,consent)}
  /\ pending' = Empty
  /\ UNCHANGED <<epoch,role,enabled,current,consent,starts,started,submitted>>

Drop == /\ pending # Empty /\ pending' = Empty
        /\ UNCHANGED <<epoch,role,enabled,current,consent,starts,started,submitted,accepted>>

Stop == \E target \in {1,2} :
  /\ current # 0
  /\ current' = IF current = target THEN 0 ELSE current
  /\ consent' = IF current = target THEN FALSE ELSE consent
  /\ UNCHANGED <<epoch,role,enabled,starts,started,pending,submitted,accepted>>

SwitchScope == \E nextRole \in Roles :
  /\ epoch < 2 /\ epoch' = epoch + 1 /\ role' = nextRole
  /\ current' = 0 /\ consent' = FALSE
  /\ UNCHANGED <<enabled,starts,started,pending,submitted,accepted>>

DisableCamera ==
  /\ enabled /\ enabled' = FALSE /\ current' = 0 /\ consent' = FALSE
  /\ UNCHANGED <<epoch,role,starts,started,pending,submitted,accepted>>

EnableCamera ==
  /\ ~enabled /\ enabled' = TRUE
  /\ UNCHANGED <<epoch,role,current,consent,starts,started,pending,submitted,accepted>>

Next == Start \/ Capture \/ Deliver \/ Drop \/ Stop \/ SwitchScope
        \/ DisableCamera \/ EnableCamera
TypeOK == /\ epoch \in 0..2 /\ role \in Roles /\ enabled \in BOOLEAN
          /\ current \in 0..2 /\ consent \in BOOLEAN /\ starts \in 0..2
          /\ started \subseteq [who : {"owner","plugin"}, consent : BOOLEAN]
          /\ pending \in {Empty} \cup {Token(s,r,e) : s \in {1,2}, r \in Roles, e \in 0..2}
          /\ submitted \subseteq {1,2}
          /\ accepted \subseteq [session : {1,2}, role : Roles, epoch : 0..2,
                 nowSession : 0..2, nowRole : Roles, nowEpoch : 0..2,
                 enabled : BOOLEAN, consent : BOOLEAN]
OwnerConsent == \A a \in started : a.who = "owner" /\ a.consent
NoLateDelivery == \A a \in accepted :
  a.session = a.nowSession /\ a.role = a.nowRole /\ a.epoch = a.nowEpoch
  /\ a.enabled /\ a.consent
Safety == TypeOK /\ OwnerConsent /\ NoLateDelivery
Spec == Init /\ [][Next]_vars
=============================================================================
