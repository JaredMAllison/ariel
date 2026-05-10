# The LMF Covenant

**Version:** 0.1
**Status:** Active

---

## What This Is

The Local Mind Foundation is an open framework for building personal cognitive support systems. This document is its governing covenant — the empirical foundation, the design obligations, and the terms of contribution.

It is not a manifesto. It does not aspire to serve all minds. It serves the minds it currently serves, and documents that service as evidence.

---

## The Evidence Model

Every principle in this framework derives from a specific neurological reality. The logic is:

```
Profile → Requirement → Principle → Contribution
```

- **Profile** — a neurological pattern that shapes how a person processes, executes, and experiences. Not a label. A functional description.
- **Requirement** — what that profile demands from a cognitive support system, derived from observed failure modes and friction points.
- **Principle** — the design obligation the requirement creates. Not a preference. A necessary condition.
- **Contribution** — a concrete implementation that fulfills the principle, validated against a real instance.

Principles are not chosen because they sound good. They exist because a specific neurological reality made them necessary.

---

## Active Profiles

These are the neurological profiles for which this framework is currently validated. They are not the only profiles worth serving — they are the ones for which evidence currently exists.

| Profile | Key Requirements |
|---------|-----------------|
| ADHD | One task at a time. No paralysis from choice. Mode is operator-declared, never inferred. |
| Autism | Predictable surfaces. No surprising state changes. System does not require social negotiation to operate. |
| AuDHD | All of the above, compounded. Working memory cannot be assumed. Every session must reconstruct state. |
| Working Memory Deficiency | External memory is not optional enhancement. It is baseline function. |
| Trauma | System never escalates urgency. System never withdraws support. Consistency is safety. |

---

## The Instance Counter

Each contribution in this framework tracks how many active instances employ it. This is empirical evidence — not endorsement, not safety certification.

```
contribution: surface-one-task
instances: ▓▓▓░░   (3 active instances)
profiles: [ADHD, AuDHD]
status: proven
```

**Status definitions:**

| Status | Meaning |
|--------|---------|
| `unproven` | Active in one instance. Personal validation only. |
| `multi-instance` | Active in 2+ instances. Community peer review completed. |
| `proven` | Active in 3+ instances across 2+ profiles. Strongest evidence. |

**What the review covers:** Code review, data handling, privacy, configuration. The review is community peer review, not medical or safety certification. The framework makes no clinical claims.

**What the review does not cover:** Whether the contribution will work for any specific person. Neurological support is deeply individual. Evidence from multiple instances increases confidence — it does not guarantee applicability.

---

## Instance Privacy

Instance identity in this framework is private by default.

- Instance names are hashed in all public records — never exposed as plaintext
- Identity disclosure is operator opt-in, not required
- No personal data is collected by the framework itself — the counter increments against an anonymous hash
- The operator retains full control over what is disclosed and to whom

The framework is interested in the *pattern*, not the person. When a contribution shows evidence of working across multiple anonymous instances, that evidence stands on its own.

---

## Contribution Terms

Anyone may contribute to this framework. Contributions are accepted under these terms:

1. **Derive from evidence.** Every principle must trace to at least one real neurological requirement from a real profile. Hypothetical needs are not grounds for principles.

2. **No magic solutions.** Contributions document what worked, in what context, for which profile. They do not promise universality.

3. **Privacy by default.** Contributions must not expose operator identity without explicit opt-in. Hashed instance IDs are the standard.

4. **Unproven until proven.** A new contribution enters the framework at `unproven` status. Peer review and multi-instance evidence earns `multi-instance` and `proven` status. This is not gatekeeping — it is evidence.

5. **The operator is not the user.** This framework is built by people who need it, for people who need it. The operator is always in charge of their own instance. No contribution overrides that.

6. **Contributed prompts cannot gate-keep write access.** Onboarding scripts, conversation templates, and prompt contributions may guide the operator — they may never condition write access on compliance, refuse to proceed without operator agreement, or persist behavioral changes without explicit operator confirmation. The write-gate is always operator-controlled, never contribution-controlled.

---

## What This Framework Is Not

- It is not a medical device. It is personal software.
- It is not a certification body. Evidence is not certification.
- It is not universal. It serves the minds it currently serves.
- It is not complete. It grows as instances grow.

---

## Design Principle

**The system comes to the user.**

Not: "here is a system, configure it to your needs."
Not: "here is a questionnaire, describe your neurological profile."

The system reduces friction until the user can engage. First contact is a conversation, not a form. Profile builds from exchange. The vault skeleton is infrastructure — empty, ready, waiting for the person.

The system finds the user.
