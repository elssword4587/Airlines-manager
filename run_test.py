from am4_bot import AM4Bot


def main() -> None:
    bot = AM4Bot(
        email="mqn33yupw40x@gettranslation.app",
        password="AkuDewa123",
        headless=True,
    )

    try:
        bot.setup_driver()
        bot.ensure_logged_in()
        bot.log_status_snapshot()
        print("--- Running check_departures() ---")
        bot.check_departures()
        print("--- Running check_fuel() ---")
        bot.check_fuel()
        print("--- Running scan_consumables() ---")
        bot.scan_consumables()
    finally:
        bot.close_driver()


if __name__ == "__main__":
    main()
