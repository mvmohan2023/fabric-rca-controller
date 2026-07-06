# Fabric Controller RCA Framework - Project Context

## Purpose
This document captures the architecture, design decisions, current implementation state, and extension model for the Fabric Controller RCA framework.

## Current Goal
Build an engineering-grade RCA framework where new fault-injection scenarios can plug into the existing pipeline without rebuilding telemetry, RCA report generation, reasoning, or UI.

## Current Status
- Fault injection runner exists
- Stress orchestrator exists
- RCA UI report builder exists
- Engineering reasoning builder exists
- Executive RCA Dashboard exists
- Engineering Investigation UI exists
- Leaf1 through Leaf7 degraded-hold scenarios validated
