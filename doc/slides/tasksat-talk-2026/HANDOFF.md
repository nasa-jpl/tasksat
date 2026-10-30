# TaskSAT talk, 2026: handoff notes

A 20-minute Beamer talk on TaskSAT. 21 frames, 32 PDF pages (because of the `\pause`s).
Same theme and footer as the old talks in `../old-talks/`: Madrid, JPL export-control line.

## Build

```sh
cd doc/slides/tasksat-talk-2026
pdflatex -interaction=nonstopmode main.tex   # run twice for the frame count
```

## Structure (`main.tex` inputs these in order)

| file | min | frames |
|---|---|---|
| `intro.tex` | 3 | MEXEC; the four questions (∃∃, ∀∀, ∀∃, compositional); the pipeline |
| `language.tex` | 6 | Rover2: timelines, tasks, impact timing, constraints and properties, schedule, results, UNSAT |
| `encoding.tex` | 3 | zones; rate × zone width as the one nonlinear term; property checking by negation |
| `beyond.tex` | 5 | realizability (vacuity trap, CEGIS); compositional (example, fine print and the 199 case); lint |
| `conclusion.tex` | 2 | five lessons; Questions? |

## Where the content comes from

The outputs on the slides are real, not invented. They were produced on 2026-10-30:

- Rover2 = `tests/tasknet_files/examples/rover2.tn`. `figures/rover2-timeline.png` is a crop of
  that run's `timeline.png`: the task panel plus battery and temperature.
  `rover2-results.png`, `impacts.png` and `architecture.png` come from `website/static/img/`.
- The UNSAT frame is rover2 with `after charge;` uncommented, run with `--mode satisfy`
  (core listing abridged).
- The realizability frame is `tests/tasknet_files/valid/tasknet53_realizability_violated.tn --realizability`.
- The compositional frame is `tasknet62_compositional_holds.tn` (20 cycles, 0.05 s).
- The 199-waypoint numbers (34 s, the battery rate timeline as the bottleneck) come from
  `jpl/mexec/compositional/FINDINGS_199.md`. The lint numbers (0.17 s vs 240 s) come from CLAUDE.md.
- `figures/mexec.png` is the diagram cropped out of the Feb 2026 talk's `mexec.png`. The
  point-of-contact box was dropped.

## Known residuals

- A few overfull boxes of under 13 pt remain: the impacts image, the CEGIS figure, the closing
  slide. None of them shows when rendered.
- The zone figure on "Zones" is schematic: task positions are to scale, but the horizon
  is drawn at 320, not 400.
- The 199 case is internal (`jpl/` is gitignored). Check before giving this talk outside JPL.
