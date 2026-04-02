# Intake Patterns by User Type

## Explorer (Motivational Interviewing)

Open questions, motivation discovery first.

```
Q1 (Open Framing):     "You mentioned wanting to run AI locally — what situation made you feel you needed it?"
Q2 (Capability Probe): "Are you currently using any AI tools, or is this your first time?"
Q3 (Closed Probe):     "Do you have a budget or existing hardware in mind?"
Q4 (Confirmation):     "When we finish here, what do you want to have decided or learned?"
```

---

## Optimizer (SPIN)

Current situation → pain → implication → value.

```
Q1 (Situation):    "What API/model are you using now? About how much per month?"
Q2 (Problem):      "What's the most frustrating or limiting part of your current setup?"
Q3 (Implication):  "If that problem continues, what do you think happens?"
Q4 (Need-Payoff):  "If it's resolved, what changes most for you?"
```

---

## Builder (5 Whys)

Quick confirmation, direct to execution.

```
Q1:          "[user-mentioned goal] — is that right? Give me the final goal in one sentence."
Q1.5 (5 Whys, required):
             "Why do you need that? What problem are you trying to solve?"
             → Run this even if the user directly states a technical spec.
             → Once actual_need is confirmed, proceed to Q2.
Q2:          "What's the specific blocker right now? (hardware / model selection / framework / cost)"
```

Max 3 turns including Q1.5 to reach GATE.
If `actual_need` is clear from Q1.5, skip Q2 and go directly to GATE.

---

## Decider (2×2 Direct)

Confirm comparison criteria only.

```
Q1: "So it's A vs B. What's the most important factor for your decision? (cost / performance / ease of setup / scalability)"
Q2: "Do you need to decide now, or can you test first?"
```

2 turns to GATE.
