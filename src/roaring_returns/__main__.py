import argparse
from pathlib import Path
from .data import fetch_data
from .experiments import run_experiments


def main():
    parser = argparse.ArgumentParser(description="Cash-flow rebalancing research prototype")
    parser.add_argument("command", choices=["fetch", "fetch-planner", "run", "research", "demo"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--split", choices=["development", "validation", "evaluation"], default="development")
    parser.add_argument("--refresh", action="store_true", help="Explicitly replace cached provider snapshots")
    parser.add_argument("--source", choices=["yahoo", "synthetic"], default="synthetic", help="v0.2 data source")
    parser.add_argument("--publish", action="store_true", help="Export derived v0.2 results to the public results folder")
    parser.add_argument("--period", choices=["2005-2014", "2015-2019", "2020-2025"], action="append")
    parser.add_argument("--port", type=int, default=8501, help="Local demo port")
    args = parser.parse_args()
    if args.command == "fetch":
        result = fetch_data(args.root, args.refresh)
        print(f"Validated {result['common_rows']} common sessions for QQQ, GLD, IEF.")
        for item in result["files"]:
            print(f"{item['symbol']}: {item['first_date']} to {item['last_date']}, {item['rows']} rows")
    elif args.command == "fetch-planner":
        from .planner_data import fetch_planner_data
        result = fetch_planner_data(args.root)
        print(f"Planner snapshot: {', '.join(result['assets'])}; {result['first_session']} to {result['last_session']}.")
    elif args.command == "research":
        from .research_runner import run_study, publish_study
        destination = args.root/"results"/("execution_v2" if args.source == "yahoo" else "execution_v2_synthetic")
        if args.publish and destination.exists():
            parser.error(f"Public export already exists: {destination}. Run without --publish for a new private run; explicitly archive the old export before replacing it.")
        output, summary = run_study(args.root, source=args.source, periods=args.period,
                                    progress=lambda message: print(message, flush=True))
        print(f"Wrote {len(summary)} exploratory configurations to {output}")
        if args.publish:
            print(f"Public aggregate export: {publish_study(output, destination)}")
    elif args.command == "demo":
        import subprocess
        import sys
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(args.root/"demo_app.py"),
                        "--server.address", "127.0.0.1", "--server.port", str(args.port)], check=True)
    else:
        output, summary = run_experiments(args.root, args.split)
        print(f"Wrote {len(summary)} scenarios to {output}")
        selected = summary[(summary.initial_wealth == 10000) & (summary.monthly_contribution == 100)]
        print(selected[["strategy", "signal_rms_deviation_pp", "posttrade_rms_deviation_pp",
                        "posttrade_outside_band_fraction", "annual_sales_over_mean_wealth"]].to_string(index=False))


if __name__ == "__main__":
    main()
