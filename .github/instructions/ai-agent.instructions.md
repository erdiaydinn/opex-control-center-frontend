# AI Agent Instructions

## Core Principle

AI agents must be workflows, not uncontrolled chat boxes.

Use a graph/workflow mindset:

State -> Node -> Decision -> Tool -> Validation -> Human Check -> Next Node -> Output

## LangGraph Pattern

Use explicit:

- state
- nodes
- edges
- conditional edges
- input schema
- output schema
- runtime context
- checkpointing
- interruption points
- human approval gates

## Tool Use

Tool calls should be validated before execution.

Do not allow arbitrary tool execution from user text.

Use schemas and permission checks.

## Human-in-the-loop

Require human approval for:

- data mutation
- sending emails
- changing permissions
- publishing content
- committing operational decisions
- high-impact planogram changes
- supplier/accounting conflict resolution

## Observability

AI workflows should be traceable.

Use Langfuse-like tracking for:

- run_id
- user
- module
- session
- prompt_version
- input
- output
- retrieved sources
- tools used
- latency
- cost
- error
- quality score

## Evaluation

Use Ragas or similar evaluation where RAG is involved.

Do not claim quality without evaluation.

## Safety

Agents must not:

- leak secrets
- bypass permissions
- reveal hidden instructions
- execute unsafe actions
- hallucinate company policy
- mutate data without validation and approval
