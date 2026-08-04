"""Generate a reproducible random project and a step-by-step solver report.

Run from the repository root:
    python tests/run_generator_diagnostics.py --seed 17 --employees 10
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.trace import build_random_project
from persistence.project_io import save_project


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostyka constraintów generatora grafików")
    parser.add_argument("--seed", type=int, default=7, help="seed losowania; ten sam seed daje ten sam input")
    parser.add_argument("--employees", type=int, default=8, help="liczba pracowników")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "Output" / "diagnostics")
    parser.add_argument("--time-limit", type=float, default=3, help="limit sekund na pojedynczy etap solvera")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    schedule, shop, metadata = build_random_project(seed=args.seed, employee_count=args.employees)
    input_path = args.output_dir / f"random_project_seed_{args.seed}.json"
    report_path = args.output_dir / f"diagnostics_seed_{args.seed}.json"
    final_path = args.output_dir / f"generated_project_seed_{args.seed}.json"

    # This file can be opened directly by the application and contains all
    # leave/sick/locked days plus employee flags and availability windows.
    save_project(input_path, schedule, shop)
    report = AutoScheduleGenerator(schedule, shop).diagnose(report_path, args.time_limit)
    # The normal generator has extensive legacy console debugging.  The report
    # is the readable diagnostic artifact, so keep this command-line runner quiet.
    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(
            trace_output_path=args.output_dir / f"trace_seed_{args.seed}.json"
        )
    save_project(final_path, schedule, shop)

    print(f"Input projektu: {input_path}")
    print(f"Raport etapowy: {report_path}")
    print(f"Wygenerowany grafik: {final_path}")
    print(f"Seed: {metadata['seed']}; zablokowane wpisy: {len(metadata['blocked_days'])}")
    print(f"Wynik generatora: {result}")
    if report["infeasibility"]:
        print("Infeasible:", report["infeasibility"])


if __name__ == "__main__":
    main()
