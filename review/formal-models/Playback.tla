---------------------------- MODULE Playback ----------------------------
EXTENDS Naturals, FiniteSets, TLC
CONSTANTS MaxMerge, RejectStale, TerminalIsFinal, FirstPrefix
VARIABLES first, second, current, switched, pending, applied, dbPrefix,
          accepted, stoppedEver
vars == <<first, second, current, switched, pending, applied, dbPrefix,
          accepted, stoppedEver>>

Max2(a,b) == IF a >= b THEN a ELSE b
Maximum(S) == CHOOSE n \in S : \A other \in S : n >= other
Record(id,prefix) == [id |-> id, prefix |-> prefix]
Ack(id,nonce,scope,atCurrent,atSwitched) ==
    [id |-> id, nonce |-> nonce, scope |-> scope,
     atCurrent |-> atCurrent, atSwitched |-> atSwitched]

Init == /\ first = "pending" /\ second = "not_started" /\ current = 1
        /\ switched = FALSE /\ pending = {} /\ applied = {} /\ dbPrefix = 0
        /\ accepted = {} /\ stoppedEver = {}

PlayFirst ==
  /\ current = 1 /\ ~switched /\ first = "pending"
  /\ first' = "playing" /\ pending' = pending \cup {Record("P1",0)}
  /\ UNCHANGED <<second,current,switched,applied,dbPrefix,accepted,stoppedEver>>

PlaySecond ==
  /\ current = 2 /\ ~switched /\ second = "pending"
  /\ second' = "playing" /\ pending' = pending \cup {Record("P2",0)}
  /\ UNCHANGED <<first,current,switched,applied,dbPrefix,accepted,stoppedEver>>

ReceiveCompleted ==
  \E id \in {1,2}, nonce \in {1,2}, scope \in {1,2} :
    /\ (IF id = 1 THEN first ELSE second) # "not_started"
    /\ (~RejectStale \/
         (id = current /\ ~switched /\ nonce = id /\ scope = 1))
    /\ (~TerminalIsFinal \/
         (IF id = 1 THEN first ELSE second) \in {"pending","playing","completed"})
    /\ first' = IF id = 1 THEN "completed" ELSE first
    /\ second' = IF id = 2 THEN "completed" ELSE second
    /\ pending' = pending \cup
           {IF id = 1 THEN Record("C1",FirstPrefix) ELSE Record("C2",3)}
    /\ accepted' = accepted \cup {Ack(id,nonce,scope,current,switched)}
    /\ UNCHANGED <<current,switched,applied,dbPrefix,stoppedEver>>

StopFirst ==
  /\ current = 1 /\ ~switched /\ first \in {"pending","playing"}
  /\ first' = "stopped" /\ pending' = pending \cup {Record("S1",0)}
  /\ stoppedEver' = stoppedEver \cup {1}
  /\ UNCHANGED <<second,current,switched,applied,dbPrefix,accepted>>

BeginSecond ==
  /\ second = "not_started" /\ ~switched
  /\ second' = "pending" /\ current' = 2
  /\ first' = IF first \in {"pending","playing"} THEN "stopped" ELSE first
  /\ pending' = IF first \in {"pending","playing"}
                 THEN pending \cup {Record("S1",0)} ELSE pending
  /\ stoppedEver' = IF first \in {"pending","playing"}
                    THEN stoppedEver \cup {1} ELSE stoppedEver
  /\ UNCHANGED <<switched,applied,dbPrefix,accepted>>

StopSecond ==
  /\ current = 2 /\ ~switched /\ second \in {"pending","playing"}
  /\ second' = "stopped" /\ pending' = pending \cup {Record("S2",0)}
  /\ stoppedEver' = stoppedEver \cup {2}
  /\ UNCHANGED <<first,current,switched,applied,dbPrefix,accepted>>

SwitchScope ==
  /\ ~switched /\ switched' = TRUE /\ current' = 0
  /\ first' = IF first \in {"pending","playing"} THEN "stopped" ELSE first
  /\ second' = IF second \in {"pending","playing"} THEN "stopped" ELSE second
  /\ pending' = pending
        \cup (IF first \in {"pending","playing"} THEN {Record("S1",0)} ELSE {})
        \cup (IF second \in {"pending","playing"} THEN {Record("S2",0)} ELSE {})
  /\ stoppedEver' = stoppedEver
        \cup (IF first \in {"pending","playing"} THEN {1} ELSE {})
        \cup (IF second \in {"pending","playing"} THEN {2} ELSE {})
  /\ UNCHANGED <<applied,dbPrefix,accepted>>

Persist ==
  \E record \in pending :
    /\ pending' = pending \ {record}
    /\ applied' = applied \cup {record}
    /\ dbPrefix' = IF MaxMerge THEN Max2(dbPrefix,record.prefix) ELSE record.prefix
    /\ UNCHANGED <<first,second,current,switched,accepted,stoppedEver>>

Next == PlayFirst \/ PlaySecond \/ ReceiveCompleted \/ StopFirst \/ BeginSecond
        \/ StopSecond \/ SwitchScope \/ Persist

TypeOK == /\ first \in {"pending","playing","completed","stopped"}
          /\ second \in {"not_started","pending","playing","completed","stopped"}
          /\ current \in {0,1,2} /\ switched \in BOOLEAN
          /\ pending \subseteq {Record("C1",FirstPrefix),Record("S1",0),Record("C2",3),Record("S2",0),Record("P1",0),Record("P2",0)}
          /\ applied \subseteq {Record("C1",FirstPrefix),Record("S1",0),Record("C2",3),Record("S2",0),Record("P1",0),Record("P2",0)}
          /\ dbPrefix \in {0,FirstPrefix,3}
          /\ stoppedEver \subseteq {1,2}
          /\ accepted \subseteq {Ack(i,n,s,c,w) : i \in {1,2}, n \in {1,2},
                      s \in {1,2}, c \in {0,1,2}, w \in BOOLEAN}
NoScopeOrNonceRevival == \A a \in accepted :
    a.id = a.nonce /\ a.scope = 1 /\ a.atCurrent = a.id /\ ~a.atSwitched
StoppedIsTerminal == /\ (1 \in stoppedEver => first = "stopped")
                     /\ (2 \in stoppedEver => second = "stopped")
ConfirmedPrefixNeverForgotten == dbPrefix = Maximum({0} \cup {record.prefix : record \in applied})
Safety == TypeOK /\ NoScopeOrNonceRevival /\ StoppedIsTerminal /\ ConfirmedPrefixNeverForgotten
Spec == Init /\ [][Next]_vars
=============================================================================
