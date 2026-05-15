# Planogram Studio Instructions

## Core Principle

Planogram is a physical and mathematical constraint problem before it is a UI problem.

Never prioritize 3D visuals over correctness.

## Required Model Order

1. Fixture model
2. Product model
3. Constraint model
4. Solver / placement engine
5. Validation report
6. Visual rendering

## Fixture Model

Fixtures should include:

- type
- width
- height
- depth
- shelf count
- shelf dimensions
- temperature zone
- physical position
- capacity
- allowed categories
- blocked zones
- special handling rules

## Product Model

Products should include:

- SKU
- name
- width
- height
- depth
- weight
- category
- brand
- temperature requirement
- sales velocity
- margin / priority
- mandatory flag
- min/max facing
- stackability
- forbidden fixtures

## Constraint Examples

- Product must fit physically.
- Frozen products must be in frozen fixtures.
- Chilled products must be in chilled fixtures.
- Heavy products should not be placed too high.
- Mandatory SKUs must be placed or reported.
- Brand/category blocks should be preserved where required.
- Facing count must not exceed shelf width/depth.
- Fixture capacity cannot be exceeded.

## Optimization

Use OR-Tools or similar solver for serious placement logic.

Objective may include:

- Sales potential
- Capacity utilization
- Picking efficiency
- Refill risk reduction
- Category coherence
- NSFR/fire risk reduction
- Operational simplicity

## Infeasible Cases

If placement fails, explain why.

Bad:

"Could not place product"

Good:

"SKU X could not be placed because it requires frozen storage and all frozen fixtures are at capacity."

## Renderer Rule

2D/3D renderer must display the validated engine output.

Renderer must not invent placement.
