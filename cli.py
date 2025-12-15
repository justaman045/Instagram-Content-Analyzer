import argparse
from jobs.monitor import run_monitor
from jobs.analyze import run_analyze
from jobs.deliver import run_deliver
from setup.wizard import run_setup
from setup.preview import run_preview


def main():
    parser = argparse.ArgumentParser(
        description="Instagram Automation CLI"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="Initial setup & save config to DB")
    sub.add_parser("preview", help="Preview data without saving to DB")
    sub.add_parser("monitor", help="Run monitor once")
    sub.add_parser("deliver", help="Run delivery once")

    analyze = sub.add_parser("analyze", help="Analyze collected data")
    analyze.add_argument(
        "--inspect",
        action="store_true",
        help="Preview analysis without persisting results"
    )

    args = parser.parse_args()

    if args.command == "setup":
        run_setup()

    elif args.command == "preview":
        run_preview()

    elif args.command == "monitor":
        run_monitor()

    elif args.command == "analyze":
        run_analyze(preview=args.inspect)

    elif args.command == "deliver":
        run_deliver()


if __name__ == "__main__":
    main()
