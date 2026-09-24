# Changelog

## [Unreleased]

## [0.2.0] - 2026-09-24

- Preserve the selected TV matte across collage updates, including a choice of no matte, and continue without a matte when TV metadata is unavailable (#4).

## [0.1.2] - 2026-09-24

- Create installer releases after every PR merge (#3).

## [0.1.1] - 2026-09-24

- Simplify guided setup to ask only for the TV address, offering the saved address on later runs.
- Keep the TV permission pause and require an explicit answer before enabling automatic collage updates.

## [0.1.0] - 2026-09-23

- Guided installation on Debian and Ubuntu with a systemd service and fifteen-minute timer.
- Send changed Fugleramme collages only while the TV is already in Art Mode.
- Retry interrupted uploads and pending artwork cleanup, while preserving saved state across runs.
