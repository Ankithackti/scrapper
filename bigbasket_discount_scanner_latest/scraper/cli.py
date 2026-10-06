import argparse
import logging
import time

from .offer_monitor import BigBasketDiscountMonitor


def main():
    parser = argparse.ArgumentParser(description="BigBasket public discount scanner")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("discount-monitor", help="Scan public BigBasket offers")
    p.add_argument("--threshold", type=float, default=60)
    p.add_argument("--pages-per-category", type=int, default=2)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--max-discovery-pages", type=int, default=5000)
    p.add_argument("--pincode", default=None)
    p.add_argument("--location", default=None)
    p.add_argument("--interval", type=int, default=None)
    p.add_argument("--once", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    if args.command == "discount-monitor":
        monitor = BigBasketDiscountMonitor(
            threshold=args.threshold,
            pages_per_category=args.pages_per_category,
            delay=args.delay,
            concurrency=args.concurrency,
            max_discovery_pages=args.max_discovery_pages,
            pincode=args.pincode,
            location=args.location,
        )

        try:
            while True:
                monitor.run_once()

                if args.once or args.interval is None:
                    break

                logging.info("Waiting %s minutes before next scan...", args.interval)
                time.sleep(args.interval * 60)
        finally:
            monitor.close()


if __name__ == "__main__":
    main()
