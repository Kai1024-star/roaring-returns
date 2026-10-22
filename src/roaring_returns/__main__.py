import argparse
from pathlib import Path
from .data import fetch_data
from .experiments import run_experiments


def main():
    parser = argparse.ArgumentParser(description="Cash-flow rebalancing research prototype")
    parser.add_argument("command", choices=["fetch", "run"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--split", choices=["development", "validation", "evaluation"], default="development")
    parser.add_argument("--refresh", action="store_true", help="Explicitly replace cached provider snapshots")
    args = parser.parse_args()
    if args.command == "fetch":
        result = fetch_data(args.root, args.refresh)
        print(f"Validated {result['common_rows']} common sessions for QQQ, GLD, IEF.")
        for item in result["files"]:
            print(f"{item['symbol']}: {item['first_date']} to {item['last_date']}, {item['rows']} rows")
    else:
        output, summary = run_experiments(args.root, args.split)
        print(f"Wrote {len(summary)} scenarios to {output}")
        selected = summary[(summary.initial_wealth == 10000) & (summary.monthly_contribution == 100)]
        print(selected[["strategy", "signal_rms_deviation_pp", "posttrade_rms_deviation_pp",
                        "posttrade_outside_band_fraction", "annual_sales_over_mean_wealth"]].to_string(index=False))


if __name__ == "__main__":
    main()
